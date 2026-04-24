# Logging

## 1. 目標

logging system 的目的是讓系統不只回報最終成功或失敗，也能回答：

- 哪一輪失敗
- 哪個 tool 出錯
- 模型原始輸出是什麼
- 是 parse / validation / compile / execution 哪一層出問題

## 2. Canonical File Structure

```text
/
  artifacts/
    logs/
      sessions/
        {session_id}/
          run.json
          turns.jsonl
          final_state.json
          artifacts/
            turn_01_intention_judge.json
            turn_02_parse_query.json
            turn_03_validate_query.json
    eval/
      {eval_run_id}/
```

## 3. Canonical Source Rules

- `artifacts/logs/sessions/{session_id}/`
  是單次執行的 canonical session trace
- `artifacts/eval/{eval_run_id}/`
  是整批 eval 的 canonical output
- 中間產物放 `artifacts/`，不可覆蓋 dataset canonical source

## 4. Logging Scope

以下都必須產生 log：

- 一般 CLI 查詢
- failure case 重跑
- eval pipeline 中每個 model run

## 5. 必要檔案

每次執行完成後至少應產生：

- `run.json`
- `turns.jsonl`
- `final_state.json`
- `artifacts/`

若為 eval run，額外產生：

- `eval_result.json`

## 6. 檔案用途

### `run.json`

一次執行主摘要，包含：

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

### `turns.jsonl`

每輪一筆，包含：

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

### `final_state.json`

儲存整次 session 結束時的完整 shared state。

### `artifacts/turn_XX_<tool>.json`

儲存較大 payload：

- `input_state`
- `raw_model_output`
- `output_state`
- `state_diff`
- `request_payload`
- `response_payload`
- `notes`

### `eval_result.json`

eval 單題結果：

- `eval_item_id`
- `model_name`
- `ground_truth_structured_query`
- `predicted_structured_query`
- `score`
- `is_correct`

## 7. Traceability

系統必須能：

- 依 `run_id` 查完整 session 歷史
- 查所有 turns
- 查最後停在哪一輪、哪個 tool
- 查特定 `terminate_reason` 的 sessions
- 查某個 eval item 在不同模型下對應的 sessions

## 8. 使用者失敗回覆要求

當失敗時，CLI 回覆至少包含：

- `run_id`
- `session_id`
- 失敗輪次摘要
- 最後失敗原因
- 重新提問建議

若為 `max_turns_exceeded`，應列出每輪摘要，而不是只回一個錯誤碼。
