# llm — 導覽

這個資料夾負責「跟大型語言模型（LLM）講話」這件事。Phase 2 起支援三個 provider：OpenAI、Anthropic、DeepSeek — 整個專案只透過一個抽象介面 `LLMJsonCall` 呼叫 LLM，所以 agent 跟 tool 都不用動。

## 先看哪個

1. [`__init__.py`](./__init__.py) — 定義：
   - **`LLMJsonCall`** — 函數簽名 `(system_prompt, user_message, response_schema) -> LLMResponse`。
   - **`LLMResponse`** — frozen dataclass。Phase 2 之後欄位變多，但原本的 `raw_text` / `parsed` 仍是 tool 會讀的主要資料；新增的 metadata（`provider_name` / `model_name` / `usage` / `latency_ms` / `finish_reason` / `provider_response_id` / `transport_error`）給 logger / matrix aggregator 用。
2. [`factory.py`](./factory.py) — 唯一的 provider 路由入口：
   - `make_llm(model_name, ...)` 根據 canonical 名稱回傳 `LLMBinding`。
   - `canonical_model_name(...)` / `provider_for(...)` 只接受這三個 canonical name（大小寫不敏感）：`gpt-4.1-mini`、`claude-sonnet-4`、`deepseek-r1`。
   - `SUPPORTED_MODELS` / `PROVIDER_BY_MODEL` 是擴充 provider / model 時要改的地方。**目前刻意只 whitelist 三個有 prompt appendix、測試、eval 紀錄的 canonical model：`gpt-4.1-mini`、`claude-sonnet-4`、`deepseek-r1`。**
3. Provider adapters（都是 `LLMJsonCall` 實作、介面一致）：
   - [`openai_client.py`](./openai_client.py) — `make_openai_llm(api_key, model, ...)`，用 `response_format=json_schema`。
   - [`anthropic_client.py`](./anthropic_client.py) — `make_anthropic_llm(api_key, model, ...)`，用 forced `tool_use` 產出 structured JSON。
   - [`deepseek_client.py`](./deepseek_client.py) — `make_deepseek_llm(api_key, endpoint_url, model, ...)`，預設走 DeepSeek 官方 API，也可改成 OpenAI-compatible gateway。
4. [`prompts.py`](./prompts.py) — `load_prompt_bundle(name, model)` 讀 `prompts/core/{name}.md` + 可選的 `prompts/appendix/{name}-{model}.md`，回傳 `PromptBundle(core_text, appendix_text, prompt_version)`。PHASE2_PLAN §1.1 要求 model-specific 內容只能寫在 appendix，core 保持跨 provider 共用。

## 為什麼 raw_text 跟 parsed 要同時回

一開始只回 dict，出問題時 log 裡看不到模型到底吐了什麼字、只看得到 parse 之後的結果，除錯很痛苦。現在：tool 用 `.parsed`；agent loop 的 `_record_llm()` 順手抓 `.raw_text` 寫進 `turn_NN_<tool>.json` 的 `raw_model_output`。好處是 tool 的介面不變、又能保留原始紀錄。

## 使用上的幾個規定

- **Structured output 是合約**。
  - OpenAI：`response_format=json_schema` + `strict=True`。
  - Anthropic：forced `tool_use`，`tool_choice={"type":"tool","name":...}`，`input_schema` 就是 target schema。
  - DeepSeek：先試 `response_format=json_schema`；如果 endpoint 不支援（`json_schema_support=False`），退回 `json_object` 並把 schema inline 到 system prompt。
- `temperature=0` 是固定的（PHASE2_PLAN §1.1），避免同題同結果飄移。
- `response_schema` 由 tool 自己產生。這個 repo 目前大多直接在 tool 檔案裡手寫 JSON schema dict，而不是在 llm/ 這層定義。重點是：llm/ 不知道任何 domain 細節，它只拿 schema 當 opaque contract。
- **沒有內建 retry**。provider 回錯直接 raise，由上層 tool / loop 用 `TerminateReason` 處理。

## 想換 model 或換 provider 的話

1. 在 `factory.py` 的 `SUPPORTED_MODELS` / `PROVIDER_BY_MODEL` 補 entry。
2. 若要新 provider，寫 `make_xxx_llm(...)` 回傳 `LLMJsonCall`，在 `make_llm` 加新 branch。
3. 在 `prompts/appendix/` 放對應模型的 appendix（或空殼 placeholder）。
4. CLI / runner / tool 都不用改 — 它們只認 `LLMJsonCall` 跟 `LLMBinding`。

## 測試 mocking

- 測試不想跟真 provider 講話時，patch `gh_search.cli._resolve_llm` 或 `gh_search.cli.make_llm`，回傳一個 `LLMBinding(call=_scripted_llm(...), provider_name=..., model_name=...)`。
- 不要直接 patch 個別 adapter — 會繞過 factory 路由，之後換 provider 時容易壞。
