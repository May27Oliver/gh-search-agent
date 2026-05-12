# normalizers — 開發指南

這個 package 是 keyword canonicalization 與相關 hardening 規則的唯一入口（KEYWORD_TUNING_SPEC §8）。Parser、validator、repair、scorer、logs 都必須走這套，不准自己寫 lowercase / sort / merge / lemmatize。

## 兩層 hardening 規則

每條 hardening 規則都會被分到兩個 layer 之一（`gh_search.schemas.enums.RuleLayer`）：

- **`DOMAIN_STABLE`** — 原則性規則。在 GitHub repository search 這個 domain 中合理長期保留，**不需要綁某一題才成立**。即使換掉現有 eval dataset 仍應留著。
- **`DATASET_BACKED`** — 目前有效，但證據主要來自現有 eval dataset 的少數題目。**泛化能力還沒被充分證明**；保留這條規則可以接受，但隨 dataset 擴張要持續複查。

這個分類**不是**嚴重程度標記，**不是** outcome 標記。它回答的是「**這條規則靠什麼證據支撐**」這個問題。

### 為什麼要分層

不分層時，所有規則看起來都像同一種東西，外部 reviewer 容易解讀成「你不是在做通用 normalization，你是在 patch benchmark」。分層後文件可以誠實說清楚：

- 哪些規則我們相信可長期保留
- 哪些規則只是目前先救分，但還需要更多證據

## 怎麼看 trace 裡的 layer

`find_keyword_violations()` 回傳的每個 `ValidationIssue` 都帶 `layer` 欄位；這個 list 進到 `KeywordNormalizationTrace.violations` → `turns.jsonl`。

```jsonc
{
  "code": "alias_applied",
  "token": "pythn",
  "replacement": "python",
  "layer": "dataset_backed"   // ← 看這裡
}
```

分析時可以直接過濾：
- `layer == "domain_stable"` 的修正，當作系統穩定能力的一部分
- `layer == "dataset_backed"` 的修正，標記為「目前有效但要繼續觀察」

## 分類規則一覽

下表記錄每個 issue code 的分類邏輯。**家族 default + 稀疏 override** 的結構讓 audit 容易：絕大多數規則用 default，只有少數 entries 需要 override。

| code | layer 規則 | 為什麼 |
|---|---|---|
| `plural_drift` | 全部 `DOMAIN_STABLE` | 英文 plural drift 跨 domain 成立 |
| `decoration_stopword` | 全部 `DATASET_BACKED` | `implementations` / `projects` 錨在 q007 / 等具體題 |
| `multilingual_canonicalization` | 全部 `DATASET_BACKED` | CJK compound rewrites 每條錨 1-2 題（q027/q028/q029） |
| `multilingual_context_drop` | 全部 `DATASET_BACKED` | 同上，narrow contextual cleanup |
| `language_leak` | 全部 `DOMAIN_STABLE` | 「language token 不該進 keywords」是 principled invariant |
| `phrase_split` | 全部 `DOMAIN_STABLE` | named entity 不應被切開 |
| `qualifier_in_keyword` | 全部 `DOMAIN_STABLE` | 安全防護（防 GitHub qualifier 注入） |
| `alias_applied` | per-token：default `DATASET_BACKED`；override `DOMAIN_STABLE` for `js`/`ts`/`py`/`rb`/`pg`/`postgres` | typo 系列（`pythn`/`javscript`/...）錨在 q023-q026；多語 alias（`爬蟲`/`框架`/...）錨在 q027-q029；只有標準 programming 縮寫是跨 domain |
| `modifier_stopword` | per-token：default `DOMAIN_STABLE`；override `DATASET_BACKED` for `cool`/`good`/`small`/`recent`/`open source` | ranking 詞（`popular`/`top`/`trending`/...）跨 domain；主觀裝飾詞（`cool`/`good`/`small`）、時間語義（`recent`，目前 schema 表達不了）、內容語義（`open source`）都偏 heuristic |

實作上 `classify_issue(code, token)` 是單一查詢函式，未知 code 直接 raise `ValueError` — 避免新規則默默 emit 沒 layer 的 issue。

## 加新規則時的程序

1. 寫規則本身（dict / set / regex 等）
2. 決定它屬於哪一 layer：
   - 「即使換 eval dataset 仍應留著」→ `DOMAIN_STABLE`
   - 「主要靠目前 dataset 的某幾題支撐」→ `DATASET_BACKED`
3. 在 `find_keyword_violations()` 對應的 emission site 加新 `ValidationIssue`
4. 在 `classify_issue()` 加分類：
   - 整個 code 一律同 layer → 進 `_FIXED_LAYER_BY_CODE`
   - 同 code 內 entries 跨 layer → 加新的 family default + override 對應（仿 `_ALIAS_LAYER_*` / `_MODIFIER_STOPWORD_LAYER_*`）
5. 補 test：
   - `tests/normalizers/test_keyword_rules.py` 的 `TestRuleLayerClassification` 加一條
   - `test_every_emitted_code_has_a_classification` 預設要把新 code 也覆蓋到

## validate_query 那一側

`src/gh_search/tools/validate_query.py` 也有 hardening 規則（`_suppress_unsupported_language` / `_normalize_star_bounds` / `_normalize_ranking`），但這幾個目前**不 emit ValidationIssue** — 它們直接 mutate `StructuredQuery`。

該檔有 `_MUTATION_RULE_LAYERS` 常數記錄每個 mutation helper 的 layer，**目前只是 documentation**，還沒接到 trace artifact。後續工作會加 mutation trace stream，把這個常數的標籤實際串到每個 mutation event 上。

`_RANKING_PATTERNS` 內 `熱門` regex 只錨在 q027，雖然整個 `_normalize_ranking` function 標為 `DOMAIN_STABLE`，這個 pattern 本身比較像 `DATASET_BACKED`。等之後 per-pattern layering 上線時要拆出。

## 不要做的事

- 不要在 normalizer 之外的地方寫 keyword 處理規則（lowercase / sort / merge / lemmatize）。Single source of truth in this package.
- 不要在 `_ALIAS_MAP` 加只能靠「現實可能發生」就放進去的條目。標準是「**有沒有足夠跨 dataset 證據，值得當全域規則**」。沒有的話加進 `DATASET_BACKED` override 並在 commit message 寫清楚錨點題目。
- 不要在沒更新 `classify_issue` 的情況下新增 issue code — `test_every_emitted_code_has_a_classification` 會擋下來。
