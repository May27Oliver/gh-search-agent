# Phase 1 Plan

## 1. 目標

Phase 1 的目標不是一次做完整產品，而是先做出一條最小可跑、可觀測、可驗證的閉環：

```text
CLI -> agent loop -> parse / validate / compile -> GitHub API -> result -> logs
```

Phase 1 完成時，系統應具備：

- 可執行的 CLI 入口
- 穩定的 shared state 與 schema models
- 可測試的 GitHub query compiler
- 可呼叫的 GitHub API client
- 可回放的 file-based session logs
- bounded agent loop
- 可跑通的 smoke eval

## 1.1 Phase 1 固定技術決策

為避免 Phase 1 實作時持續搖擺，先固定以下決策：

- 實作語言：`Python`
- schema / validation library：`pydantic`
- Phase 1 smoke 與 parser 開發模型：`gpt-4.1-mini`
- Phase 1 smoke eval 預設只跑 `1` 個模型

說明：

- `Python + pydantic` 作為 Phase 1 的 canonical implementation stack
- 三模型正式比較仍保留到 baseline / final submission 階段
- Phase 1 的目標是先跑通最小閉環，不在此階段同時接三個模型

## 2. Phase 1 驗收標準

必須同時滿足：

- CLI 可以成功啟動並顯示 help
- 至少 1 題正常題可跑完整流程並成功回傳結果
- 至少 1 題拒絕題可被正確拒絕
- 每次 run 都會產生 `run.json`、`turns.jsonl`、`final_state.json`
- smoke eval 可至少跑 3 題，且每題都可回查對應 logs

## 3. 任務拆解

### 3.1 建立專案骨架

目的：

- 定義 `src/` 目錄結構
- 建立 CLI 入口
- 建立基本 config loading

預期交付物：

- `src/` 基本模組
- CLI 入口檔
- `.env.example`

應參考文件：

- [MAIN_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/MAIN_SPEC.md:1)
- [LOGGING.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/LOGGING.md:1)

驗證方式：

- 執行 `--help` 可成功顯示 usage
- CLI 啟動時不出現 import error
- config 缺漏時會給出明確錯誤訊息

若驗證失敗，調整方式：

- 先不要接真實模型與 GitHub API
- 先以最小 dummy command 跑通 CLI 入口
- 優先修正目錄與 import 問題

### 3.2 落地 Schema Models

目的：

- 將文字規格實作成 machine-readable contracts

預期交付物：

- `StructuredQuery`
- `SharedAgentState`
- `RunLog`
- `TurnLog`
- `EvalResult`

應參考文件：

- [SCHEMAS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/SCHEMAS.md:1)
- [MVP_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/target/MVP_SPEC.md:1)

驗證方式：

- 至少 3 到 5 組 sample JSON 可成功 parse
- 非法 enum、錯誤型別、缺必填欄位時會明確報錯
- `null`、空值、必填欄位行為符合 spec

若驗證失敗，調整方式：

- 先收斂到 MVP 必要欄位
- 對模糊欄位增加 enum 或 validator
- 暫時不擴充 optional metadata

### 3.3 做 GitHub Query Compiler

目的：

- 將 `structured_query` 穩定轉成 GitHub Search API 可執行參數

預期交付物：

- `compile_github_query(structured_query)`

應參考文件：

- [TOOLS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/TOOLS.md:1)
- [SCHEMAS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/SCHEMAS.md:1)

驗證方式：

- 固定輸入可得到預期 query string
- `language`、日期、stars、`sort/order` 都能正確映射
- 至少寫 10 個 compiler unit tests

若驗證失敗，調整方式：

- 先凍結 mapping 規則
- 先只支援 MVP 欄位
- 對日期與 stars 邊界採固定單一規則，不做多版本兼容

### 3.4 做 GitHub Client

目的：

- 讓 compiled query 能實際呼叫 GitHub API 並回傳最小必要結果

預期交付物：

- `search_repositories(query, sort, order, per_page)`
- response normalization

應參考文件：

- [MAIN_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/MAIN_SPEC.md:1)
- [TOOLS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/TOOLS.md:1)

驗證方式：

- 用手寫 query 可成功回傳 200
- 能解析最小必要欄位，例如 repo name、url、stars、language
- 401、422、rate limit 有穩定錯誤處理

若驗證失敗，調整方式：

- 先只實作單次 GET request
- 降低 response parsing 範圍，只保留 MVP 欄位
- 分離 transport error 與 logical error

### 3.5 做 Logging System

目的：

- 確保每次 run 都有可回放 trace

