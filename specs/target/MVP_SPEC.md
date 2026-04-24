# MVP 規格：自然語言轉結構化查詢 CLI 工具

## 1. 目標

打造一個 CLI 工具，能把自然語言需求轉成結構化查詢，對公開資料來源執行查詢，並回傳結果。

本次 MVP 選定的 domain 是 **GitHub repository search**。

原因如下：

- GitHub 是公開 API，文件完整且穩定
- 查詢條件夠豐富，能清楚展示自然語言轉 query 的能力
- 結果容易人工驗證
- 很適合設計對抗式測試案例
- 最容易在 take-home 的時限內做出完整可 demo 的版本

## 1.1 作業要求對齊目標

除了產品本身可運作之外，這份 take-home 還有明確要求。MVP 與後續版本必須朝以下目標對齊：

### Part 1 必達目標

1. 建立一個 CLI 工具，能把自然語言查詢轉成 structured query
2. 這個 structured query 必須能真正對公開 API 或資料庫執行
3. 工具必須回傳真實查詢結果，而不只是輸出 query
4. 必須主動測試工具的失敗案例，例如模糊輸入、衝突條件、typo、非英文輸入
5. 必須修復最重要的 failure cases，提升工具對 edge cases 的處理能力
6. README 必須說明剩餘尚未解決的 failure cases 為何困難，並給出技術性解釋

### Part 2 必達目標

1. 設計一套 evaluation pipeline，用來評估模型產生 structured query 的能力
2. 程式化蒐集或生成 30 筆真實且多樣的自然語言查詢
3. 為每一題人工建立正確的 ground truth structured query
4. 至少評估 3 個模型，且必須同時包含 open-weight 與 closed-source 模型
5. 持續迭代 prompt 與 pipeline，直到所有選定模型都達到 **>85% accuracy**
6. README 必須分析模型選擇理由、各模型表現差異、初始錯誤模式，以及對 eval design 的學習

### MVP 與作業整體目標的關係

本文件定義的是第一階段可落地的最小產品範圍，但在設計時必須保留後續 break、hardening 與 eval 的擴充空間。因此 MVP 不能只是「能跑」，而必須具備：

- 可觀測性：能記錄 input、parsed query、compiled query、API response
- 可驗證性：structured query 有明確 schema，能與 ground truth 比對
- 可擴充性：後續能接多模型評測與 failure-case hardening

## 2. MVP 產品定義

這個 MVP 是一個命令列工具，具備以下能力：

1. 接收使用者輸入的自然語言查詢
2. 將查詢轉成內部使用的 structured query JSON
3. 驗證 structured query 是否合法
4. 將其編譯成 GitHub Search API request
5. 實際執行查詢
6. 印出生成的 query 與查詢結果

範例：

```bash
python cli.py "Find Python repos about logistics created after 2023 with more than 100 stars"
```

## 3. 使用者問題

使用者不知道 GitHub search syntax 或 API 參數，但希望能直接用自然語言描述查詢條件，例如：

- 主題或關鍵字
- 程式語言
- 建立時間
- stars 門檻
- 排序方式
- 回傳筆數

## 4. 目標使用者

MVP 的目標使用者是技術背景使用者，想在 terminal 中用比較自然的方式搜尋 GitHub repositories。

## 5. 範圍

### MVP 內含範圍

- 只支援 GitHub repository search
- Baseline 以英文自然語言查詢為主
- 單輪 CLI 互動
- 轉換到預先定義好的 JSON schema
- 驗證支援的欄位
- 實際呼叫 GitHub Search Repositories API
- 基本錯誤處理
- 記錄 input、generated query、API request 與 response summary

### MVP 不包含

- Pull request search
- Issue search
- 多輪澄清對話
- 除了少數明顯案例外的 typo 修正
- 互動式 TUI 或 web UI
- 超出環境變數設定範圍的登入流程

## 6. 支援的查詢能力

MVP 支援以下 repository search 條件：

- `keywords`
- `language`
- `created_after`
- `created_before`
- `min_stars`
- `max_stars`
- `sort`
- `order`
- `limit`

支援的查詢意圖範例：

- 「找 Rust repos，主題是 freight optimization」
- 「找 2024 年之後建立的 Python logistics repos」
- 「找超過 500 stars 的熱門 TypeScript repos」
- 「列出前 5 個 Go supply chain repos，依 stars 排序」

## 7. Structured Query Schema

內部資料表示方式採用標準化 JSON：

```json
{
  "keywords": ["logistics", "optimization"],
  "language": "Python",
  "created_after": "2024-01-01",
  "created_before": null,
  "min_stars": 100,
  "max_stars": null,
  "sort": "stars",
  "order": "desc",
  "limit": 5
}
```

規則如下：

- `keywords` 是搜尋關鍵字陣列
- 日期格式統一使用 ISO `YYYY-MM-DD`
- `sort` 只允許：`stars`、`forks`、`updated`
- `order` 只允許：`asc`、`desc`
- `limit` 預設值為 `10`，MVP 最大值為 `20`
- 所有欄位都必須存在；未指定時明確填入 `null`

## 7.1 Shared Agent State Schema

本專案不是單次 parser call，而是採用 bounded agent loop。每一輪 tool call 都必須共享同一份 state schema，並在此基礎上更新。

共享 state 範例如下：

