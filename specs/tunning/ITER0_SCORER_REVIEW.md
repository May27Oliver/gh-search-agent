# Iteration 0 — Scorer Review

> Source run: `eval_gpt41mini_20260424`（model `gpt-4.1-mini`, accuracy 3/30）
> Related plan: [EVAL_GPT41MINI_20260424_PLAN.md §5](EVAL_GPT41MINI_20260424_PLAN.md)
>
> 本份文件只做人工標註，不修 code。目的：在碰 parser/gate 之前，先確認目前 scorer
> 是否把「語意等價但表面不完全一致」的 prediction 判錯。

## Method

對 `artifacts/eval/eval_gpt41mini_20260424/per_item_results.jsonl` 中 14 題 keyword
mismatch（§3.2 列出）逐題標註：

- `S` — scorer brittleness（語意等價但 schema-different；scorer 應吸收）
- `P` — parser error（真的理解錯、加了不該加、拆了不該拆）
- `D` — dataset / ground truth 需要再確認
- 同一題可能同時帶多種標籤（例：`S+P`）

Canonicalization rules 的候選（對應 §5.2）：

1. **lowercase** — 所有 keyword 小寫比對（**目前 scorer 已做**）
2. **phrase-merge** — 若 gt 含多詞 phrase（`"machine learning"`），pred 包含該 phrase 所有 token，視為相符
3. **lemmatize-basic** — 僅處理英文單複數：`s$` / `es$` / `ies$ → y`
4. **language-redundancy** — 若 pred 的 keyword 等於 `language` 欄位值（case-insensitive），移除該 keyword 再比對

## Per-item annotations

| id | gt keywords | pred keywords | label | scorer rule that would save it | notes |
|---|---|---|---|---|---|
| q002 | `['machine learning']` | `['machine', 'learning']` | **P+S** | phrase-merge | parser 拆開 `machine learning`；phrase-merge 可接 |
| q003 | `['web', 'framework']` | `['rust', 'web', 'frameworks']` | **P+S** | language-redundancy + lemmatize | `rust` 冗餘（`language=Rust`）+ `framework→frameworks` |
| q005 | `['kubernetes', 'operator', 'example']` | `['kubernetes', 'operator', 'examples']` | **S** | lemmatize | 純單複數 |
| q006 | `['state management', 'library']` | `['state', 'management', 'libraries']` | **P+S** | phrase-merge + lemmatize | `state management` 拆開 + `library→libraries` |
| q007 | `['graphql', 'server']` | `['graphql', 'server', 'implementations']` | **P** | —（不應救） | parser 擅自加 `implementations`，語意擴寫，屬真正錯誤 |
| q008 | `['LLM', 'inference', 'engine']` | `['open', 'source', 'llm', 'inference', 'engines']` | **P** | —（不應救） | 加了 `open`、`source`；這是 parser 擴寫，不該吸收 |
| q010 | `['ai', 'agent', 'framework']` | `['ai', 'agent', 'frameworks']` | **S** | lemmatize | 純單複數 |
| q011 | `['scraping', 'library']` | `['scraping', 'libraries']` | **S** | lemmatize | 純單複數 |
| q014 | `['testing', 'framework']` | `['testing', 'frameworks']` | **S** | lemmatize | 純單複數 |
| q016 | `['game', 'engine']` | `['game', 'engines']` | **S** | lemmatize | 純單複數 |
| q017 | `['utility']` | `['small', 'utilities']` | **P+S** | lemmatize 只能吸收一半 | parser 加 `small`（過度推定），另有 date mismatch（§3.3） |
| q018 | `['spring boot', 'starter']` | `['spring', 'boot', 'starter']` | **P+S** | phrase-merge | `spring boot` 拆開；另有 `created_before` 缺失 |
| q023 | `['web', 'framework']` | `['python', 'web', 'framework']` | **P+S** | language-redundancy | `python` 與 `language=Python` 冗餘 |
| q028 | `['microservice', 'framework']` | `['微服务', '框架']` | **P** | —（不應救） | 中文未翻成 canonical English；典型 multilingual 問題 |

