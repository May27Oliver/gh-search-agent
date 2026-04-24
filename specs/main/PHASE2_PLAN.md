# Phase 2 Plan

## 1. 目標

Phase 2 的目標不是直接開始做 parser tuning，而是先把系統升級成：

```text
可跨 provider / 跨模型執行 -> 可聚合比較 -> 可回歸驗證 -> 可支撐後續 tuning
```

Phase 2 完成時，系統應具備：

- cross-provider multi-model baseline
- canonical `model_matrix` 聚合輸出
- provider adapter architecture
- retrieval result logging 與 human-auditable eval artifacts
- golden regression guard
- scorer review artifact 與後續維護責任

## 1.1 Phase 2 固定技術決策

為避免 implementer 在 Phase 2 開發時持續搖擺，先固定以下決策：

- Phase 2 範圍是 **infra-only**
- iteration-level tuning 任務不放在本文件，交由 [specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md:1) 接手
- `prompt / few-shot / gate wording` 改動必須隔離為 model-specific appendix
- 所有 model-specific 改動都必須做 `>= 2` 個正式模型、且跨 provider 的 falsification
- Iteration 0 預設 baseline 模型組合：
  - `gpt-4.1-mini`
  - `claude-sonnet-4`
- Iteration 2 起必跑三個正式模型：
  - `gpt-4.1-mini`
  - `claude-sonnet-4`
  - `DeepSeek-R1`
- decoding 固定：
  - `temperature = 0`
- prompt 檔案物理位置固定為：
  - `prompts/core/v{N}.md`
  - `prompts/appendix/{model_name}-v{N}.md`
- `model_name` 規則：
  - canonical identifier 一律 lowercase kebab-case
  - CLI 輸入可做 alias mapping，但 runtime / logs / matrix 一律寫 canonical name
- partial matrix 規則：
  - provider 掛掉時可產出 partial matrix 作為 debug artifact
  - 但 partial matrix **不得**作為 iteration pass / release gate 依據
- ownership 邊界：
  - per-run eval runner 負責產出單一 `eval_run_id` 的 artifacts
  - matrix aggregator 負責跨 run 聚合，不負責單題執行
- logging schema 必須增加 `provider_name`
- `per_item_results` 必須同時服務：
  - 機器聚合
  - 人眼 audit
- 因此每筆 `per_item_results` 都必須包含：
  - `compiled_query`
  - `retrieved_repositories`
  - `retrieved_repositories_path`
- `retrieved_repositories` 預設保留 top `5` 筆摘要
- 每題完整 retrieval payload 必須另存獨立 artifact，不可只保留 `result_count`
- DeepSeek provider 規則：
  - 正式模型 family 寫為 `DeepSeek-R1`
  - 若透過官方 API 執行，實際 model id 可為 `deepseek-reasoner`
  - 若透過 OpenAI-compatible gateway / hosted inference 執行，必須在 run config 與 matrix refs 明確記錄實際 provider / endpoint / deployed model id

## 2. Phase 2 驗收標準

Phase 2 驗收只看 infra readiness，不看 parser tuning 成果。

必須同時滿足：

- 已完成 provider adapter architecture，至少可接：
  - OpenAI
  - Anthropic
  - DeepSeek provider
- 每個 eval item 的 `per_item_results` 都可直接看到 `retrieved_repositories` 摘要
- 每個 eval item 都可回連到完整 retrieval artifact
- 已建立 `model_matrix.json` / `model_matrix.md` / `refs.json`
- 至少 2 個正式模型的 cross-provider baseline 已完成
- `q012`、`q015`、`q025` 已凍結成 golden tests
- scorer review 已完成並落地成維護 artifact
- 已至少產出 1 份含 `>= 2` 個 cross-provider model rows 的 canonical `model_matrix.json`

## 3. 任務拆解

### 3.0 Provider Adapter Architecture

目的：

- 讓 `gpt-4.1-mini`、`claude-sonnet-4`、`DeepSeek-R1` 能透過統一 contract 被 eval runner 呼叫
- 解決 Phase 2 真正新的架構工作

預期交付物：

- provider-agnostic `LLMJsonCall` / adapter contract
- OpenAI adapter
- Anthropic adapter
- DeepSeek adapter
- provider routing 規則
- prompt loading / composition 規則
- config / env 擴充

應參考文件：

- [EVAL_EXECUTION_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL_EXECUTION_SPEC.md:1)
- [SCHEMAS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/SCHEMAS.md:1)
- [specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md:1)