```json
{
  "run_id": "uuid",
  "turn_index": 1,
  "max_turns": 5,
  "user_query": "find python repos about logistics after 2023 with 100+ stars",
  "intention_judge": {
    "intent_status": "supported",
    "reason": null,
    "should_terminate": false
  },
  "structured_query": {
    "keywords": ["logistics"],
    "language": "Python",
    "created_after": "2023-01-01",
    "created_before": null,
    "min_stars": 100,
    "max_stars": null,
    "sort": "stars",
    "order": "desc",
    "limit": 10
  },
  "validation": {
    "is_valid": true,
    "errors": [],
    "missing_required_fields": []
  },
  "compiled_query": "logistics language:Python stars:>=100 created:>=2023-01-01",
  "execution": {
    "status": "not_started",
    "response_status": null,
    "result_count": null
  },
  "control": {
    "next_tool": "execute_github_search",
    "should_terminate": false,
    "terminate_reason": null
  }
}
```

規則如下：

- 每個 tool 的輸入與輸出都必須基於同一份 shared state
- `turn_index` 每輪加一
- `max_turns` 固定為 `5`
- `intention_judge` 是第一道 gatekeeper
- `structured_query` 與 `validation` 是 agent planning 的核心狀態
- `compiled_query` 與 `execution` 是 API 執行階段的核心狀態
- `control` 用來明確標示下一步與終止條件

## 7.2 Machine-Readable Schema Contracts

除了人類可讀的文字規格外，實作時必須提供對應的 machine-readable schema。目的在於確保 parser、validator、logger、eval runner 都依賴同一套資料合約，而不是各自維護不同欄位集合。

### `structured_query` contract

`structured_query` 必須固定包含以下欄位：

- `keywords`
  型別：`string[]`
  預設：`[]`
- `language`
  型別：`string | null`
- `created_after`
  型別：`string | null`
  格式：`YYYY-MM-DD`
- `created_before`
  型別：`string | null`
  格式：`YYYY-MM-DD`
- `min_stars`
  型別：`integer | null`
- `max_stars`
  型別：`integer | null`
- `sort`
  型別：`"stars" | "forks" | "updated" | null`
- `order`
  型別：`"asc" | "desc" | null`
- `limit`
  型別：`integer`
  範圍：`1` 到 `20`

附加規則：

- 不允許未知欄位
- `keywords` 不可為 `null`
- 未指定欄位必須顯式填 `null`
- 若 `sort` 為 `null`，`order` 也必須為 `null`

### `shared_agent_state` contract

shared state 必須固定包含以下一級欄位：

- `run_id`
- `turn_index`
- `max_turns`
- `user_query`
- `intention_judge`
- `structured_query`
- `validation`
- `compiled_query`
- `execution`
- `control`

其中：

- `turn_index`
  型別：`integer`
  最小值：`1`
- `max_turns`
  型別：`integer`
  固定值：`5`
- `compiled_query`
  型別：`string | null`

### `validation` contract

`validation` 必須包含：

- `is_valid`
  型別：`boolean`
- `errors`
  型別：`string[]`
- `missing_required_fields`
  型別：`string[]`

### `execution` contract

`execution` 必須包含：

- `status`
  型別：`"not_started" | "success" | "no_results" | "failed"`
- `response_status`
  型別：`integer | null`
- `result_count`
  型別：`integer | null`

### `control` contract

`control` 必須包含：

- `next_tool`
  型別：`"intention_judge" | "parse_query" | "validate_query" | "repair_query" | "compile_github_query" | "execute_github_search" | "finalize" | null`
- `should_terminate`
  型別：`boolean`
- `terminate_reason`
  型別：`"ambiguous_query" | "unsupported_intent" | "validation_failed" | "max_turns_exceeded" | "execution_failed" | null`

### `run.json` contract

`run.json` 至少必須包含：

- `session_id`
- `run_id`
- `run_type`
  值只能是 `cli`、`failure_case`、`eval`
- `user_query`
- `model_name`
- `prompt_version`
- `final_outcome`
- `terminate_reason`
- `started_at`
- `ended_at`
- `log_version`

### `turns.jsonl` row contract

`turns.jsonl` 每一列至少必須包含：

- `session_id`
- `run_id`
- `turn_index`
- `tool_name`
- `input_query`
- `intention_status`
- `raw_model_output`
- `parsed_structured_query`
- `validation_result`
- `validation_errors`
- `compiled_query`
- `response_status`
- `final_outcome`
- `next_action`
- `latency_ms`
- `created_at`

### `eval_result` contract

`eval_result.json` 至少必須包含：

- `run_id`
- `session_id`
- `eval_item_id`
- `model_name`
- `ground_truth_structured_query`
- `predicted_structured_query`
- `score`
- `is_correct`
- `created_at`

### `failure_case` contract

每筆 `failure_cases.jsonl` 至少必須包含：

- `id`
- `phase`
- `input_query`
- `expected_behavior`
- `actual_structured_query`
- `actual_compiled_query`
- `execution_outcome`
- `failure_category`
- `severity`
- `run_id`
- `session_id`
- `notes`

### Schema implementation 要求

- 實作時應以 `pydantic` model、JSON Schema，或等價方式定義上述 contracts
- parser、validator、logger、eval runner 不可各自維護不同欄位集合
- 所有正式 artifact 的序列化格式都必須可被 schema 驗證

## 8. Agent Flow 與端到端 Workflow

本專案借鑑 Claude Code 的 turn-based tool-calling loop，但只保留最小必要控制流，不複製其完整通用 agent 複雜度。

核心流程如下：

```text
user query
-> intention_judge
-> if reject: finalize_rejection
-> else enter agent loop
-> parse_query
-> validate_query
-> if invalid: repair_query -> validate_query
-> if valid: compile_github_query
-> execute_github_search
-> finalize
```

### Agent Loop 規則

- agent loop 採 bounded loop，而非無限制 `while (true)`
- 每輪只能執行一個明確 tool action
- 每輪都要更新 shared state
- 每輪都必須留下 turn-level log
- 若 `turn_index >= max_turns` 仍未完成，流程必須安全終止

