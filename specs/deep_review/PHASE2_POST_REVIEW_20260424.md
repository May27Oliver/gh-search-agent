# Deep Code Review — Phase 2 Post-Delivery Tech Debt Sweep

> **Date**: 2026-04-24
> **Scope**: 全 repo（偏重 `src/gh_search/llm/`、`tests/`、`scripts/build_model_matrix.py`、`README.md`、`specs/main/`、`prompts/appendix/`）
> **Goal**: 不找一般 bug，專門找 dead code / legacy naming / 棄用 adapter 路線 / Qwen→DeepSeek 切換殘留 / unreachable branches / duplicate logic / doc-code drift / over-abstraction / 可在第一次 commit 前安全收斂的內容
> **Method**: 4 個 review agent 並行掃描 + 主幹針對可疑 claim 實地 grep/read 驗證

---

## TL;DR

- ✅ **Qwen → DeepSeek 切換乾淨**：code / spec / config / prompt / tests 全部已清乾淨。
  唯一殘留是 `artifacts/eval/**/retrieved_repositories.json` 內被 GitHub API 回傳的 repo description 字串（ollama 的 README 提及 Qwen），屬於 immutable history record，**不動**。
- ⚠️ **Tech debt 集中在 LLM adapter 層**：過度設計的 `LLMResponse` 欄位、跨層 duplicate map、Optional shim 留給 Phase 1 legacy fixture 卻已經不需要。
- ⚠️ **沒有 structural rot**。找到的 10 個 finding 都是「Phase 2 寫得太前瞻、production 還沒追上」性質的雜訊，安全處理不會影響 §3.2 baseline matrix 的結論。

---

## Severity 統計

| Severity | Count | 來源 reviewer |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 3 | llm-audit, refactor-cleaner |
| MEDIUM | 5 | llm-audit, refactor-cleaner |
| LOW | 2 | refactor-cleaner |
| **Total** | **10** | |

---

## 🔴 HIGH — runtime 事實上沒人用的抽象

### H1 — `LLMResponse` 的 4 個 field populated-but-never-consumed

