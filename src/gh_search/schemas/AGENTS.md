# schemas — 導覽

這個資料夾是整個專案的**資料字典**。所有會在 agent 各步驟之間傳來傳去的欄位、所有可能的列舉值（例如 `unsupported_intent` 這種字串），全部都住在這裡。

換句話說：當你在其他地方看到一個欄位或 enum，不用猜它長什麼樣，直接回這裡查就對了。這也是為什麼根目錄 `AGENTS.md` 把「不重複定義 schema」列成鐵律——如果每個模組各自寫一份「差不多的 dict」，很快就會有兩個版本開始偷偷漂移。

## 先看哪個

建議閱讀順序：

1. [`enums.py`](./enums.py) — 先看這個。裡面是所有字串型的列舉值，例如「這個 agent 可以跑的 tool 名稱清單」、「終止原因有哪幾種」、「意圖判斷的狀態有哪些」。不先看這個，其他檔案傳的值你看不懂。
2. [`shared_state.py`](./shared_state.py) — `SharedAgentState` 是 agent 的核心資料結構，agent loop 每一輪讀它、更新它、再傳給下一步。裡面又包了 `IntentionJudge`、`Validation`、`Execution`、`Control` 四個子物件，分別代表 agent 目前在四個面向的進度。
3. [`structured_query.py`](./structured_query.py) — `StructuredQuery` 是使用者自然語言被 LLM 解析之後的結構化結果。`compiler.py` 吃這個然後輸出 GitHub 查詢字串。
4. [`logs.py`](./logs.py) — 三種寫到磁碟的 log：`RunLog`（整次執行的總結）、`TurnLog`（每一輪的紀錄）、`FinalState`（最後的狀態快照）。對應到 `logger/` 寫出的三個檔案。
5. [`eval.py`](./eval.py) — eval 評測的結果結構，只給 `eval/scorer.py` 用。

## 這裡有幾個一定要知道的規矩

- **全部都是 immutable**。pydantic model 全開 `ConfigDict(extra="forbid", frozen=True)`：不能加沒定義過的欄位、也不能改已有欄位的值。要變更請用 `model_copy(update={...})`，拿到的是一份新物件，原本那份不會動。這是為了讓 agent loop 能安全地比較前後 state 的差異。
- **`StructuredQuery` 本身有驗證器**：日期必須 `created_after <= created_before`，而 `sort` 跟 `order` 要嘛都指定、要嘛都是 `None`，不能只填一個。寫測試時這些邊界值要特別留意。
- **所有 enum 都用 `str` 當基底**，這樣序列化成 JSON 寫 log 時可以直接用，不用特別處理。
- **「還沒解析出來」狀態請用 `None`，不要用空 dict `{}`**。之前踩過坑：用 `{}` 時，後面的程式會以為「已經解析了但結果是空的」，分不出來。

## 想新加一個欄位的時候

1. 先在對應的檔案（例如 `structured_query.py`）加上欄位、型別、預設值。
2. 把用到它的 tool、compiler、validator 都同步更新。
3. 補上對應的測試：`tests/test_schemas_*.py` 加欄位層級的檢查，再加上受影響的 tool 測試。
4. **絕對不要**在別的地方又宣告一份「幾乎一樣但略有不同的 dict」。如果你發現類似的東西，請直接合併回這個資料夾。