### 步驟 1：Input

使用者在 CLI 中輸入自然語言字串。

### 步驟 2：`intention_judge`

先判斷這個請求是否屬於 GitHub repository search domain，且是否足夠明確到可以安全進入後續流程。

可能結果：

- `supported`
- `ambiguous`
- `unsupported`

### 步驟 3：Early Termination Check

若為以下情況，直接終止流程，不進入 query compilation：

- 請求與 GitHub repo search 無關
- 請求語意模糊，且在單輪 CLI 架構下無法安全補足

### 步驟 4：`parse_query`

將使用者輸入轉成 `structured_query` 初稿。

### 步驟 5：`validate_query`

驗證 `structured_query` 是否符合 schema 與業務規則。

### 步驟 6：`repair_query`

若 validation 失敗，根據 validator 輸出的錯誤修復 `structured_query`，再重新驗證。

### 步驟 7：`compile_github_query`

當 `structured_query` 合法後，編譯成 GitHub Search API 可用的 query string。

例如：

```text
logistics optimization language:Python stars:>=100 created:>=2024-01-01
```

### 步驟 8：`execute_github_search`

送出 GitHub Search Repositories API request 並取得結果。

### 步驟 9：`finalize`

CLI 輸出內容包含：

- 原始使用者查詢
- `intention_judge` 結果
- structured query JSON
- 編譯後的 GitHub query
- 查詢結果，至少包含 repo name、stars、URL、description
- 若被拒絕或提前終止，則輸出明確終止原因

### 重要說明

`structured_query` 完整且合法，只代表 planning 階段完成；整個 workflow 只有在 API 已執行並得到結果或明確執行狀態後才算完成。

## 8.1 終止規則

以下任一條件成立時，流程必須終止：

1. `intention_judge.intent_status == "unsupported"`
2. `intention_judge.intent_status == "ambiguous"`，且在單輪 CLI 條件下不可安全修復
3. `control.terminate_reason == "validation_failed"`
4. `control.terminate_reason == "max_turns_exceeded"`
5. `execution.status == "success"`
6. `execution.status == "no_results"`
7. `control.terminate_reason == "execution_failed"`

建議使用以下 `terminate_reason` 值：

- `unsupported_intent`
- `ambiguous_query`
- `missing_search_constraints`
- `validation_failed`
- `max_turns_exceeded`
- `execution_failed`

## 9. 系統模組

MVP 應包含以下模組：

1. `cli`
   負責解析命令列輸入並啟動整個流程

2. `agent_loop`
   負責 bounded turn-based workflow、state transition 與終止控制

3. `tool_registry`
   負責註冊可用 tools 與 tool contract

4. `intention_judge`
   判斷請求是否屬於 GitHub repo search domain，是否應提前終止

5. `query_parser`
   將自然語言轉成 `structured_query`

6. `schema_validator`
   驗證 `structured_query` 是否安全且結構正確

7. `query_repairer`
   根據 validator 錯誤修正 `structured_query`

8. `query_compiler`
   將標準化 JSON 轉成 GitHub search syntax

9. `github_client`
   呼叫 GitHub API 並整理回傳結果

10. `renderer`
   負責終端輸出格式

11. `logger`
   保存 debug、agent turns 與 evaluation 所需的 trace

所有執行路徑都必須經過 `logger`，不可只在 `--debug` 模式下輸出。
本專案以 **file-based logging system** 作為 session 與 log 的主要儲存層。

## 9.1 Tool 設計

為了保持可控性與可評測性，MVP 只定義最小必要工具集合。

### `intention_judge`

責任：

- 判斷請求是否屬於 GitHub repository search
- 判斷請求是否足夠明確到可安全進入 parsing 階段
- 決定是否直接終止

輸出至少包含：

- `intent_status`
- `reason`
- `should_terminate`

### `parse_query`

責任：

- 將自然語言轉成 `structured_query` 初稿
- 僅使用支援的 schema 欄位
- 不得虛構 GitHub Search API 不支援的 filter

### `validate_query`

責任：

- 檢查 `structured_query` 是否完整且合法
- 輸出 `is_valid`、`errors`、`missing_required_fields`

### `repair_query`

責任：

- 根據 validation errors 修正 `structured_query`
- 不直接略過 validator

### `compile_github_query`

責任：

- 將合法的 `structured_query` 轉成 GitHub Search API query string

### `execute_github_search`

責任：

- 實際呼叫 GitHub Search Repositories API
- 更新 `execution.status`、`response_status`、`result_count`

### `finalize`

責任：

- 輸出最終 CLI 結果
- 在成功、無結果、拒絕、失敗等情況下，統一產出最終狀態

## 9.2 Tool 執行原則

- 每輪只允許一個 tool action
- 所有 tools 都必須讀寫 shared agent state
- tool 輸出必須是 deterministic schema update，而不是自由文字 side effect
- `finalize` 前必須已有明確 `control` 或 `execution` 狀態
- 不做並行 tool execution，避免增加 debug 與 eval 複雜度

## 9.3 Tool Input / Output Contracts

本節定義每個 tool 的正式 I/O contract。目的在於限制 tool 的責任邊界，避免不同步驟互相覆寫不該修改的 state。

### `intention_judge` contract

輸入：

- `user_query`
- `turn_index`
- `max_turns`

輸出：

- `intention_judge.intent_status`
- `intention_judge.reason`
- `intention_judge.should_terminate`
- `control.next_tool`
- `control.should_terminate`
- `control.terminate_reason`

可修改欄位：

- `intention_judge`
- `control`

不得修改：

- `structured_query`
- `validation`
- `compiled_query`
- `execution`

### `parse_query` contract

輸入：