- **Location**:
  - 定義：[src/gh_search/llm/__init__.py:23-27](../../src/gh_search/llm/__init__.py#L23-L27)
  - 被三個 adapter 填值：
    - [openai_client.py:61-64](../../src/gh_search/llm/openai_client.py#L61-L64)
    - [anthropic_client.py:107-110](../../src/gh_search/llm/anthropic_client.py#L107-L110)
    - [deepseek_client.py:74-77](../../src/gh_search/llm/deepseek_client.py#L74-L77)
  - 文件聲稱 consumer：[src/gh_search/llm/AGENTS.md:9](../../src/gh_search/llm/AGENTS.md#L9)
- **Type**: Dead field（populated-but-never-consumed）
- **Why**: `finish_reason` / `latency_ms` / `provider_response_id` 被三個 adapter 精心填好，但整條 production 路徑（`agent/loop.py`、`eval/runner.py`、`logger/session.py`、`cli.py`、`scripts/build_model_matrix.py`）**沒有任何一處讀這些 field**。`agent/loop.py:61` 的 `latency_ms` 是自己 `time.perf_counter()` 量的，和 `LLMResponse.latency_ms` 無關（事實上 duplicate measurement）。`transport_error` field 更進一步 — **沒有任何 adapter 填它**，永遠是 `None`。`AGENTS.md:9` 聲稱「給 logger / matrix aggregator 用」實際不成立 → doc drift。
- **Canonical path**（三擇一，須做決策）:
  - (A) 刪除這 4 個 field + 對應 adapter 填值邏輯 + 更新 `AGENTS.md` —— 最小化，與當前 production 對齊
  - (B) 保留 field，把值寫進 `run.json` 或 `per_item_results.jsonl`，兌現原本文件的承諾 —— observability 投資
  - (C) 就地加個 `# reserved for Phase 3 observability` 註解並保留 —— 最差，債還在
  - **推薦 A**：先拿掉，需要再加回，commit 歷史才乾淨

### H2 — `LLMBinding.endpoint_url` production 完全沒人讀

- **Location**:
  - 定義：[src/gh_search/llm/factory.py:76](../../src/gh_search/llm/factory.py#L76)
  - 被填入：[factory.py:151, 161](../../src/gh_search/llm/factory.py#L151)
  - 唯一 consumer：[tests/test_llm_factory.py:70](../../tests/test_llm_factory.py#L70)（test assert 自己剛設定的值，tautology）
- **Type**: Dead field
- **Why**: 整個 `src/` + `scripts/` 沒有任何地方讀 `binding.endpoint_url`。adapter 內部（`deepseek_client.py`）已經持有 endpoint，外露到 binding 層沒有 downstream consumer。該欄位是 Phase 2 §3.0 「partial matrix 必須明確記錄實際 provider / endpoint」這條規格的誤讀 —— 正確做法是把 endpoint 寫進 `run_config.json`，不是掛在 binding 上。
- **Canonical path**: 從 `LLMBinding` 移除 `endpoint_url`；同步刪 `test_llm_factory.py:70-71` 兩行 assert；若要兌現 §3.0 的「記錄 endpoint」規格，由 DeepSeek adapter 自己在 `LLMResponse.usage` 或 `run_config.json` 寫入。

### H3 — `PROVIDER_BY_MODEL` dict 跨層重複並開始漂移

- **Location**:
  - Canonical source：[src/gh_search/llm/factory.py:48-53](../../src/gh_search/llm/factory.py#L48-L53) — 4 entries
  - Duplicate copy：[scripts/build_model_matrix.py:43-54](../../scripts/build_model_matrix.py#L43-L54) — 8 entries
- **Type**: Duplicate map / drift
- **Why**: Script 自己寫了一份 `PROVIDER_BY_MODEL`，多出 `gpt-4o-mini` / `gpt-4o` / `claude-opus-4` / `deepseek-reasoner`；factory 的 canonical source 沒有這些。兩份手動同步已經開始漂移。
  - `deepseek-reasoner` 在 factory 是 `MODEL_ALIASES` 的 alias → 正規化成 `deepseek-r1`，所以 runner 寫進 `model_summary.json` 的永遠是 canonical `deepseek-r1`，**script 裡的 `"deepseek-reasoner": "deepseek"` 永遠不會被命中**。
  - `claude-opus-4` 不在 factory.PROVIDER_BY_MODEL，產不出這樣的 artifact。
- **Canonical path**:
  ```python
  # scripts/build_model_matrix.py
  from gh_search.llm.factory import PROVIDER_BY_MODEL
  # 刪除本地 dict
  ```
  若真的需要「讀舊 artifact 時能 fallback 到 gpt-4o 之類 canonical 外的名字」，用一個獨立的 `_LEGACY_PROVIDER_HINTS` 小 dict 並加註解說明它只處理 Phase-1-era run。

---

## 🟠 MEDIUM — unreachable branches / backward-compat shims

### M1 — `_API_MODEL_ID` 3/4 entries unreachable

- **Location**: [src/gh_search/llm/anthropic_client.py:37-42](../../src/gh_search/llm/anthropic_client.py#L37-L42)
- **Type**: Dead entries
- **Why**: 4 個 key，實際可達的只有 `claude-sonnet-4`：
  - `claude-sonnet-4-5`: 在 [factory.py:39](../../src/gh_search/llm/factory.py#L39) `MODEL_ALIASES` 被 normalize 成 `claude-sonnet-4`，到 adapter 時已經是 canonical → `_API_MODEL_ID["claude-sonnet-4-5"]` 永遠不會查
  - `claude-3-5-sonnet`: 同上，[factory.py:40](../../src/gh_search/llm/factory.py#L40)
  - `claude-opus-4`: 不在 [factory.PROVIDER_BY_MODEL:48-53](../../src/gh_search/llm/factory.py#L48-L53) 也不在 MODEL_ALIASES → `canonical_model_name` 會直接 raise `UnknownModelError`，永遠到不了 adapter
- **Canonical path**: 刪除這 3 個 dead key；若要真的支援 Opus 或 Sonnet-4.5，要在 `factory.MODEL_ALIASES` + `factory.PROVIDER_BY_MODEL` 同步開路（而不是偷偷塞在 adapter 層）。

### M2 — `.lower()` fallback branch unreachable

- **Location**: [scripts/build_model_matrix.py:185-191](../../scripts/build_model_matrix.py#L185-L191)
- **Type**: Unreachable branch
- **Why**: 4-level fallback chain：
  ```python
  provider = (
      run_config.get("provider_name")
      or summary.get("provider_name")
      or PROVIDER_BY_MODEL.get(model_name)
      or PROVIDER_BY_MODEL.get(model_name.lower() if isinstance(model_name, str) else "")
      or "unknown"
  )
  ```
  Script 自己的 `PROVIDER_BY_MODEL` 的 key 本身就是 lowercase kebab-case，`.lower()` 不會產生新的 lookup key。前兩個 branch 在 Phase 2 之後 runner 已 always populate，只有 Phase 1 legacy artifact 會落到 static map。
- **Canonical path**:
  ```python
  provider = (
      run_config.get("provider_name")  # Phase 2+
      or summary.get("provider_name")  # Phase 2+ (redundant safety)
      or PROVIDER_BY_MODEL.get(model_name, "unknown")  # Phase 1 legacy only
  )
  ```
  加 comment 注記「legacy-only path for pre-Phase-2 artifacts」。

### M3 — `RunLog.provider_name` Optional 只剩一個 test helper 在用

- **Location**:
  - 定義：[src/gh_search/schemas/logs.py:23](../../src/gh_search/schemas/logs.py#L23)
  - 所有 production 構造點 always 填值：
    - [src/gh_search/cli.py:135](../../src/gh_search/cli.py#L135)
    - [src/gh_search/eval/runner.py:281](../../src/gh_search/eval/runner.py#L281)
  - 唯一仰賴 Optional default 的地方：[tests/test_logger.py:75-87](../../tests/test_logger.py#L75-L87)
- **Type**: Backward-compat shim
- **Why**: Phase 2 之後 `cli.py` 和 `runner.py` 都 always 傳 `binding.provider_name`（`ProviderName` Literal type，保證非空）。Optional default 唯一 load-bearing 的地方是 `test_logger.py:75` 這個 helper 省略沒傳。
- **Canonical path**: 改成 `provider_name: str = Field(...)` 必填；`test_logger.py:75` 那行補 `provider_name="openai"`。

### M4 — `SmokeSummary.provider_name` / `run_smoke_eval` param 同樣多餘 Optional

- **Location**:
  - [src/gh_search/eval/runner.py:40](../../src/gh_search/eval/runner.py#L40) (`SmokeSummary.provider_name: str | None = None`)
  - [src/gh_search/eval/runner.py:50](../../src/gh_search/eval/runner.py#L50) (`run_smoke_eval(..., provider_name: str | None = None, ...)`)
- **Type**: Backward-compat shim
- **Why**: 所有 caller 經過 `make_llm → LLMBinding.provider_name: ProviderName`，非 Optional。Optional 是 Phase 1 殘留 noise。
- **Canonical path**: 兩處都改 `str` 非 Optional。

### M5 — `_usage_dict` 三個 adapter 各抄一遍

- **Location**:
  - [openai_client.py:54-60](../../src/gh_search/llm/openai_client.py#L54-L60)
  - [deepseek_client.py:77-100](../../src/gh_search/llm/deepseek_client.py#L77-L100)
  - [anthropic_client.py:130-146](../../src/gh_search/llm/anthropic_client.py#L130-L146)
- **Type**: Duplicate logic
- **Why**: OpenAI/DeepSeek 版本實質相同；Anthropic 只差 key 正規化（`input_tokens`→`prompt_tokens`、`output_tokens`→`completion_tokens`）。三份各抄一次，未來加 provider 還要抄第四次。
- **Canonical path**: `llm/__init__.py` 開一個：
  ```python
  def normalize_usage(usage_obj, key_mapping: dict[str, str] | None = None) -> dict: ...
  ```
  OpenAI/DeepSeek 呼叫 `normalize_usage(raw)`，Anthropic 呼叫 `normalize_usage(raw, {"input_tokens": "prompt_tokens", ...})`。

---

## 🟡 LOW — clutter，不急但建議收

### L1 — Dev-churn eval artifact 目錄，沒有 iteration 指到它們

- **Location**:
  - `artifacts/eval/eval_gpt41mini_20260424_rerun/`
  - `artifacts/eval/eval_gpt41mini_2026042401/`（甚至缺 `per_item_results.jsonl`，不可用）
  - `artifacts/eval/smoke_3848edfa/`
  - `artifacts/eval/smoke_96290075/`
  - `artifacts/eval/smoke_phase2_gpt41mini_validate/`
  - `artifacts/eval/smoke_phase2_claude_validate/` + `_validate2/`
- **Type**: Dev-churn
- **Why**: 任何 `iterations/*/refs.json` 都沒指到這些 run_id；grep 0 references in `src/` + `tests/`。純 dev-cycle 中段驗證產物。
- **Canonical path**: 第一次 commit 前清掉。只保留 `eval_gpt41mini_20260424`（iter_0 legacy）、`eval_gpt41mini_phase2_20260424`、`eval_claude_sonnet4_phase2_20260424`、`eval_deepseek_r1_phase2`（如果 refs.json 有指到）。

### L2 — DeepSeek adapter 內部 4 個 helper 過度細分

- **Location**: [src/gh_search/llm/deepseek_client.py:85-185](../../src/gh_search/llm/deepseek_client.py#L85-L185)
  - `_inline_schema_if_needed` / `_pick_response_format` / `_build_request_kwargs` / `_create_with_fallback` / `_should_fallback_to_json_object`
- **Type**: Over-abstraction
- **Why**: 5 個 private helper，沒有任何一個被單獨單測打到（只有 integration 測試 `test_deepseek_client.py` 全鏈路）。拆這麼細是為了「之後 self-host vLLM 會走不同路徑」的伏筆，現況只有 DeepSeek 官方一條實際使用的路徑。
- **Canonical path**: 先**留著不擋路**；真的要精簡時 inline 回 `make_deepseek_llm`；若要精簡，先加 helper-level unit test 再動手。

---

## ✅ Confirmed Clean — 不動

| Area | 結論 |
|---|---|
| `src/`、`tests/`、`scripts/`、`specs/`、`prompts/`、`README.md`、`.env.example` 內的 Qwen 字面搜尋 | **零殘留** |
| [PHASE2_PLAN.md §1.1 / §3.0](../main/PHASE2_PLAN.md) | 已經是 DeepSeek-R1，not Qwen |
| [specs/tunning/EVAL_GPT41MINI_20260424_PLAN.md §8 Iteration 2](../tunning/EVAL_GPT41MINI_20260424_PLAN.md) | 已經是 `GH_SEARCH_MODEL=DeepSeek-R1` bash 範例 |
| `prompts/appendix/*-{gpt-4.1-mini,claude-sonnet-4,deepseek-r1}-v1.md` | 9 個檔案齊全；intention/repair 未填內容的 appendix 是刻意的 baseline placeholder（HTML comment 註明「Empty baseline」），**不是 dead file** |
| `prompts/core/*.md` | model-agnostic，沒夾任何模型名 ✓ |
| `artifacts/eval/**/retrieved_repositories.json` 內的 Qwen 字串 | 是 ollama/ollama repo 的 GitHub description 被 API 回傳 captured 下來的 immutable record（repo 的 README 提及它支援 Qwen/Gemma/etc），屬於歷史 audit artifact，不動 |
| CLI / factory / runner 的 DeepSeek 串通性 | 四條測試路徑（`test_deepseek_client.py` / `test_llm_factory.py` / `test_cli_provider_routing.py` / runtime 實跑 `eval_deepseek_r1_phase2`）均 green |

---

## 建議處理順序

### 🔵 第一次 commit 前（低風險，收斂雜訊）

優先順序：

1. **H2** — 刪 `LLMBinding.endpoint_url` + 對應兩行 test（3 行 diff）
2. **H3** — Matrix script 改 `from gh_search.llm.factory import PROVIDER_BY_MODEL`，刪 local copy（~15 行 diff）
3. **M1** — 刪 `_API_MODEL_ID` 的 3 個 dead key（3 行 diff）
4. **M2** — 刪 matrix script 的 `.lower()` fallback branch（2 行 diff）
5. **M3 + M4** — `RunLog.provider_name` / `SmokeSummary.provider_name` / `run_smoke_eval` param 改非 Optional；補 `test_logger.py:75` 的 `provider_name="openai"`
6. **L1** — 刪 dev-churn artifact 目錄（純檔案操作，無 code 影響）

### 🟢 第一次 commit 前（需要決策）

7. **H1** — 決定 `finish_reason` / `latency_ms` / `provider_response_id` / `transport_error` 四個 field 的命運：
   - **推薦方案 A**：刪除 field + 對應 adapter 填值邏輯 + 更新 `AGENTS.md`。理由：Phase 2 目標是「infra readiness」，不是「full observability」；這四個 field 沒有任何 production consumer，留著是兌現一個沒人讀的承諾。要加回來 Phase 3 再加，commit 歷史才乾淨。

### 🟡 可延後（non-blocking）

8. **M5** — `_usage_dict` 合併到 `llm/__init__.py` 的共用 helper（cross-cutting，收益中等）
9. **L2** — DeepSeek adapter 內部 helper 收斂（等確定不會再加 vLLM 路徑時再做；要做前先加 helper-level 單測）

---

## Review 方法論

本次 review 用 4 個並行 agent 分區掃描，每個負責一個角度，避免單一 reviewer 的 blind spot：

| Reviewer | 焦點 | 輸出 |
|---|---|---|
| **llm-adapter-audit** (Explore) | `src/gh_search/llm/` + `tests/` 的 dead code / unreachable / duplicate / over-abstraction | H1、M1、M5、L2、確認 Qwen 零殘留 |
| **qwen-pivot-residue** (Explore) | 全 repo 搜尋 Qwen 字面，分類每個命中 | 12 筆全部為 HISTORICAL（GitHub API 回傳的 repo description 字串），**無 action** |
| **matrix-runner-debt** (refactor-cleaner) | `scripts/build_model_matrix.py` + `eval/runner.py` + `schemas/logs.py` 的 duplicate / backward-compat shim / unreachable | H2、H3、M2、M3、M4、L1 |
| **docs-specs-prompts** (Explore) | `README.md` + `specs/main/` + `prompts/` 的 doc-code drift / empty placeholder | 無 drift（Qwen 切換已完整同步；empty prompt appendix 是刻意 baseline） |

所有 agent finding 均經過主幹的實地 grep / read 驗證後才納入本報告；agent 自行推論但無法 grep 證實的 claim 已剔除。

---

## 結論

Phase 2 infra 沒有 structural rot。10 個 finding 全部集中在「Phase 2 寫得太前瞻、production 還沒追上」性質的 field / abstraction，安全收斂不會影響 §3.2 baseline matrix 的結論或 Iteration 1 handoff。建議 H1 H2 H3 + M1~M4 + L1 在第一次 commit 前收斂（約 30~40 行 diff），commit 歷史會乾淨很多。
