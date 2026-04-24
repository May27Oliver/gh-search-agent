# Eval Execution Spec

## 1. 目的

本文件定義本專案的正式測分規劃，目的是讓 evaluation 在開發前就可落地，而不是等系統完成後再臨時拼湊。

本文件回答四個問題：

- eval runner 怎麼跑
- scorer 怎麼算
- 三個模型怎麼以一致方式接入
- 最終如何證明所有模型都達到 `>85% accuracy`

## 2. 核心原則

- primary score 必須是 deterministic，不以 LLM judge 當主分數
- 每題每模型都必須保留完整 session trace
- runner、scorer、model adapter 要彼此解耦
- baseline、regression、final submission 要使用同一套 scoring contract
- transport retry 與 logical retry 必須分開處理

## 3. 評測分層

本專案的 eval 分成三層：

### 3.1 Primary Evaluation

用正式 dataset 跑完整 agent pipeline，將最終 `structured_query` 與 ground truth 做 deterministic comparison。

這是正式分數來源，也是 README 與最終交付物應採用的 canonical score。

### 3.2 System Evaluation

記錄系統行為指標，用於診斷而不是主排名：

- execution success rate
- validation pass rate
- max-turns-exceeded rate
- average turns per item
- average latency per item
- average token usage per item
- average cost per item

### 3.3 Error Analysis

將錯誤按不同維度切分：

- field-level mismatch
- case type
- language
- terminate reason
- tool stage

## 4. Canonical Inputs

正式評測輸入如下：

- dataset: `datasets/eval_dataset_reviewed.json`
- failure reference: `datasets/failure_cases.jsonl`
- prompt version: 由 runner 顯式帶入，且寫入 artifacts
- model list: 由 runner 顯式帶入，且寫入 artifacts

若有 smoke dataset 或 regression subset，應額外放在：

- `datasets/smoke_eval_dataset.json`
- `datasets/regression_eval_dataset.json`

若這兩份資料尚未建立，不得替換正式 eval dataset 的 canonical 地位。

## 5. Runner Modes

eval runner 至少支援以下模式：

### 5.1 Smoke

目的：

- 驗證 runner、model adapter、logging、artifact paths 是否正常

規模：

- 3 到 5 題
- 覆蓋 1 題正常題、1 題複合限制題、1 題拒絕題
- 預設只跑 `1` 個模型
- 預設模型為 `gpt-4.1-mini`

### 5.2 Baseline

目的：

- 取得初始模型表現
- 建立第一版 failure case dataset

規模：

- 正式 30 題 dataset

### 5.3 Regression

目的：

- 驗證 hardening 後是否修復既有高優先問題

規模：

- 以 failure-driven subset 為主
- 至少包含所有 P0 / P1 failure cases

### 5.4 Final Submission

目的：

- 產生最終提交分數與 artifacts

規模：

- 正式 30 題 dataset
- 全部正式模型

## 6. Runner Contract

每個 eval 單位：

```text
1 eval item x 1 model = 1 full session run
```

runner 必須固定並記錄以下參數：

- `eval_run_id`
- `dataset_path`
- `model_name`
- `provider_name`
- `prompt_version`
- `system_version`
- `temperature`
- `max_tokens`
- `max_turns`
- `timeout_seconds`
- `transport_retry_policy`
- `logical_retry_policy`

建議預設值：

- `temperature = 0`
- `max_turns = 5`
- `logical_retry_policy = none`

Smoke mode 額外預設：

- `model_count = 1`
- `model_name = gpt-4.1-mini`

`logical_retry_policy = none` 的目的，是避免為了拿高分而在 eval 階段偷偷加入多次重試，導致分數失真。

## 7. Transport Retry 與 Logical Retry

必須明確區分：

- transport retry: 針對 429、5xx、暫時性網路錯誤
- logical retry: 因模型輸出不佳而再問一次

規則：

- transport retry 可允許有限次數，例如 2 次
- logical retry 在正式 eval 中預設禁止
- 若未來要比較「有 retry pipeline」，必須視為新 system version，單獨記錄與比較

## 8. Model Adapter Contract

每個模型 provider 必須透過統一 adapter 介面接入。

adapter 至少要實作：

- `generate_structured_response(request) -> response`
- `get_model_metadata() -> metadata`

`request` 至少包含：

- `model_name`
- `messages`
- `system_prompt`
- `response_schema`
- `temperature`
- `max_tokens`
- `timeout_seconds`

`response` 至少包含：

- `raw_text`
- `parsed_json`
- `finish_reason`
- `usage`
- `latency_ms`
- `provider_response_id`
- `transport_error`

