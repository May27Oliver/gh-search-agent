# Eval

## 1. Eval Dataset

正式 eval dataset 的 canonical source：

- `datasets/eval_dataset_reviewed.json`

每筆 eval item 至少包含：

- `id`
- `input_query`
- `ground_truth_structured_query`
- `case_type`
- `language`
- `difficulty`
- `notes`

## 2. 資料分布要求

30 筆資料至少滿足：

- 10 筆一般查詢
- 8 筆複合限制查詢
- 4 筆模糊或容易誤解的查詢
- 4 筆 typo / noisy 查詢
- 4 筆非英文查詢

並覆蓋：

- `language`
- `created_after` / `created_before`
- `min_stars` / `max_stars`
- `sort` / `order`
- `limit`

## 3. Ground Truth 規則

- 必須直接使用本專案 schema
- 不可只存 GitHub query string
- 必須人工 review
- 未指定欄位明確填 `null`
- 日期正規化成 `YYYY-MM-DD`
- `keywords` 去除無意義停用詞

## 4. Break-It Test Plan 與 Failure Cases

### 開發前

先定義 `break-it test plan`，列出要主動測的風險類型：

- ambiguity
- conflicting constraints
- typo / noisy input
- multilingual
- unsupported intent

### 開發後

再建立正式：

- `datasets/failure_cases.jsonl`

每筆至少包含：

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

## 5. Failure Categories

- `ambiguity`
- `conflicting_constraints`
- `typo_or_noise`
- `multilingual`
- `unsupported_intent`
- `schema_error`
- `constraint_parsing_error`
- `execution_error`

## 6. Hardening 要求

- 列出 baseline failure cases
- 至少定義 5 個高優先級 hardening 目標
- 至少修復 3 類核心問題
- 以相同測試集重跑，展示 before / after 差異

## 7. Scoring

主分數採：

- normalized exact match

單題正確需同時滿足：

- 所有 schema 欄位都存在
- normalization 後與 ground truth 一致
- 無多餘未知欄位

Normalization 規則：

- `keywords` 視為集合，不看順序
- 字串比對大小寫不敏感
- `null` 與缺欄位不等價
- 日期標準化為 `YYYY-MM-DD`
- 數值欄位型別必須正確
- `limit` 以模型原始輸出為準，不以 CLI override 為準

## 8. Rejected-Case Scoring Rules

對於 `unsupported` / `ambiguous` 類題目，若 ground truth 定義為「應拒絕」：

- 模型必須產生正確的拒絕型 outcome
- 不應硬產生可執行 query
- 被 validator 或 `intention_judge` 正確攔下可視為正確

## 9. Eval Runner Contract

每個 eval 單位：

```text
1 eval item x 1 model = 1 full session run
```

runner 至少要固定：

- input dataset
- model name
- prompt version
- max turns
- timeout
- retry policy
- output artifact format

## 10. Eval Outputs

每次評測至少產出：

- 每模型整體 accuracy
- 每欄位 accuracy
- 每 case type accuracy
- 每語言 accuracy
- 每題預測與 ground truth 對照
- 錯誤分類報告
- 每題對應 `run_id`
- 每題對應 `session_id`
- 每題對應的 session log 路徑

## 11. Model Plan

正式建議組合：

- `gpt-4.1-mini`
- `claude-sonnet-4`
- `DeepSeek-R1`

要求：

- 至少 1 個 closed-source
- 至少 1 個 open-weight
- 所有模型都要在最終 pipeline 上達到 `>85% accuracy`
- 若 `DeepSeek-R1` 透過官方 API 執行，README 必須明確標示：
  - model family：`DeepSeek-R1`
  - deployed model id：`deepseek-reasoner`
  - access method：DeepSeek API / hosted inference

## 12. Iteration Evidence

至少保留一輪以上 iteration record，內容包含：

- 初始 prompt / pipeline
- 初始錯誤模式
- 修正內容
- 修正後結果

## 13. Eval Artifact 位置

建議：

```text
artifacts/eval/{eval_run_id}/
  model_summary.json
  per_item_results.jsonl
  error_analysis.json
```

## 14. Eval Run 檔案結構範例

eval dataset 執行時，每一題、每一個模型都必須視為一次獨立 session run，保留完整可回放 log。

建議結構：

```text
artifacts/
  eval/{eval_run_id}/
    model_summary.json
    per_item_results.jsonl
    error_analysis.json
    models/
      gpt-4.1-mini/
        summary.json
      claude-sonnet-4/
        summary.json
      deepseek-r1/
        summary.json
  logs/
    sessions/
      {session_id_1}/
        run.json
        turns.jsonl
        final_state.json
        eval_result.json
        artifacts/
          turn_01_intention_judge.json
          turn_02_parse_query.json
          turn_03_validate_query.json
      {session_id_2}/
        run.json
        turns.jsonl
        final_state.json
        eval_result.json
        artifacts/
          ...
```

說明：

- `artifacts/eval/{eval_run_id}/` 存放本次 eval 的聚合報表
- `artifacts/logs/sessions/{session_id}/` 存放單題單模型的完整 execution trace
- `per_item_results.jsonl` 每筆都必須能回連到對應的 `run_id`、`session_id` 與 log 路徑
- `eval_result.json` 存放該 session 的題目編號、模型名稱、ground truth、prediction、scoring outcome

`per_item_results.jsonl` 建議至少包含：

- `eval_run_id`
- `eval_item_id`
- `model_name`
- `run_id`
- `session_id`
- `session_log_path`
- `is_correct`
- `score`
- `terminate_reason`
- `predicted_structured_query`
- `ground_truth_structured_query`