## Tally

| 類別 | 題數 | list |
|---|---|---|
| 純 `S`（只要 scorer 調整即可救） | 5 | q005, q010, q011, q014, q016 |
| `S+P`（scorer 調整 + parser 改也要做） | 6 | q002, q003, q006, q017, q018, q023 |
| 純 `P`（scorer 不能也不該救） | 3 | q007, q008, q028 |

## Findings

### F1. 5 題純粹是 scorer brittleness

q005 / q010 / q011 / q014 / q016 都是 `example↔examples`、`framework↔frameworks`、
`library↔libraries`、`engine↔engines` 這種英文單複數差異。parser 理解完全正確；
扣分只是 multiset equality 沒處理詞形變化。

- 引入 **lemmatize-basic**（只處理英文規則複數）即可全部收回
- 這 5 題全對 ≒ +16.7% accuracy（6/30 correct），且完全 model-agnostic

### F2. 6 題是 scorer + parser 混合

q002 / q003 / q006 / q017 / q018 / q023 這些題只靠 scorer 吸收不夠（phrase 還是被
parser 拆了），但部分失分確實是 scorer 可以先吸收一層，讓 parser 改動時錯誤 signal
更乾淨。

- `phrase-merge` 可救 q002 / q006 / q018（三題共通：gt 有 `"machine learning"` /
  `"state management"` / `"spring boot"`）
- `language-redundancy` 可救 q003 / q023（parser 重複放 `rust` / `python`）
- 但 q017 (`utility` vs `small utilities`) 只能救一半，`small` 仍是 parser error

這組合意義在：**先把 scorer 吸收掉這層，再看 parser 還錯哪些**，能避免把乾淨
改動壓在不乾淨的 metric 上。

### F3. 3 題是 parser 真正錯、scorer 不該救

q007 / q008 / q028：

- q007: parser 自行加 `implementations`
- q008: parser 自行加 `open`、`source`
- q028: parser 完全未把中文翻成英文 canonical keyword

這些屬於 `P1 Parser Output Policy` 和 `P3 Multilingual / Noisy Input` 的責任，不可用
scorer 吸收，否則會把真正的理解錯誤洗成正確。

### F4. 非 keyword 欄位的連帶影響

- q017: `created_after` 錯（`2024-01-01` vs `2026-01-01`）→ date normalizer（P2）責任
- q018: `created_before` 沒填 → date normalizer 責任
- q003 / q023 / q026 / q029: `language` 欄位在多題同時有 over-inference / redundancy 現象 → P1

這些不算在本份 scorer review 的 14 題內，但在 §10 的 `per-field recall` 統計時要分清。

## Recommended scorer adjustments（優先順序）

1. **lemmatize-basic**（規則：`s$` / `es$` / `ies→y`；**不做** fuzzy）
2. **phrase-merge**（gt 有多詞 phrase 時，pred 的 token set 包含該 phrase 所有 token
   即視為命中；unused tokens 仍須完全對齊）
3. **language-redundancy**（`pred_keywords.lower()` 若含 `language` 欄位值，比對前移除）

保留 deterministic、保留可解釋性。任何 fuzzy / semantic similarity 在 Iteration 0
**不做**。

## What this review is NOT

- 不是 scorer 的實作改動。實作歸 Iteration 1（P1 / gate relaxation 之後或同期）。
- 不是 dataset 改動。本輪暫不調整 `eval_dataset_reviewed.json`。
- 不降低 correctness 判定。若某題標 `S`，代表 **scorer 吸收後仍然保守**：只吸收「parser
  理解正確、表面差異」的部分，不吸收「parser 理解錯誤」的部分。

## Pass criteria（對應 §5.3）

- [x] 14 題 keyword mismatch 每題有人工標註
- [x] 每題明確區分 scorer 問題 / parser 問題（或兩者）
- [x] 產出下一輪 parser tuning 可依據的優先級

可以進下一步：golden tests（§7）+ model matrix artifact（§4.6）。
