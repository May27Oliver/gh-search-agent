# AGENTS.md

本專案給任何 agent / contributor 的開發守則。內容刻意保持精簡，規則以 **可驗證** 為優先。規格母本見 [specs/main/](./specs/main/README.md)。

**給人類讀者**：各主要資料夾底下另有一份 `AGENTS.md`（導覽圖），說明該資料夾的角色、檔案分工、以及從哪個檔案開始讀最快。第一次進這個 repo，建議閱讀順序：本檔 → [src/gh_search/AGENTS.md](./src/gh_search/AGENTS.md) → 你關心的子資料夾。

**撰寫資料夾導覽 AGENTS.md 的規則**：

- **務必白話**。假設讀者是剛加入的工程師（不是熟這份 spec 的 reviewer）。用完整句子、口語一點沒關係，不要堆專有名詞縮寫。
- 先講「這個資料夾在做什麼」、再講「從哪個檔案開始讀」，最後才講細節與眉角。不要一開場就丟一張表。
- 需要條列時，條列項本身也寫成完整句子，不要只丟一串名詞。
- 有 jargon（例：`LLMJsonCall`、`SharedAgentState`）第一次出現時附上一句白話解釋，不要預設讀者已經懂。
- 舉正面範例：[src/gh_search/agent/AGENTS.md](./src/gh_search/agent/AGENTS.md) 是目前的基準樣板，新增或改寫時請對齊這個風格。

## 1. 三條鐵律

1. **TDD**：先寫會紅的測試，再寫最小實作讓它綠，最後才 refactor。不允許「先寫功能，之後再補測試」。
2. **DDD**：依 domain 切層，不依檔案類型。Domain 層不得 import infrastructure。
3. **DRY**：同一段邏輯只能有一個來源。第二次抄之前，先抽成函數 / module。

任何 PR 違反這三條會被退回。

## 2. 不做的事（反過度工程）

- 不建立目前沒有使用者的抽象層或 interface（含「未來可能換 provider」這類 justification）。
- 不加 feature flag、沒有規格要求的 fallback、沒發生過的邊界處理。
- 不在 domain model 上加與 domain 無關的 metadata / telemetry / audit 欄位（這些走 logging 層）。
- 不為了「之後好擴充」而預留多態 / 泛型 / 繼承樹。需要時再抽。
- 不重複寫 validator、schema、enum：來源只能是 `src/gh_search/schemas/`。
- 不在多個地方各自維護同一份常數（例：`max_turns`、model name、tool name 清單）。

## 3. 可讀性與註解

程式碼的第一讀者是下一位工程師（可能是三個月後的自己），不是編譯器。

命名與結構：

- 名稱說明意圖，不說明型別或實作（`compiled_query` 比 `q_str` 好；`IntentStatus` 比 `State1` 好）。
- 函數只做一件事；超過 50 行先想能不能拆。
- 巢狀超過 3 層、或一個函數需要註解才看得懂主線邏輯時，拆出 helper。
- 公開 API（被其他模組 import 的函數 / class）必須有型別標註；內部 helper 可省。

何時寫註解：

- **WHY**：非顯而易見的約束、規格條文、歷史 bug 的 workaround、違反直覺的設計決策。
- **規格連結**：實作某個規格段落時，引用來源（例：`# MAIN_SPEC §4.2` 或 `# LOGGING.md §8`）。
- **公開介面**：module / public function / public class 的 docstring 說明「這個東西為何存在、誰會用、invariant 是什麼」。
- **不變量 / 邊界**：`assert` 或 docstring 點出「這個值永遠非 None、這個 dict 的 key 來自某個 enum」。

何時不寫：

- 註解只是在複述程式碼（`i += 1  # increment i`）。
- 用來標記過時 / 已刪除的東西（直接刪）。
- 解釋命名不良的變數（改名比加註解好）。

docstring 採用單段落風格，前一行講「這個函數做什麼」，必要時下一段講 invariant / 使用情境。不寫形式化的 Args/Returns，除非有真的需要說明的細節。

