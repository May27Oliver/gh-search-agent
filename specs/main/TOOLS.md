# Tools

## 1. Tool Set

- `intention_judge`
- `parse_query`
- `validate_query`
- `repair_query`
- `compile_github_query`
- `execute_github_search`
- `finalize`

## 2. 責任分工

### `intention_judge`

- 判斷請求是否屬於 GitHub repository search
- 判斷是否足夠明確
- 決定是否直接終止

### `parse_query`

- 將自然語言轉成 `structured_query` 初稿
- 只能使用支援的 schema 欄位

### `validate_query`

- 檢查 `structured_query` 結構是否合法
- 檢查欄位值、型別、範圍、衝突條件

### `repair_query`

- 根據 validation errors 修正 `structured_query`
- 不可跳過 re-validation

### `compile_github_query`

- 將合法 `structured_query` 轉為 GitHub Search API query string

### `execute_github_search`

- 呼叫 GitHub Search Repositories API
- 更新 execution 狀態

### `finalize`

- 產生最終 CLI 回應
- 處理 success / no_results / rejection / failure

## 3. I/O Contracts

### `intention_judge`

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

### `parse_query`

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

- `validation`
- `compiled_query`
- `execution`

### `validate_query`

輸入：

- `structured_query`

輸出：

- `validation.is_valid`
- `validation.errors`
- `validation.missing_required_fields`
- `control.next_tool`
- 必要時更新 `control.should_terminate`
- 必要時更新 `control.terminate_reason`

可修改欄位：

- `validation`
- `control`

不得修改：

- `structured_query`
- `compiled_query`
- `execution`

### `repair_query`

輸入：

- `user_query`
- `structured_query`
- `validation.errors`
- `validation.missing_required_fields`

輸出：

- 修正後 `structured_query`
- `control.next_tool`

可修改欄位：

- `structured_query`
- `control.next_tool`

不得修改：

- `compiled_query`
- `execution`
- `validation.is_valid`

### `compile_github_query`

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

### `execute_github_search`

輸入：

- `compiled_query`
- `structured_query.limit`

輸出：

- `execution.status`
- `execution.response_status`
- `execution.result_count`
- `control.next_tool`
- 必要時更新 `control.should_terminate`
- 必要時更新 `control.terminate_reason`

可修改欄位：

- `execution`
- `control`

不得修改：

- `structured_query`
- `validation`
- `compiled_query`

### `finalize`

輸入：

- 完整 `shared_agent_state`

輸出：

- `final_outcome`
- `terminate_reason`
- `user_facing_summary`

## 4. Tool Error Contract

所有 tools 若執行失敗，必須回傳結構化錯誤：

- `error_code`
- `error_stage`
- `error_message`
- `recoverable`

## 5. State Transition

基本轉移如下：

```text
intention_judge
-> parse_query
-> validate_query
-> repair_query (if invalid)
-> validate_query
-> compile_github_query
-> execute_github_search
-> finalize
```

規則：

- 每輪只能執行一個 tool
- `repair_query` 之後必須回到 `validate_query`
- `validation.is_valid = true` 前不可 compile
- `compiled_query` 存在前不可 execute
- 任一 termination condition 成立時必須進 `finalize`

## 6. Termination Rules

終止條件：

- `unsupported_intent`
- `ambiguous_query`
- `validation_failed`
- `max_turns_exceeded`
- `execution_failed`
- `execution.status = success`
- `execution.status = no_results`

## 7. `intention_judge` 判準

### `supported`

- 查詢明確屬於 GitHub repository search
- 可映射到現有 schema

### `ambiguous`

- 屬於 GitHub repository search
- 但缺少足夠約束，無法安全推定

### `unsupported`

- 非 GitHub repository search
- 或需要目前 schema 無法表達的能力

## 8. GitHub Compiler Mapping

- `keywords`
  以空白 join 到主 query
- `language`
  映射為 `language:<value>`
- `created_after`
  映射為 `created:>=YYYY-MM-DD`
- `created_before`
  映射為 `created:<=YYYY-MM-DD`
- `min_stars`
  映射為 `stars:>=N`
- `max_stars`
  映射為 `stars:<=N`
- `sort`
  映射到 GitHub API `sort`
- `order`
  映射到 GitHub API `order`
- `limit`
  映射到 `per_page`

## 9. Validation Rules

- JSON 可解析
- 無未知欄位
- enum 合法
- 日期格式正確
- stars 非負數
- `created_after <= created_before`
- `min_stars <= max_stars`
- 至少存在一個有效搜尋條件
- 若 `intention_judge` 已拒絕，不得繼續 compile / execute