禁止讓上層 runner 依賴不同 provider 的原生回傳格式。

## 9. 單題執行流程

每題每模型的標準流程如下：

1. 讀取 eval item
2. 建立 `session_id`、`run_id`
3. 啟動 agent loop
4. 寫出每輪 session logs
5. 取得 final outcome
6. 執行 scorer
7. 寫出 `eval_result.json`
8. 將 summary append 到 `per_item_results.jsonl`

若單題失敗：

- 仍必須產出 session logs
- 仍必須產出 `eval_result.json`
- 不得直接跳過

## 10. Scorer Contract

scorer 是獨立元件，不可直接耦合到 agent loop 內。

輸入至少包含：

- `eval_item`
- `predicted_structured_query`
- `final_outcome`
- `terminate_reason`
- `ground_truth_structured_query`
- `session_id`
- `run_id`

輸出至少包含：

- `is_correct`
- `score`
- `score_type`
- `field_results`
- `mismatch_reasons`
- `terminate_reason`

主分數規則：

- `score_type = normalized_exact_match`
- 完全一致記為 `1`
- 否則記為 `0`

輔助分數規則：

- `field_results` 顯示每個欄位是否正確
- 可額外產出 `field_accuracy` 報表，但不得取代主分數

## 11. Rejected-Case Scoring

若 ground truth 定義該題應拒絕：

- `intention_judge` 正確拒絕可算對
- validator 正確攔下且最終 outcome 為拒絕可算對
- 若模型硬產生可執行 query，直接算錯

對 rejected case，`predicted_structured_query` 可為 `null`，但必須同時滿足：

- `final_outcome = rejected`
- `terminate_reason` 符合 ground truth 預期類型

## 12. Metrics

runner 必須至少產出以下 metrics：

### 12.1 Primary Metrics

- overall accuracy
- per-model accuracy
- per-case-type accuracy
- per-language accuracy
- per-difficulty accuracy

### 12.2 Secondary Metrics

- validation pass rate
- execution success rate
- no-result rate
- rejected-as-expected rate
- max-turns-exceeded rate
- average turns per item
- average latency per item
- average prompt tokens per item
- average completion tokens per item
- average cost per item

### 12.3 Diagnostic Metrics

- field-level accuracy
- tool-stage failure distribution
- terminate reason distribution
- schema mismatch distribution

## 13. Thresholds 與 Gating

最終 submission 的 gating criteria：

- 所有正式模型 `overall accuracy > 85%`
- 無任一模型因系統錯誤導致大量空跑或缺失 logs
- 每題都可回查對應 `run_id` / `session_id`

建議內部 gate：

- smoke run 必須 100% 成功產出 artifacts
- baseline run 後必須能形成第一版 failure taxonomy
- final submission run 不得有遺失的 `eval_result.json`

## 14. Artifacts

本次 eval 的 canonical outputs：

```text
artifacts/eval/{eval_run_id}/
  run_config.json
  model_summary.json
  per_item_results.jsonl
  error_analysis.json
  models/
    gpt-4.1-mini/
      summary.json
      per_item_results.jsonl
    claude-sonnet-4/
      summary.json
      per_item_results.jsonl
    deepseek-r1/
      summary.json
      per_item_results.jsonl
```

單題 session logs 仍放在：

```text
artifacts/logs/sessions/{session_id}/
```

`run_config.json` 至少要包含：

- dataset path
- model list
- prompt version
- system version
- runner mode
- scoring version
- start / end timestamps

## 15. Iteration Protocol

每一輪 prompt 或 pipeline 調整，都必須形成一個新的 `system_version`。

至少保留：

- baseline run
- 至少一輪 hardening 後 run
- final submission run

每輪都要能回答：

- 改了什麼
- 目標修哪類錯誤
- 哪些指標改善
- 哪些問題仍未解

## 16. 外部 Eval 工具策略

本專案的 canonical eval tool 為自研 deterministic runner + scorer。

原因：

- 任務是 fixed-schema exact match，適合 deterministic scoring
- tool-calling agent 已有完整 session logs，不需要先依賴外部平台才能分析
- 面試專案應避免將主分數依賴綁在第三方平台

外部工具可作為 optional 輔助層，例如：

- trace visualization
- judge-based qualitative analysis
- regression dashboard

但不得取代 canonical scoring。

## 17. 實作優先順序

建議按以下順序落地：

1. 先實作 scorer normalization 與 exact-match comparison
2. 再實作 model adapter abstraction
3. 再實作 smoke runner
4. 確保每題 session logging 正常
5. 再擴成 baseline / regression / final submission modes
6. 最後補 model summary 與 error analysis 報表
