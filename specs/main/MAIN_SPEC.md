# Main Spec

## 1. 目標

本專案要完成一個 CLI 工具，將自然語言 GitHub repository search 查詢轉成結構化查詢，實際執行 GitHub Search API，並回傳結果。

同時，專案必須支援：

- break-it 測試
- hardening
- multi-model evaluation
- session-level traceability

## 2. 作業對齊目標

### Part 1

- 接受自然語言輸入
- 產生合法 structured query
- 編譯成 GitHub Search API query
- 實際執行並回傳結果
- 主動記錄 failure cases
- 修復最重要的 failure cases
- README 解釋剩餘 failure cases 為何困難

### Part 2

- 建立至少 30 筆 eval dataset
- 每題有人工 review 過的 ground truth structured query
- 至少評估 3 個模型
- 模型組合同時包含 open-weight 與 closed-source
- 持續迭代 prompt / pipeline，直到所有參與評測模型都達到 `>85% accuracy`

## 3. Domain 與範圍

### Domain

- GitHub repository search

### MVP 內含

- `keywords`
- `language`
- `created_after`
- `created_before`
- `min_stars`
- `max_stars`
- `sort`
- `order`
- `limit`

### MVP 不含

- GitHub issues / PR / users / code search
- 多輪澄清對話
- 通用 agent 平台
- 並行 tool execution

## 4. 核心流程

```text
user query
-> intention_judge
-> if reject: finalize_rejection
-> parse_query
-> validate_query
-> if invalid: repair_query -> validate_query
-> compile_github_query
-> execute_github_search
-> finalize
```

## 5. Agent Loop 原則

- bounded turn-based loop
- 每輪只允許一個 tool action
- 所有 tools 都讀寫同一份 shared state
- 每輪都要留下 turn-level log
- `max_turns = 5`

## 6. 終止規則

流程必須在以下任一情況終止：

1. `unsupported_intent`
2. `ambiguous_query` 且不可安全修復
3. `validation_failed`
4. `max_turns_exceeded`
5. `execution_failed`
6. `execution.status == success`
7. `execution.status == no_results`

## 7. 實作模組

- `cli`
- `agent_loop`
- `tool_registry`
- `intention_judge`
- `query_parser`
- `schema_validator`
- `query_repairer`
- `query_compiler`
- `github_client`
- `renderer`
- `logger`

## 8. 成功標準

### MVP 成功

- 一條 CLI 指令可完成端到端查詢
- 能產生合法 structured query
- 能成功執行 GitHub 查詢
- 能回傳可閱讀結果
- 對不支援或錯誤輸入能安全失敗
- 每次執行都能查到 session 與 turn logs

### 作業整體成功

- 已記錄 baseline failure cases
- 已完成至少一輪 hardening
- 已建立 30 題以上 eval dataset
- 已完成至少 3 個模型比較
- 所有模型都達到 `>85% accuracy`
- README 完整說明系統設計、failure cases、hardening、model comparison、learnings

## 9. 交付物

- CLI implementation
- README
- `.env.example`
- file-based log convention
- failure case dataset
- evaluation dataset
- evaluation runner
- result summary
- prompt / pipeline iteration record

## 10. 開發順序

1. 定義 schema
2. 寫 GitHub query compiler
3. 寫 validator
4. 接 parser
5. 做 CLI output
6. 加 logger
7. 定義 break-it test plan
8. 跑 baseline 並產生第一版 failure case dataset
9. 完成 hardening
10. 建 eval dataset 與 scoring script
11. 跑多模型評測與 iteration
