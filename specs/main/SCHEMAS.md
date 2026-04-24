# Schemas

## 1. `structured_query`

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
  "limit": 10
}
```

欄位 contract：

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

規則：

- 不允許未知欄位
- `keywords` 不可為 `null`
- 所有欄位都必須存在
- 未指定值用 `null`
- 若 `sort = null`，則 `order` 也必須為 `null`

## 2. `shared_agent_state`

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
  "structured_query": {},
  "validation": {
    "is_valid": false,
    "errors": [],
    "missing_required_fields": []
  },
  "compiled_query": null,
  "execution": {
    "status": "not_started",
    "response_status": null,
    "result_count": null
  },
  "control": {
    "next_tool": "parse_query",
    "should_terminate": false,
    "terminate_reason": null
  }
}
```

一級欄位必須包含：

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

## 3. `intention_judge`

- `intent_status`
  型別：`"supported" | "ambiguous" | "unsupported"`
- `reason`
  型別：`string | null`
- `should_terminate`
  型別：`boolean`

## 4. `validation`

- `is_valid`
  型別：`boolean`
- `errors`
  型別：`string[]`
- `missing_required_fields`
  型別：`string[]`

## 5. `execution`

- `status`
  型別：`"not_started" | "success" | "no_results" | "failed"`
- `response_status`
  型別：`integer | null`
- `result_count`
  型別：`integer | null`

## 6. `control`

- `next_tool`
  型別：`"intention_judge" | "parse_query" | "validate_query" | "repair_query" | "compile_github_query" | "execute_github_search" | "finalize" | null`
- `should_terminate`
  型別：`boolean`
- `terminate_reason`
  型別：`"ambiguous_query" | "unsupported_intent" | "validation_failed" | "max_turns_exceeded" | "execution_failed" | null`

## 7. `run.json`

至少包含：

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

## 8. `turns.jsonl`

每列至少包含：

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

## 9. `final_state.json`

- `session_id`
- `run_id`
- `state_type`
  固定值：`final`
- `turn_index`
- `state_payload`
- `created_at`

## 10. `eval_result.json`

- `run_id`
- `session_id`
- `eval_item_id`
- `model_name`
- `ground_truth_structured_query`
- `predicted_structured_query`
- `score`
- `is_correct`
- `created_at`

## 11. `failure_cases.jsonl`

- `id`
- `phase`
  值只能是 `baseline` 或 `hardened`
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

## 12. 實作要求

- 用 `pydantic` model、JSON Schema 或等價方式定義上述 contracts
- parser、validator、logger、eval runner 不可各自維護不同欄位集合
- 所有正式 artifact 都必須可被 schema 驗證