架構要求：

- adapter contract 必須統一：
  - input：`model_name`、`provider_name`、`system_prompt`、`messages`、`response_schema`、`temperature`、`timeout_seconds`
  - output：`raw_text`、`parsed_json`、`finish_reason`、`usage`、`latency_ms`、`provider_response_id`、`transport_error`
- 不允許上層 runner 依賴 provider 原生格式
- prompt 組裝必須支援：
  - core prompt
  - per-model appendix
- config / env 至少擴充：
  - `ANTHROPIC_API_KEY`
  - `DEEPSEEK_API_KEY`
  - `GH_SEARCH_PROVIDER`
- CLI routing 必須能將 `--model claude-sonnet-4` 解析到正確 adapter
- test mocking 必須維持可替換 `LLMJsonCall`，不可把 provider SDK 綁死在 agent loop

驗證方式：

- `gpt-4.1-mini`、`claude-sonnet-4` 各自可成功跑 1 個 smoke / eval item
- 若 DeepSeek provider 可用，`DeepSeek-R1` 也可完成至少 1 個 smoke / eval item
- logs / run config / matrix row 都包含 `provider_name`
- 同一個 runner 不需要改上層邏輯即可切換 provider

若驗證失敗，調整方式：

- 先用 thin adapter，不先追求 provider feature 完整性
- DeepSeek 先接受官方 API 或 hosted endpoint，不先追求自架部署
- 若 Anthropic / DeepSeek structured output API 差異過大，先在 adapter 層做 schema coercion，不把差異滲到 runner

### 3.1 Retrieval Result Logging & Auditability

目的：

- 讓 eval 不只知道這題 `success / rejected / no_results`
- 也能讓人直接檢查「這題實際從 GitHub 找回了哪些 repo」

預期交付物：

- `per_item_results.jsonl` / `per_item_results.json` 新欄位：
  - `compiled_query`
  - `retrieved_repositories`
  - `retrieved_repositories_path`
- 每題獨立 retrieval artifact，例如：
  - `retrieved_repositories.json`
  - 或 `artifacts/turn_XX_execute_github_search.json` 內含 top-N repos

欄位要求：

- `retrieved_repositories` 需直接存在於 `per_item_results`
- 預設只放 top `5` 筆，作為人眼可讀摘要
- 每筆至少包含：
  - `name`
  - `url`
  - `stars`
  - `language`
  - `description`
- `retrieved_repositories_path` 必須指向完整 artifact

應參考文件：

- [LOGGING.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/LOGGING.md:1)
- [EVAL.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL.md:1)
- [EVAL_EXECUTION_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL_EXECUTION_SPEC.md:1)

驗證方式：

- 任一 `success` 或 `no_results` 題都可在 `per_item_results` 看見：
  - `compiled_query`
  - `retrieved_repositories`
  - `retrieved_repositories_path`
- 人工 spot check 時，不必再進 session state 就能知道 top repos 是哪些
- `retrieved_repositories_path` 指向的 artifact 存在且格式合法

若驗證失敗，調整方式：

- 先只保留 top 5 摘要，不先寫完整 GitHub response body
- 不把 repo list 塞進 shared state，改寫獨立 artifact
- 先讓 eval runner 寫出 retrieval summary，再補 session logger 整合

### 3.2 建立 Multi-Model Baseline

目的：

- 建立 Phase 2 的 cross-provider 起點
- 區分 task-level failure 與 model-specific failure

預期交付物：

- 至少 2 個正式模型的 eval runs
- baseline iteration id
- 各 model 對應的 `eval_run_id`

應參考文件：

- [EVAL.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL.md:1)
- [EVAL_EXECUTION_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL_EXECUTION_SPEC.md:1)
- [specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md:1)

驗證方式：

- 至少 2 個正式模型完成 eval
- 模型必須跨 provider
- 每個 model 都能回查對應 `per_item_results.jsonl`

若驗證失敗，調整方式：

- 先只保留 `gpt-4.1-mini + claude-sonnet-4`
- 不允許退回同 provider 內互比
- 優先修正 §3.0 的 provider adapter / config routing

### 3.3 Model Matrix Aggregator

狀態：

- `DONE in iter_0`

既有交付：

- `scripts/build_model_matrix.py`
- `artifacts/eval/iterations/iter_0_baseline_20260424/model_matrix.json`
- `artifacts/eval/iterations/iter_0_baseline_20260424/model_matrix.md`
- `artifacts/eval/iterations/iter_0_baseline_20260424/refs.json`