當你在 refactor 老程式碼，發現註解與程式碼不一致，**先修程式碼、再修註解或直接刪註解**，不要信註解。

## 4. TDD 工作流

每個 task 都遵循以下循環：

1. **RED**：先在 `tests/` 對應檔寫一個失敗測試，對應 PHASE1_PLAN 該 task 的「驗證方式」。
2. **GREEN**：寫最小實作讓新測試通過。禁止把尚未測到的邏輯一起寫進去。
3. **REFACTOR**：所有測試綠之後再重構；重構不可改測試。

每個 task 的 PR 至少要包含：

- 新增 / 變更的測試（可看出先紅後綠）
- 不碰與此 task 無關的檔案
- `pytest -q` 全綠

Coverage 要求：對 schema、compiler、validator、scorer 這類 deterministic 模組要求 **≥ 90 %**；對 tools 與 agent loop 要求 **≥ 80 %**；對外部 I/O 層（github client、openai adapter）至少要有 error-path tests。

## 5. DDD 分層

本專案 domain = **GitHub repository search**。以下是四層分工，import 方向只能從上往下：

```text
presentation:   src/gh_search/cli.py
application:    src/gh_search/agent/          # loop controller, tool orchestration
domain:         src/gh_search/schemas/        # entities, value objects, invariants
                src/gh_search/compiler.py     # pure domain service (structured_query -> GH query)
                src/gh_search/validator.py    # pure domain service
infrastructure: src/gh_search/github/         # HTTP client
                src/gh_search/llm/            # model adapter (OpenAI etc.)
                src/gh_search/logger/         # file-based session logger
```

規則：

- **Domain 層不可 import infrastructure**。compiler、validator、schemas 必須是純函數 / 純資料；要拿時間、ID、IO，由呼叫端注入。
- **Infrastructure 可 import domain**，反之不可。
- **Application 層負責串接**，不得把 domain 規則寫在這裡（例：compile mapping、validation rule 屬於 domain）。
- **Tools** 是 application-level adapter：把 shared state 餵給 domain service，再把結果寫回 state，不承擔 domain logic。

單檔 400 行以下為佳，超過 500 必須先拆。

## 6. DRY 的落地點

以下來源只能有一個版本，任何「看起來差不多」的第二份出現時，都要合併：

| 類型 | 單一來源 |
|---|---|
| `structured_query` schema | `schemas/structured_query.py` |
| shared agent state shape | `schemas/shared_state.py` |
| log schema | `schemas/logs.py` |
| eval result schema | `schemas/eval.py` |
| enum 值（intent_status / terminate_reason / next_tool 等） | `schemas/enums.py` |
| compiler mapping rules | `compiler.py` |
| validation rules | `validator.py` |
| tool 名稱清單 | `schemas/enums.py::ToolName` |
| default max_turns / model name | `config.py` |

parser、validator、logger、eval scorer 不得各自再定義欄位集合或預設值。

## 7. Commit / PR 規範

- commit message：`<type>: <what>`，type ∈ `feat/fix/refactor/test/docs/chore`。
- 一個 commit 只做一件事；TDD 的 RED → GREEN → REFACTOR 可以是三個 commit 也可以是一個 squash commit，但 diff 必須能單獨解釋。
- 不在 commit / code 加 AI 署名。

## 8. 驗收門檻（Phase 1 sign-off）

以下全部為綠才能結束 Phase 1：

- `pytest -q` 全綠，總 coverage ≥ 80 %
- `gh-search --help` 與 `gh-search check` 正常
- smoke eval（3–5 題）產出 `run.json` / `turns.jsonl` / `final_state.json`
- 至少 1 題正常題成功、1 題拒絕題正確拒絕、scorer 能區分四種 outcome

## 9. 當你不確定時

- 規格模糊 → 先回 [specs/main/](./specs/main/README.md) 查；仍模糊則在 PR 描述中明確標出「這題規格未定，我採用 X，若不對請指正」，**不要自己加一個新抽象層把它繞過去**。
- 既有模組已經做類似事 → **先 import、不要自己重寫一份**。
- 不清楚要不要加某個功能 → 預設不加。