- `user_query`
- `intention_judge`
- 前一輪 `structured_query`

輸出：

- 完整 `structured_query`
- `control.next_tool`

可修改欄位：

- `structured_query`
- `control.next_tool`

不得修改：

- `validation.is_valid`
- `compiled_query`
- `execution`

### `validate_query` contract

輸入：

- `structured_query`

輸出：

- `validation.is_valid`
- `validation.errors`
- `validation.missing_required_fields`
- `control.next_tool`
- 視情況更新 `control.should_terminate`
- 視情況更新 `control.terminate_reason`

可修改欄位：

- `validation`
- `control`

不得修改：

- `structured_query`
- `compiled_query`
- `execution`

### `repair_query` contract

輸入：

- `user_query`
- `structured_query`
- `validation.errors`
- `validation.missing_required_fields`

輸出：

- 修正後的 `structured_query`
- `control.next_tool`

可修改欄位：

- `structured_query`
- `control.next_tool`

不得修改：

- `execution`
- `compiled_query`
- `validation.is_valid`
  `repair_query` 之後必須重新進 `validate_query`，不可自行宣告合法。

### `compile_github_query` contract

輸入：

- `structured_query`
- `validation.is_valid`

輸出：

- `compiled_query`
- `control.next_tool`

可修改欄位：

- `compiled_query`
- `control.next_tool`

不得修改：

- `structured_query`
- `validation`
- `execution`

### `execute_github_search` contract

輸入：

- `compiled_query`
- `structured_query.limit`

輸出：

- `execution.status`
- `execution.response_status`
- `execution.result_count`
- `control.next_tool`
- 視情況更新 `control.should_terminate`
- 視情況更新 `control.terminate_reason`

可修改欄位：

- `execution`
- `control`

不得修改：

- `structured_query`
- `validation`
- `compiled_query`

### `finalize` contract

輸入：

- 完整 `shared_agent_state`

輸出：

- `final_outcome`
- `terminate_reason`
- `user_facing_summary`

可修改欄位：

- 最終回應 payload
- run-level summary artifact

不得修改：

- 歷史 turn logs
- 任何先前已完成的 tool 結果

### Tool error contract

所有 tools 若執行失敗，必須以結構化錯誤回傳，而不是自由文字：

- `error_code`
- `error_stage`
- `error_message`
- `recoverable`

若 `recoverable = true`，controller 應根據 `error_stage` 決定是否進入下一輪 repair 或 finalize failure。

## 10. CLI 介面定義

範例指令：

```bash
python cli.py "Find Python repos about logistics created after 2023 with more than 100 stars"
```

可選 flags：

```bash
python cli.py "query text" --json
python cli.py "query text" --limit 5
python cli.py "query text" --debug
```

MVP 行為定義如下：

- `--json`：輸出 machine-readable 結果
- `--limit`：若合法，覆蓋模型產生的 limit
- `--debug`：印出中間產物

## 11. Prompt 策略

Prompt 必須分角色設計，至少包含 `intention_judge` 與 `parse_query` 兩類。

### `intention_judge` prompt 要求

- 明確定義本專案只處理 GitHub repository search intent
- 明確區分 `supported`、`ambiguous`、`unsupported`
- 對模糊查詢採保守策略，不可硬猜
- 對非 GitHub query 請求直接標記拒絕

### `parse_query` prompt 要求

- 明確定義 JSON schema
- 明確定義可用欄位與 enum 值
- 明確禁止模型虛構不支援的 filters
- 未指定欄位時回傳 `null`
- 優先採用安全預設值

若可行，parser 應優先使用 structured output。

## 12. Validation 規則

MVP 至少要做到以下驗證：

- 拒絕無法解析的 JSON
- 拒絕未知欄位
- 拒絕不支援的 `sort` 或 `order`
- 拒絕格式錯誤的日期
- 拒絕負數 stars
- 拒絕互相矛盾的範圍，例如 `created_after > created_before`
- 將 `limit` 限制在允許範圍內
- 至少存在一個有效搜尋條件
- 若 `intention_judge` 已判定 `unsupported` 或不可修復的 `ambiguous`，不得繼續 compile / execute

## 13. 錯誤處理

MVP 應明確處理以下錯誤：

- 模型輸出無法解析
- structured query 不合法
- GitHub token 缺失
- GitHub rate limit 或 request failure
- 查無結果

錯誤訊息必須指出失敗階段：

- parse failure
- validation failure
- execution failure

## 13.1 Logging 與 Traceability 規格

本專案要求每一輪執行都留下可追蹤 log，目的是讓系統不只回報最終成功或失敗，也能定位是哪個步驟出問題。
所有 session、turn 與主要事件，必須寫入檔案型 log。

### Logging 適用範圍

以下三類執行都必須產生 log：

- 一般 CLI 查詢執行
- failure case 重跑
- eval pipeline 的每個 model run

### Log 儲存策略

- file-based logs 是 canonical source
- 每次 CLI 執行建立一個 `session`
- 每個 session 底下包含多個 `turn logs`
- failure case 與 eval run 必須能透過 `session_id` / `run_id` 回查完整歷史

### 建議檔案結構

每次執行建立一個獨立 session 目錄，建議結構如下：

```text
artifacts/logs/sessions/{session_id}/
  run.json
  turns.jsonl
  final_state.json
  artifacts/
    turn_01_intention_judge.json
    turn_02_parse_query.json
    turn_03_validate_query.json
```

### 每次對話執行完成後至少應產生的 log 檔案

每次 CLI 對話執行完成後，檔案系統中至少應存在以下內容：

- `run.json`
- `turns.jsonl`
- `final_state.json`
- `artifacts/`

若該次執行屬於 eval pipeline，則額外建議產生：