預期交付物：

- `run.json`
- `turns.jsonl`
- `final_state.json`
- `artifacts/`

應參考文件：

- [LOGGING.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/LOGGING.md:1)
- [EVAL.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL.md:1)

驗證方式：

- 跑一次 dummy session 後，目錄與檔案完整生成
- `session_id`、`run_id` 可一致回查
- 可從 `turns.jsonl` 還原每輪 tool 與結果

若驗證失敗，調整方式：

- 先只記最小必要欄位
- 不先追求完整 telemetry
- 先保證單輪 append 正確，再擴成多輪

### 3.6 做單輪 Parser 與 Validator

目的：

- 先做最小可用的 `intention_judge`、`parse_query`、`validate_query`
- Phase 1 僅以單一模型驗證 parser 行為

預期交付物：

- `intention_judge`
- `parse_query`
- `validate_query`
- `gpt-4.1-mini` parser prompt / response contract

應參考文件：

- [TOOLS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/TOOLS.md:1)
- [SCHEMAS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/SCHEMAS.md:1)
- [datasets/eval_dataset_reviewed.json](/Users/chenweiqi/Documents/interview/gofreight/datasets/eval_dataset_reviewed.json:1)

驗證方式：

- 至少 10 題手工 sample 中，7 題以上可產出合法 `structured_query`
- `unsupported` / `ambiguous` case 可正確拒絕
- validation errors 格式穩定，可供後續 log 與 scorer 使用

若驗證失敗，調整方式：

- 限制模型輸出為固定 JSON schema
- 降低 parser 自由度，減少自由生成文字
- 優先使用 strict schema + few-shot，而不是增加 tool 複雜度
- 不在此階段切換多模型，先把單模型 parser 跑穩

### 3.7 做 Bounded Agent Loop

目的：

- 將 parser、validator、compiler、GitHub client 串成最多 5 輪的控制流

預期交付物：

- loop controller
- state transition logic
- termination handling
- failure reporting

應參考文件：

- [TOOLS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/TOOLS.md:1)
- [LOGGING.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/LOGGING.md:1)
- [MAIN_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/MAIN_SPEC.md:1)

驗證方式：

- 正常題能在 5 輪內完成
- 模糊題能在 5 輪內安全拒絕
- 超過 `max_turns` 時會輸出逐輪摘要與失敗原因

若驗證失敗，調整方式：

- 先減少 tool 數量
- 若 `repair_query` 不穩，先讓 invalid case 直接 terminate
- 優先保證 deterministic flow，再補 agent 智能性

### 3.8 做 Phase 1 Smoke Eval

目的：

- 驗證整條 pipeline 在小樣本下可測、可評分、可回放

預期交付物：

- 3 到 5 題 smoke dataset
- smoke runner
- per-item logs
- 簡易 score summary
- `gpt-4.1-mini` smoke run summary

應參考文件：

- [EVAL.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL.md:1)
- [EVAL_EXECUTION_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL_EXECUTION_SPEC.md:1)
- [datasets/eval_dataset_reviewed.json](/Users/chenweiqi/Documents/interview/gofreight/datasets/eval_dataset_reviewed.json:1)
- [specs/datasets/HUMAN_REVIEW_SUMMARY.md](/Users/chenweiqi/Documents/interview/gofreight/specs/datasets/HUMAN_REVIEW_SUMMARY.md:1)

驗證方式：

- 每題都會產生 session logs
- scorer 能正常比對 ground truth
- 至少能分辨：正確、拒絕正確、validation fail、`max_turns_exceeded`
- smoke eval 預設只跑 `gpt-4.1-mini` 一個模型

若驗證失敗，調整方式：

- 維持只跑 `gpt-4.1-mini` 一個模型
- 先只跑 3 題
- 優先修 runner、scorer、logs 的整合，不急著擴充 dataset 規模

## 4. 建議開發順序

建議順序如下：

1. 建立專案骨架
2. 落地 schema models
3. 做 GitHub query compiler
4. 做 GitHub client
5. 做 logging system
6. 做單輪 parser 與 validator
7. 做 bounded agent loop
8. 做 Phase 1 smoke eval

## 5. Phase 1 完成後才能進入 Phase 2 的條件

進入 Phase 2 之前，至少要滿足：

- smoke eval 可穩定重跑
- session logs 可逐題回放
- scorer 已能穩定區分 exact match 與 rejected case
- 至少一個模型可完成端到端正常題流程

若這些條件尚未達成，不應直接進入 full eval 或 hardening 階段。