Phase 2 中的責任：

- 維護 canonical schema
- 確保後續 iteration 不破壞既有輸出格式
- 補 provider / per-field recall / future rows 時維持 backward compatibility

應參考文件：

- [LOGGING.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/LOGGING.md:1)
- [EVAL_EXECUTION_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL_EXECUTION_SPEC.md:1)
- [specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md:1)

驗證方式：

- 既有 iter_0 matrix artifact 可成功重建
- schema 回歸測試可抓出 breaking changes
- 後續 iteration 仍可輸出：
  - `model_matrix.json`
  - `model_matrix.md`
  - `refs.json`

若驗證失敗，調整方式：

- 先維持 JSON schema 穩定，不先調整 MD 呈現
- 新欄位採 additive-only 方式擴充

### 3.4 Golden Regression Guard

狀態：

- `DONE in iter_0`

既有交付：

- [tests/test_golden_iter0.py](/Users/chenweiqi/Documents/interview/gofreight/tests/test_golden_iter0.py:1)
- [tests/golden/iter0_cases.json](/Users/chenweiqi/Documents/interview/gofreight/tests/golden/iter0_cases.json:1)

Phase 2 中的責任：

- 維護 golden cases
- 確保 cross-model matrix 可計算 `golden_passed`
- 防止 provider adapter / runner / scorer 變更造成回歸

應參考文件：

- [specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md:1)

驗證方式：

- `q012`、`q015`、`q025` 在 baseline models 上全部 pass
- 任一題回歸時 golden test fail
- matrix row 可正確顯示 `golden_passed`

若驗證失敗，調整方式：

- 先修 adapter / scorer / runner，不先改 golden 期望
- 除非 dataset / scorer policy 已正式更新，否則不得任意重寫 golden cases

### 3.5 Scorer Review

狀態：

- `DONE in iter_0`

既有交付：

- [specs/tunning/ITER0_SCORER_REVIEW.md](/Users/chenweiqi/Documents/interview/gofreight/specs/tunning/ITER0_SCORER_REVIEW.md:1)

Phase 2 中的責任：

- 維護 scorer review 結論
- 將 scorer policy 變更和 dataset / parser 變更分開記錄
- 作為後續 tuning 的判斷依據，而不是重複做同一輪人工分類

應參考文件：

- [EVAL_EXECUTION_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL_EXECUTION_SPEC.md:1)
- [specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md:1)

驗證方式：

- scorer policy 變更時，需更新 review artifact 或新增新一輪 scorer review
- scorer 仍保持 deterministic
- 不會把明顯錯誤洗成正確

若驗證失敗，調整方式：

- 先只做最小 canonicalization
- 暫時不做 fuzzy match

### 3.6 Iteration Handoff

目的：

- 清楚切分 Phase 2 與 iteration-level tuning 的 ownership

交接規則：

- Phase 2 完成後，以下 tuning 任務交由 [specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md:1) 接手：
  - intention gate
  - parser output policy
  - date normalization
  - multilingual / noisy input ablation
- Phase 2 不以任何 parser tuning 成果作為 exit criteria

驗證方式：

- `PHASE2_PLAN.md` 與 tuning plan 無任務衝突
- implementer 讀完後能清楚知道：
  - infra work 看這份
  - tuning work 看 `specs/tunning/`

若驗證失敗，調整方式：

- 優先刪除 PHASE2 內重複的 tuning task
- 保持 Phase 2 僅聚焦 infra

## 4. 建議執行順序

### 4.1 先做 Provider Adapter Architecture

- `3.0` Provider Adapter Architecture

### 4.2 補 Retrieval Audit Layer

- `3.1` Retrieval Result Logging & Auditability

### 4.3 再做 Baseline

- `3.2` Multi-model baseline

### 4.4 已完成項目轉為維護

- `3.3` Model matrix aggregator
- `3.4` Golden regression guard
- `3.5` Scorer review

## 5. 進入 Iteration / Phase 3 前必須滿足

- provider adapter architecture 可穩定支援至少 2 個 cross-provider 模型
- `per_item_results` 已可直接顯示 `retrieved_repositories`
- retrieval artifact 可供人眼 audit
- 已有至少一份 canonical `model_matrix`
- 已完成至少一輪 cross-provider baseline
- golden tests 穩定
- scorer review artifact 已存在且被納入維護流程
- infrastructure 已能支撐後續 iteration-level tuning