- `eval_result.json`

### 各檔案用途如下：

- `run.json`
  一次執行的主摘要，包含 `run_id`、`run_type`、`user_query`、`final_outcome`
- `turns.jsonl`
  每輪一筆 turn log，是失敗分析與回放的主要來源
- `final_state.json`
  該次執行結束時的 shared agent state
- `artifacts/`
  存放較大的 payload，例如 raw model output、完整 API response、validator 詳細錯誤
- `eval_result.json`
  僅在 eval run 時產生，保存該題 ground truth、預測結果與 scoring 結果

### Log 層級要求

- 每個 `run` 必須有一筆 run-level 主 log
- agent loop 的每個 `turn` 必須有一筆 turn-level log
- run-level log 與 turn-level log 必須能以 `run_id` 關聯

### 每輪執行必須記錄的欄位

至少要記錄以下欄位：

- `run_id`
- `turn_index`
- `run_type`
  值只能是 `cli`、`failure_case`、`eval`
- `timestamp`
- `input_query`
- `tool_name`
- `model_name`
- `prompt_version`
- `raw_model_output`
- `intention_status`
- `parsed_structured_query`
- `validation_result`
- `validation_errors`
- `compiled_query`
- `request_target`
  例如 GitHub API endpoint
- `request_params`
- `response_status`
- `response_summary`
- `final_outcome`
  例如 `success`、`parse_failure`、`validation_failure`、`execution_failure`
- `latency_ms`
- `notes`

### Session Log 檔案格式

至少建立以下檔案：

1. `run.json`
   紀錄一次完整 CLI / failure case / eval 執行

建議欄位：

- `session_id`
- `run_id`
- `run_type`
- `user_query`
- `model_name`
- `prompt_version`
- `final_outcome`
- `terminate_reason`
- `started_at`
- `ended_at`
- `log_version`
- `metadata`

2. `turns.jsonl`
   紀錄 agent loop 每一輪的執行狀態

每筆建議欄位：

- `session_id`
- `run_id`
- `turn_index`
- `tool_name`
- `input_query`
- `intention_status`
- `raw_model_output`
- `parsed_structured_query`
- `validation_result`
- `validation_errors`
- `compiled_query`
- `request_target`
- `request_params`
- `response_status`
- `response_summary`
- `final_outcome`
- `next_action`
- `latency_ms`
- `created_at`
- `artifact_ref`

3. `final_state.json`
   紀錄每次 session 的最終 shared state

建議欄位：

- `session_id`
- `run_id`
- `state_type`
  值固定為 `final`
- `turn_index`
- `state_payload`
- `created_at`

4. `eval_result.json`
   僅在 eval run 時建立，紀錄該次 evaluation item 的結果與 session 對應

建議欄位：

- `run_id`
- `session_id`
- `eval_item_id`
- `model_name`
- `ground_truth_structured_query`
- `predicted_structured_query`
- `score`
- `is_correct`
- `created_at`

### `artifacts/` 目錄規格

`artifacts/` 目錄用來存放不適合直接內嵌在主 log 中的大型 payload。檔名建議格式如下：

```text
turn_{turn_index}_{tool_name}.json
```

例如：

```text
artifacts/
  turn_01_intention_judge.json
  turn_02_parse_query.json
  turn_03_validate_query.json
  turn_04_execute_github_search.json
```

每個 artifact 檔建議至少包含：

- `session_id`
- `run_id`
- `turn_index`
- `tool_name`
- `input_state`
- `raw_model_output`
- `output_state`
- `state_diff`
- `request_payload`
- `response_payload`
- `notes`

### Log 格式要求

- 檔案格式必須固定，便於分析與聚合
- `turns` 與 `eval results` 建議使用 JSONL
- `run summary` 與 `final state` 建議使用 JSON
- 若 payload 過大，可將完整內容寫入 artifact 檔，主 log 只保留 `artifact_ref`

### Session 查詢能力要求

檔案系統設計至少要支援以下查詢：

- 依 `run_id` 查某次 session 的完整歷史
- 查某次 session 的所有 turns
- 查最後失敗停在哪一輪、哪個 tool
- 查特定 `terminate_reason` 的所有 session
- 查某個 eval item 在不同模型下對應的 sessions

### 使用者失敗回覆與 Log 關聯

當流程因 `max_turns_exceeded` 或其他原因失敗時，CLI 最終回覆必須至少包含：

- `run_id`
- `session_id`
- 失敗輪次摘要
- 最後失敗原因
- 重新提問建議

系統必須能透過 `session_id` 或 `run_id` 從檔案型 log 取回各輪紀錄，生成這份失敗報告。

### Traceability 要求

每筆 log 必須能讓我們回答以下問題：

- 模型原始輸出是什麼
- 是 parse、validation、compile 還是 execution 階段失敗
- 編譯後的 query 是否符合預期
- API 回應是否異常
- 問題是模型理解錯誤，還是後處理規則不足

### 與 Failure / Eval 的關聯要求

- `failure_cases.jsonl` 中的案例必須能對應到實際執行 log
- eval 結果中的每一題、每個模型輸出，也必須能追溯到原始 log
- `run_id` 與 `session_id` 必須可用來串接 CLI、failure case、eval 的分析結果

## 13.2 Canonical 檔案結構

本專案必須定義單一 canonical 檔案結構，目的在於明確 source of truth，避免 dataset、results、logs 在多個目錄各自漂移。

建議專案結構如下：

