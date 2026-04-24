# tools — 導覽

這個資料夾放的是 agent 每一輪會用到的「工具」（tool）。可以把一個 tool 想像成**一個小步驟的做法**：agent loop 每一輪都會叫其中一個 tool 來跑，tool 做完事情、把結果更新回 agent 的 state，然後由 loop 決定下一步要跑哪個 tool。

每個 tool 都是一個純函數，簽名都長一樣：吃進目前的 `SharedAgentState`（加上它需要的外部資源，例如 LLM 或 GitHub client），回傳一份新的 state。tool 裡面**不應該寫 domain 規則**，真正的規則應該住在 `compiler.py` / `validator.py` 這些 domain service，tool 只是把 state 餵給這些 service，再把結果抄回 state。

## 先看哪個

按照 agent loop 實際跑的順序：

| 檔案 | 它做什麼 | 依賴 |
|---|---|---|
| [`intention_judge.py`](./intention_judge.py) | 判斷使用者這句話到底是不是「找 GitHub repository」的需求。不是的話就直接標記為不支援、終止流程。 | LLM |
| [`parse_query.py`](./parse_query.py) | 把使用者的自然語言解析成 `StructuredQuery`。用 LLM 的 JSON schema 強約束格式。 | LLM |
| [`validate_query.py`](./validate_query.py) | 呼叫 `validator.validate_structured_query()`，檢查剛剛解析出來的東西有沒有矛盾，結果寫回 `state.validation`。 | `validator.py` |
| [`repair_query.py`](./repair_query.py) | 上面驗證不過的時候，叫 LLM 看著錯誤訊息再解析一次。重試幾次由 loop 的 `max_turns` 控制。 | LLM |
| [`compile_github_query.py`](./compile_github_query.py) | 呼叫 `compiler.compile_github_query()`，把結構化查詢變成 GitHub 認得的字串，寫進 `state.compiled_query`。 | `compiler.py` |
| [`execute_github_search.py`](./execute_github_search.py) | 實際打 GitHub API，把各種錯誤轉成 `ExecutionStatus`，把搜到的 `Repository` 清單透過 `results_sink` 傳出去。 | `github/` |

## 所有 tool 都必須遵守的約定

- **Signature 要一致**。全部都是 `fn(state, *, llm=..., github=..., results_sink=...) -> SharedAgentState`，沒用到的參數就忽略。這樣 loop 才能用同一套機制呼叫每個 tool，不用 if-else 判斷。
- **不可以原地改 state**。一律用 `state.model_copy(update={...})` 產一份新的再回傳。理由跟 schemas 那邊一樣：loop 會比對前後差異，中途被改壞會很難 debug。
- **下一步要跑哪個 tool 是 tool 自己寫進 `state.control.next_tool`**，loop 只負責讀。換句話說，流程控制權在 tool 手上，loop 是照表操課的排程器。
- **LLM tool 收到的是 `LLMJsonCall`**（定義在 [`llm/AGENTS.md`](../llm/AGENTS.md)），呼叫後回傳的物件有兩個欄位：`.parsed`（解析好的 dict，拿來用）和 `.raw_text`（LLM 吐出來的原始字串，loop 會自動抓去寫 log）。tool 不用自己處理 log，只要用 `.parsed` 即可。
- **tool 不寫 domain 規則**。如果你覺得「這段驗證邏輯寫在 tool 裡比較順手」，停下來想一下——那段邏輯應該搬去 `validator.py` 或 `compiler.py`。tool 保持薄薄一層就好。

## 測試

每個 tool 都有對應的測試檔（`tests/test_tool_*.py`）。想新加一個 tool，直接照抄現有測試的骨架就好：給一個起始 state、給一個假的（scripted）LLM，檢查跑完之後 state 的某些欄位是否變成預期的值。
