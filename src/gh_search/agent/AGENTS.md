# agent — 導覽

這個資料夾負責 agent 主迴圈：把使用者輸入一步一步處理完，直到找到 GitHub repository 搜尋結果，或明確決定停止。

整體流程是固定的：
`INTENTION_JUDGE → PARSE_QUERY → VALIDATE_QUERY → (REPAIR_QUERY)* → COMPILE_GITHUB_QUERY → EXECUTE_GITHUB_SEARCH → FINALIZE`

可以把它想成一台照表操課的機器。每一輪只做一件事，做完再決定下一步。

## 先看哪個

- [`loop.py`](./loop.py) — 主流程都在這裡。建議從 `run_agent_loop()` 開始往下讀：
  1. `_initial_state()` 建立第 0 輪的初始 state。
  2. 進入 for loop，每一輪先看 `state.control.next_tool` 指定下一步要跑哪個 tool。
  3. `_dispatch()` 依照這個值呼叫對應的 tool，tool 回傳更新後的 state。
  4. `_record_llm()` 會順手把這一輪 LLM 的原始輸出先存起來，讓 logger 後面可以寫檔，但不需要改動每個 tool 的介面。
  5. 每輪結束都會寫 `TurnLog`，也會輸出一份 artifact（`turn_NN_<tool>.json`）。
  6. 如果 `state.control.should_terminate` 已經是 `True`，或回合數超過 `max_turns`，流程就結束。

## 這個切法的用意

- **loop 只負責流程控制**。它只決定「現在該跑哪一步」，不負責判斷 query 合不合法、GitHub 查詢字串怎麼組，這些規則都在 tool 叫到的 domain service。
- `results_sink` 可以把最後找到的 `Repository` 結果帶出迴圈，讓 CLI 顯示給使用者看。它只是額外的輸出通道，不是 agent state 的一部分，所以沒有放進 schema。
- `_record_llm()` 的目的，是在不讓 tool 直接碰 logger 的前提下，還是能保留 LLM 原始回應。之後如果要記錄 latency、token 數，也優先沿用這種做法，不要把 logging 需求塞進 tool 參數。

## 常見修改場景

- 新增一個 tool：
  1. 在 `schemas/enums.py::ToolName` 加上新值。
  2. 實作對應的 tool。
  3. 在 `_dispatch()` 補上分派邏輯。
  4. 測試可參考 `tests/test_agent_loop.py`。
- 修改停止條件：
  1. 通常不是改 loop。
  2. 應該去改負責設定 `control.terminate_reason` 或 `control.should_terminate` 的 tool。
  3. loop 本身只讀這些欄位，不負責判斷業務規則。

## 看測試

`tests/test_agent_loop.py` 有主流程最重要的案例：假資料 LLM、正常停止、超過 `max_turns`、每輪 artifact 寫出。想快速理解這個 loop 怎麼運作，先看這份測試最快。