```text
/
  MVP_SPEC.md
  README.md
  .env.example
  src/
    cli.py
    agent_loop.py
    schemas/
    tools/
    services/
  datasets/
    candidate_dataset.json
    ground_truth_structured_query.json
    eval_dataset_reviewed.json
    failure_cases.jsonl
  specs/
    DATASET_GENERATION_PROMPT.md
    GROUND_TRUTH_GENERATION_PROMPT.md
    HUMAN_REVIEW_CHECKLIST.md
    HUMAN_REVIEW_SUMMARY.md
  scripts/
    generate_eval_dataset.py
    run_eval.py
    run_failure_suite.py
  artifacts/
    logs/
      sessions/
        {session_id}/
    eval/
      {eval_run_id}/
```

### Canonical source 規則

- `datasets/eval_dataset_reviewed.json`
  是正式 eval dataset 的 canonical source
- `datasets/failure_cases.jsonl`
  是正式 failure case dataset 的 canonical source
- `artifacts/logs/sessions/{session_id}/`
  是每次 CLI / failure / eval 單次執行的 canonical session trace
- `artifacts/eval/{eval_run_id}/`
  是整批模型評測結果的 canonical output
- `specs/`
  僅存放 prompt、checklist、review 說明，不作為 runtime source

### 路徑設計原則

- runtime 程式不應依賴 `specs/` 內的文件作為輸入資料
- dataset、logs、eval outputs 必須各有單一 canonical 位置
- 若產生中間產物，必須放在 `artifacts/` 下，不可覆蓋 canonical dataset
- README 中引用的路徑必須與上述結構一致

## 14. 成功標準

若滿足以下條件，即視為 MVP 成功：

1. 使用者可以用一條 CLI 指令完成端到端查詢
2. 工具能為常見 GitHub repo search 請求產生合法 structured JSON
3. 工具能成功執行 GitHub 查詢
4. 工具能回傳可閱讀的結果
5. 對於不支援或格式錯誤的輸入，工具能安全失敗
6. 每次執行都能在檔案型 log 系統中查到對應 session 與 turn logs

## 14.1 作業整體成功標準

若以整份 take-home 的角度來看，除了 MVP 成功之外，還需要達成以下成果：

1. 已記錄並整理 baseline 的 failure cases
2. 已實作至少一輪 hardening，並展示修正前後差異
3. 已建立 30 筆以上的 evaluation dataset
4. 已完成至少 3 個模型的比較，其中包含 open-weight 與 closed-source
5. 所有參與評測的模型在最終版本 pipeline 上都達到 **85% 以上 accuracy**
6. README 已完整說明系統設計、失敗案例、補強方式、模型比較與 learnings

## 15. Failure Case Spec

Part 1 不能只描述 failure cases，必須以可重現、可比較的格式記錄。

### Failure Case Dataset

至少建立一份 `failure_cases.jsonl` 或等價資料檔，每筆資料必須包含：

- `id`
- `phase`
  值只能是 `baseline` 或 `hardened`
- `input_query`
- `expected_behavior`
  說明系統應回傳正確 query、應拒絕執行、或應要求澄清
- `actual_structured_query`
- `actual_compiled_query`
- `execution_outcome`
  例如 `success`、`validation_error`、`api_error`、`wrong_results`
- `failure_category`
- `severity`
  值只能是 `critical`、`major`、`minor`
- `run_id`
  對應到實際執行 log
- `session_id`
  對應檔案系統中的 session 目錄
- `notes`

### Failure Categories

至少使用以下分類：

- `ambiguity`
- `conflicting_constraints`
- `typo_or_noise`
- `multilingual`
- `unsupported_intent`
- `schema_error`
- `constraint_parsing_error`
- `execution_error`

### Break-It 測試最低要求

至少要主動設計並執行以下類型的測試：

- 模糊語意，例如「recent popular repos」
- 衝突條件，例如「after 2024 but before 2023」
- typo 或髒輸入
- 非英文輸入，至少包含中文
- 混合多重限制條件
- 不支援的 intent

### Hardening 驗收要求

Hardening 階段至少要挑選 `critical` 或 `major` 的 failure cases 進行修復，並滿足以下條件：

1. 明確列出 baseline 失敗案例清單
2. 定義至少 5 個高優先級 failure cases 作為 hardening 目標
3. 實作至少一輪修復
4. 以相同測試集重跑，展示修復前後差異
5. 至少修復下列其中 3 類問題：
   - `conflicting_constraints`
   - `typo_or_noise`
   - `multilingual`
   - `constraint_parsing_error`
   - `schema_error`

### 非英文輸入要求

雖然 baseline 以英文為主，但 hardening 後必須至少能正確處理：

- 中文查詢 3 題以上
- 至少另一種非英文語言查詢 2 題以上，建議西班牙文或日文

這些案例必須進入 failure/eval dataset，不可只在 README 口頭描述。

### Failure Analysis 交付要求

README 與結果檔至少要能回答：

- 哪些 failure cases 是 baseline 最常見且最嚴重的
- 哪些問題透過 prompt 可修，哪些需要 validator 或 normalization
- 哪些問題修完後仍無法穩定處理
- 剩餘問題為何困難，是因為語意歧義、API 限制、資料源限制，還是模型限制

## 16. Eval Dataset 與 Scoring Spec

Part 2 的評測規格必須在實作前定義清楚，避免最後 accuracy 不可解釋。

### Eval Dataset 要求

建立至少 30 筆資料，且必須以程式化方式蒐集或生成。

每筆 eval item 必須包含：

- `id`
- `input_query`
- `ground_truth_structured_query`
- `case_type`
- `language`
- `difficulty`
  值只能是 `easy`、`medium`、`hard`
- `notes`

### 資料分布要求

30 筆資料至少要滿足以下分布：

- 10 筆一般查詢
- 8 筆複合限制查詢
- 4 筆模糊或容易誤解的查詢
- 4 筆 typo / noisy 查詢
- 4 筆非英文查詢

同時必須涵蓋：

- `language`
- `created_after` / `created_before`
- `min_stars` / `max_stars`
- `sort` / `order`
- `limit`

### Ground Truth 撰寫規格

每筆 ground truth 必須直接使用本專案的 schema，不可只存 GitHub query string。

Ground truth 必須經過人工檢查，確保：

- 欄位完整且合法
- 未指定的欄位明確填 `null`
- 日期已正規化為 `YYYY-MM-DD`
- `keywords` 已去除無意義停用詞

### 程式化生成要求

資料集不能完全手工臨時撰寫，至少要有一個 generator script 或 template-driven script 負責：

- 建立案例骨架
- 混入不同 constraint 組合
- 產生 typo / multilingual / adversarial 變體
- 匯出成固定格式資料檔

允許人工 review 與修正 ground truth，但資料集來源流程必須可重現。

### Scoring 規格

評測以 normalized exact match 為主，不採自由裁量人工評分。

單題判定正確需同時滿足：

- 所有 schema 欄位都存在
- 所有值在 normalization 後與 ground truth 一致
- 無多餘未知欄位

### Normalization 規則

Scoring 時採以下 normalization：

- `keywords` 視為集合比對，不看順序，但值必須完全一致
- 字串比較採大小寫不敏感
- `null` 與缺欄位不等價，缺欄位視為錯誤
- 日期必須標準化成 `YYYY-MM-DD`
- 數值欄位必須型別正確
- `limit` 若被 CLI flag 覆蓋，eval 時以模型原始輸出為準，不以 runtime override 為準

### Eval Pipeline 輸出要求

每次評測至少產出：

- 每模型整體 accuracy
- 每欄位 accuracy
- 每 case type accuracy
- 每語言 accuracy
- 每題預測結果與 ground truth 對照
- 錯誤分類報告
- 與每題對應的 `run_id` 或 log reference
- 與每題對應的 `session_id`

### Accuracy 驗收標準

最終版本必須達成：

- 至少 3 個模型參與評測
- 所有模型皆達到 **>85% accuracy**
- 若未達標，必須繼續迭代 prompt、normalization 或 validation pipeline

## 17. Model Execution Plan

模型執行計畫必須在 spec 中定死，避免最後才補湊模型名單。

### 模型數量與來源要求

至少使用 3 個模型，且配置如下：

- 至少 1 個 closed-source model
- 至少 1 個 open-weight model
- 第 3 個模型可為 closed-source 或 open-weight，但應與前兩者有明顯差異

### 建議模型組合

第一版明確建議使用以下組合：

- Closed-source（便宜 baseline）: `gpt-4.1-mini`
- Closed-source（中高階主力）: `claude-sonnet-4`
- Open-weight（正式評測模型）: `DeepSeek-R1`

實際 API model ID 或部署來源可依執行環境微調，但最終 README 必須清楚標示版本與供應來源。

### 選型理由

#### `gpt-4.1-mini`

用途定位：

- 作為便宜、快速的 closed-source baseline
- 適合大量重跑 eval 與 prompt iteration

選用理由：

- instruction following 與 structured output 能力夠穩定
- 成本低，適合高頻率評測
- 能代表「成本敏感情境下的可用模型」

#### `claude-sonnet-4`

用途定位：

- 作為中高階 closed-source 主力模型
- 用來代表較高品質的商業模型表現

選用理由：

- 對複雜語意理解與約束解析通常比便宜模型更穩
- 成本顯著低於最頂級模型，但能力仍足夠強
- 適合當作主要的高品質比較對象

#### `DeepSeek-R1`

用途定位：

- 作為 open-weight 正式參賽模型
- 用來滿足題目要求的 open-weight / closed-source 混合評測

選用理由：

- 權重公開，符合 open-weight 要求
- 若使用官方 API，接入成本低，適合在有限時間內完成正式 eval
- 具備強推理能力，較有機會達成 `>85% accuracy`

補充說明：

- 若實際執行走官方 API，README 必須明確標示：
  - model family：`DeepSeek-R1`
  - deployed model id：`deepseek-reasoner`
  - access method：DeepSeek API / hosted inference

### 不建議的模型選型

以下模型策略不建議作為正式評測主組合：

- 過小的 open-weight 模型，例如 7B / 8B instruct
  原因：較難穩定達到 `>85% accuracy`
- 三個都來自同一家且能力差異很小的模型
  原因：比較結果說服力不足
- 過於昂貴的旗艦模型作為必要主力
  原因：對 take-home 成本效益不高

### 執行方式要求

每個模型必須以相同 eval dataset、相同 schema、相同 scoring 規則評測。

允許根據模型能力做 prompt 微調，但必須記錄：

- `model_name`
- `model_provider`
- `prompt_version`
- `run_timestamp`
- `raw_output`
- `parsed_output`
- `score`

### Prompt Iteration 要求

至少保存一輪以上的 prompt/pipeline 迭代記錄，內容包含：

- 初始 prompt 或 pipeline 設計
- 初始主要錯誤模式
- 修正內容
- 修正後結果

### 資源與可行性要求

若 open-weight 模型無法本機執行，可接受以下方式：

- 使用可存取的推論服務
- 使用 Hugging Face Inference API 或等價服務
- 使用本機較小模型，只要能合理說明其代表性

但不得完全省略 open-weight 模型。

## 18. 建議技術棧

為了加快實作速度，建議使用：

- Python
- `Typer` 或 `argparse` 做 CLI
- `pydantic` 做 schema validation
- `httpx` 呼叫 GitHub API
- OpenAI-compatible API client 呼叫模型
- JSONL 儲存 logs 與 eval data

## 19. 交付物

最終專案至少應包含：

- CLI implementation
- README
- 範例 `.env.example`
- file-based log directory convention
- failure case dataset
- evaluation dataset
- evaluation runner
- result summary
- prompt or pipeline iteration record

README 至少必須涵蓋以下內容：

- 系統設計與整體 workflow
- 為什麼選 GitHub search 作為 domain
- baseline failure cases 與測試方式
- hardening 後改善了哪些問題
- 哪些 failure cases 仍未解決，以及為什麼本質上困難
- 為什麼選這些模型做 eval
- 各模型的表現比較與錯誤模式
- 對 eval design 與 ground truth 建立的學習

## 20. 建議開發順序

1. 先定義 JSON schema
2. 先手寫 GitHub query compiler
3. 再做 validator
4. 接上 LLM parser
5. 補上 CLI output formatting
6. 加入 logs
7. 先定義 break-it test plan
8. 跑 baseline 並建立第一版 failure case dataset
9. 完成第一輪 hardening
10. 建立 evaluation dataset 與 scoring script
11. 跑多模型評測並迭代 prompt/pipeline

這個順序的目的，是讓系統保持可 debug，避免 LLM 變成唯一且不可檢驗的黑盒。

## 21. 規格落地階段劃分

為避免把「現在就應該定好的規格」和「要等系統跑起來後才會出現的結果」混在一起，本專案的規格落地分成三個階段：

- 開發前必補：沒有這些規格，implementation 會邊寫邊猜
- 開發中同步落地：隨著功能完成，需要同步生成的結構與 artifact
- 開發後產出：必須依賴 baseline、hardening、eval 實跑結果，無法事前憑空補齊

### 21.1 開發前必補

以下內容必須在正式開始 implementation 前定義完成：

1. Canonical 檔案結構與路徑約定
   至少要定義 dataset、failure cases、session logs、eval outputs、prompts、scripts 的固定路徑與命名規則。

2. Machine-readable schema
   至少包含：
   - `structured_query`
   - `shared_agent_state`
   - `run.json`
   - `turns.jsonl`
   - `final_state.json`
   - `eval_result`
   - `failure_case`

3. Tool I/O contract
   每個 tool 都必須定義：
   - 輸入欄位
   - 輸出欄位
   - 可修改 state 的範圍
   - 錯誤格式

4. Agent state transition 規格
   必須明確定義：
   - 哪些狀態可以呼叫哪些 tool
   - 什麼條件下進下一輪
   - 什麼條件下直接 terminate
   - `last_stage` 與 `next_action` 的合法值

5. `intention_judge` 判定準則
   必須定義 `supported`、`ambiguous`、`unsupported` 的判斷標準，以及哪些 ambiguous case 可以進 repair，哪些必須直接拒絕。

6. GitHub query compiler mapping spec
   必須明確寫出 schema 欄位如何映射成 GitHub Search API 參數與 query qualifiers。

7. Eval scoring contract
   必須先定義：
   - exact match 規則
   - normalization 規則
   - `unsupported` / `ambiguous` / `reject` 類答案如何判定正確

8. Eval runner contract
   至少定義：
   - input dataset
   - 每題執行方式
   - timeout / retry 規則
   - output artifact 格式

9. Config / env spec
   至少包含 GitHub token、模型 API key、default model、`max_turns`、log path 等必要設定。

10. Break-it test plan
    在 baseline 開始前，必須先定義預期要測的 failure 類型與案例來源。這份計畫不是正式 failure case dataset，而是失敗測試藍圖。

### 21.2 開發中同步落地

以下內容應在 implementation 過程中逐步產生，不應拖到最後才補：

1. 可執行的 CLI implementation
2. Shared state 與 tool interface 的實際程式結構
3. File-based session logging
   至少要能寫出：
   - `run.json`
   - `turns.jsonl`
   - `final_state.json`
   - `artifacts/`

4. Dataset generator 或 template-driven generation script
5. Evaluation runner 與 scoring script
6. Baseline prompt / pipeline 版本記錄

### 21.3 開發後產出

以下內容必須等系統能真正執行後，才能依實際結果建立：

1. 正式 `failure_cases.jsonl`
   必須來自 baseline 或 hardened 系統的真實執行結果，不可只靠事前猜測。

2. Hardening 前後比較結果
   必須能展示同一批高優先失敗案例在修復前後的差異。

3. Session logs 與 replay evidence
   必須由實際 CLI / eval run 產生。

4. 多模型 eval 結果
   包含每模型 accuracy、per-field accuracy、per-case-type accuracy、error breakdown。

5. Prompt / pipeline iteration evidence
   必須記錄 baseline 錯誤模式、修正內容、修正後結果。

6. README 的結果分析章節
   包含失敗案例、hardening、模型比較、learned lessons，必須建立在真實實驗結果上。

### 21.4 Failure Case Dataset 與 Break-It Test Plan 的區分

這兩者不可混為一談：

- `break_it_test_plan`
  開發前定義，用來規劃 baseline 要主動測哪些風險類型。

- `failure_cases.jsonl`
  開發後產生，用來記錄系統實際失敗了哪些題、失敗在哪一層、嚴重程度如何，以及是否納入 hardening。

簡單來說：

- 先定義「要測什麼」
- 再用真實執行結果記錄「實際怎麼失敗」

### 21.5 實務優先順序

若目標是讓 spec 可以直接落地成 implementation，優先補齊順序如下：

1. Canonical 檔案結構與命名
2. Machine-readable schemas
3. Tool I/O contracts
4. State transition / termination 規格
5. GitHub compiler mapping spec
6. Rejected-case scoring rules

以上 6 項補齊後，implementation 才能在較少歧義的前提下開始推進。
