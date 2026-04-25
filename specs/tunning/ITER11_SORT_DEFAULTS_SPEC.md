# Iteration 11 Sort Defaults / Ranking Intent Spec

## 1. 目標

本輪 tuning 的單一目標是把 **ranking intent -> `sort=stars`, `order=desc`**
下放到 deterministic downstream，補回 DeepSeek-R1 在 iter10 shipped baseline
中穩定遺失的 `sort/order`。

iter11 延續 iter5 - iter10 已確立的方法論：

- **不擴寫** `prompts/core/parse-v1.md`
- **不動** parser prompt / appendix prompt
- 優先把 dataset-backed ranking intent policy 放到 downstream

本輪所有 ground truth 一律對齊
`datasets/eval_dataset_reviewed.json`。

## 2. 背景

iter10 shipped baseline（`eval_*_iter10_20260425`）後：

- GPT：`27/30`
- CLA：`29/30`
- DSK：`24/30`

DSK 剩餘失分已高度集中在同一桶：

1. sort-default / ranking intent drift
2. plural drift 小尾巴
3. topic-retention 小尾巴

本輪只做第 1 桶。

### 2.1 iter10 baseline 中仍可直接由 ranking normalization 吃回的題目

| qid | model | iter10 blocker | 預期 iter11 |
|---|---|---|---|
| q013 | DSK | `sort=None`, `order=None` | CORRECT |
| q015 | DSK | `sort=None`, `order=None` | CORRECT |
| q026 | DSK | `sort=None`, `order=None` | CORRECT |
| q027 | DSK | `sort=None`, `order=None` | CORRECT |

共 **4 個 primary target pairs**。

### 2.2 bonus / secondary cases

| qid | model | iter10 blocker | 為何不列 primary |
|---|---|---|---|
| q020 | GPT | `sort=None`, `order=None` | 本輪主軸是 DSK sort drift；GPT 只列 bonus，不綁硬門檻 |
| q020 | DSK | 本輪已正確 | guard case，不列 target |

### 2.3 明確不在本輪處理

- `q009 DSK templates -> template`
- `q029 DSK japanese` 殘留
- `q018 GPT` 的 `created_before=null` 與 `spring boot` 缺失
- `q029 CLA` 的 `react` topic retention
- 任何 numeric semantics
- 任何 language suppression
- 任何 prompt-level ranking examples / appendix
- `sort=updated` / `latest` / `recent` / `newest` 等非 stars 排序軸

## 3. 單一判定原則

iter11 只在 **user query 明示表達 ranking intent** 時，補回
`sort=stars`, `order=desc`。

### 3.1 ranking intent evidence 規則

只有當 `user_query` 出現 dataset-backed ranking phrases 時，才允許 downstream
補回 `sort=stars`, `order=desc`。

iter11 應採 **query-driven rewrite**，不是只在 parser 已給部分 sort/order 時做修補。
也就是：

- query 有 ranking intent -> 不論 parser 原本是否漏掉 `sort/order`，都補成
  `sort=stars`, `order=desc`
- query 沒有 ranking intent -> 不新增 `sort/order`
- 若 parser 已給非空 `sort/order` 且 query 也支持 stars ranking -> 維持一致值即可

本輪 ranking lexicon 只覆蓋 dataset 已出現、且可安全對齊到 `stars desc`
的詞：

- `popular`
- `trending`
- `ranked by stars`
- `sorted by stars`
- `lots of stars`
- `most stars`
- `top N`（例如 `top10`, `top 10`, `top 5`）
- `按 star 排序`
- `按star排序`
- `按 stars 排序`
- `按stars排序`
- `熱門`

matching policy 必須明寫為：

- case-insensitive
- 多詞 English phrase 必須整段匹配，不允許單詞 partial match
  - 例如 `most stars` 不能只匹配 `most`
  - `lots of stars` 必須整串匹配
  - `ranked by stars` / `sorted by stars` 必須整串匹配
- `top N` 應支援 `top10` 與 `top 10`
- CJK phrase 不要求 word boundary，但仍需整段匹配
- CJK ranking phrase 應支援連寫與單空格變體
  - 例如 `按star排序` / `按stars排序` / `按 star 排序` / `按 stars 排序`
  - 可視為概念上等價於 `按\\s*stars?\\s*排序`

### 3.2 本輪不處理其他排序軸

iter11 **不處理**：

- `recent`
- `latest`
- `newest`
- `updated`
- `most forks`
- 任何未在 dataset 中明確出現、且不確定是否應映射到 `stars desc` 的排序語意
- query 有 ranking intent 但 parser 給了非 stars sort（例如 `updated`）的覆寫修正

若 query 含上述詞，本輪不新增任何 sort normalization。

### 3.3 不清空既有 sort/order

iter11 與 iter10 numeric policy 不同。

本輪若 query **沒有** ranking intent：

- 不新增 `sort/order`
- 但也**不主動清空** parser 已給的 `sort/order`

也就是 iter11 只補回缺失，不負責否定其他排序判斷。

若 query **有** ranking intent，但 parser 給了 non-stars `sort/order`
（例如 `updated`），iter11 也**不覆寫**；這類情況視為 parser drift，留後續處理。

## 4. 明確責任分界

iter11 **只處理**：

- `sort` / `order` 的 downstream normalization
- ranking intent detection
- `stars desc` 的 deterministic 補回

iter11 **不處理**：

- `keywords` 補回或 canonicalization
- `language`
- `min_stars` / `max_stars`
- `created_after` / `created_before`
- validator 規則改寫
- repair prompt / parser prompt wording

## 5. 設計方向

### 5.1 主策略

沿用 `validate_query` 的 normalization 階段，在 keyword / language / numeric
之後加入 **ranking normalization**，讓：

- runtime 最終 `structured_query.sort/order`
- validator 看到的 `sort/order`
- per-item artifact trace

全部共用同一套結果。

### 5.2 建議實作位置

建議只動：

- `src/gh_search/tools/validate_query.py`
- `tests/normalizers/test_ranking_intent.py`（新檔）
- `tests/test_tool_validate_query.py`

不動：

- `prompts/core/parse-v1.md`
- `prompts/appendix/parse-*.md`
- `src/gh_search/normalizers/keyword_rules.py`
- `src/gh_search/tools/parse_query.py`
- `src/gh_search/validator.py`
- `src/gh_search/tools/repair_query.py`
- `src/gh_search/eval/scorer.py`

### 5.3 建議插入層級

建議放在 [validate_query.py](/Users/chenweiqi/Documents/interview/gofreight/src/gh_search/tools/validate_query.py:55)
的 `_normalize_structured_query()` 內，在：

1. `normalize_keywords(...)`
2. `language` suppression
3. numeric normalization
4. **ranking normalization**

之後再進 validator。

示意：

```python
def _normalize_structured_query(
    sq: StructuredQuery,
    user_query: str,
) -> StructuredQuery:
    ...
    normalized_sort, normalized_order = _normalize_ranking(
        sort=sq.sort,
        order=sq.order,
        user_query=user_query,
    )
```

理由：

- iter11 處理的是 final structured facet，不是 parser prompt wording
- `user_query` 在 `validate_query(state)` 層最自然可得
- 對 GPT / CLA 多半是 idempotent；對 DSK 則補回穩定遺失欄位

## 6. 本輪要救回的題目

### 6.1 Primary target pairs

| qid | model | iter10 blocker | 預期 iter11 |
|---|---|---|---|
| q013 | DSK | `sort=None`, `order=None` | CORRECT |
| q015 | DSK | `sort=None`, `order=None` | CORRECT |
| q026 | DSK | `sort=None`, `order=None` | CORRECT |
| q027 | DSK | `sort=None`, `order=None` | CORRECT |

共 **4 個 primary target pairs**。

### 6.2 Bonus target

| qid | model | iter10 blocker | iter11 驗收方式 |
|---|---|---|---|
| q020 | GPT | `sort=None`, `order=None` | 若補成 `stars desc` 視為 bonus，不列硬門檻 |

### 6.3 Positive / guard set

iter11 必須證明沒有破壞既有正確 sort semantics。

至少觀察：

| qid | model | 必須維持 |
|---|---|---|
| q001 | GPT / CLA | `sort=stars`, `order=desc` |
| q013 | GPT / CLA | `sort=stars`, `order=desc` |
| q015 | GPT / CLA | `sort=stars`, `order=desc` |
| q018 | GPT / CLA / DSK | `sort=stars`, `order=desc` |
| q020 | CLA / DSK | `sort=stars`, `order=desc` |
| q025 | GPT / CLA / DSK | `sort=stars`, `order=desc` |
| q028 | GPT / CLA / DSK | `sort=stars`, `order=desc` |

另外必須保護：

- 沒有 ranking intent 的 query 不得被誤補 `stars desc`
- 本輪不得改動 `keywords` / `language` / `min_stars` / `max_stars`

### 6.4 預期增分

保守預期：

- GPT：`27/30 -> 27/30`（`q020 GPT` 只列 bonus，不計 headline）
- CLA：`29/30 -> 29/30`
- DSK：`24/30 -> 28/30`

DSK 若只回收 2 題，即可達到 `26/30`，超過 `85%`。

若 `q020 GPT` 的 stochastic drift 在 iter11 run 中仍維持 `sort=None`，iter11 lexicon
會將其補回 `stars desc`，因此 GPT 亦可能達到 `28/30`。

## 7. 驗證方法

### 7.1 Unit：ranking intent policy

至少新增以下測試：

- stars ranking intent -> `stars desc`
  - `popular TypeScript ORM libraries` -> `sort=stars`, `order=desc`
  - `trending rust projects` -> `sort=stars`, `order=desc`
  - `ranked by stars` -> `sort=stars`, `order=desc`
  - `sorted by stars` -> `sort=stars`, `order=desc`
  - `ui kit with lots of stars` -> `sort=stars`, `order=desc`
  - `repos with most stars` -> `sort=stars`, `order=desc`
  - `gimme top10 go repoz created aftr 2022!!!` -> `sort=stars`, `order=desc`
  - `按 star 排序` -> `sort=stars`, `order=desc`
  - `熱門的 python 爬蟲套件` -> `sort=stars`, `order=desc`

- no ranking intent -> do not invent sort/order
  - `vue 3 admin dashboard templates` + incoming `sort=None` -> stays `None`
  - `java spring boot starter projects from 2024` + incoming `sort=None` -> stays `None`

- do not clear existing sort/order
  - no ranking phrase + incoming `sort=updated`, `order=desc` -> keep as-is

- idempotence
  - incoming already `stars desc` + ranking query -> keep `stars desc`

### 7.2 Integration：validate_query snapshot

確認：

- integration test 應直接餵 raw parser fixture 的 `predicted_structured_query` 給
  `validate_query`，不重新呼叫 LLM
- `q013 DSK` 類 raw parse output 含 `sort=None`, `order=None`
  - downstream 後 `sort=stars`, `order=desc`
- `q015 DSK` 類 raw parse output 含 `sort=None`, `order=None`
  - downstream 後 `sort=stars`, `order=desc`
- `q026 DSK` 類 raw parse output 含 `sort=None`, `order=None`
  - downstream 後 `sort=stars`, `order=desc`
- `q027 DSK` 類 raw parse output 含 `sort=None`, `order=None`
  - downstream 後 `sort=stars`, `order=desc`
- `q020 GPT` 若同樣被補回 `stars desc`，視為 bonus

### 7.3 Guard：sort-only scope

iter11 應補 guard test，鎖住本輪只動 sort/order。

至少覆蓋：

- normalization 不得改動 `keywords`
- normalization 不得改動 `language`
- normalization 不得改動 `min_stars` / `max_stars`
- normalization 不得改動 date fields
- 沒有 ranking intent 的 query 不得被誤補 `stars desc`

### 7.4 Cross-model full smoke rerun

```bash
gh-search smoke --model gpt-4.1-mini    --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_gpt41mini_iter11_20260425
gh-search smoke --model claude-sonnet-4 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_claude_sonnet4_iter11_20260425
gh-search smoke --model DeepSeek-R1     --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_deepseek_r1_iter11_20260425
```

## 8. 通過標準

本輪採實質判準，通過需同時滿足：

1. §6.1 的 **4 個 primary target pairs** 至少回收 2 題，讓 DSK headline 達到 `26/30` 以上
2. 若 4 題皆回收，視為 full DSK recovery
3. §6.3 的 positive / guard set 不得出現新的 sort regression
4. `pytest -q` 全綠

### 8.1 完整達標

若 4/4 primary 全翻正，同時：

- GPT headline 不下降
- CLA headline 不下降
- DSK headline 達到 `24 -> 28`

則判定為 **完整達標**。

### 8.2 實質通過

若至少回收 2 個 DSK primary target，使 DSK 達到 `26/30` 以上，且差額可清楚歸因於：

- `q009 DSK` plural drift
- `q029 DSK` topic retention drift
- 其他 out-of-scope parser drift

且 **不是 iter11 patch 造成的新 sort regression**，可判為 **實質通過**。

## 9. 驗證不過時的調整順序

若驗證未過，依下列順序收斂：

1. 先確認失敗是否真的屬 ranking policy
   - 若是 keyword 缺詞、language、numeric、date，屬 out-of-scope
2. 若 `q013/q015/q026/q027 DSK` 仍缺 sort/order
   - 先檢查 ranking lexicon 是否漏了 `popular` / `trending` / `熱門` / `lots of stars`
3. 若沒有 ranking intent 的題被誤補 sort/order
   - 先縮窄 lexicon，不要擴 scope 去清理其他欄位
4. 若想為了救更多題去新增 `updated/latest` 類排序軸
   - 停止；那已經是新的 scope，不屬 iter11

## 10. Rollback 條件

符合任一條件就 rollback：

1. DSK 4 個 primary target 一題都沒回收
2. DSK headline 仍低於 `26/30`
3. 任一 §6.3 positive / guard case 出現新的 sort regression
4. 為了救題而開始修改 prompt / appendix
5. 為了救題而開始擴到 `updated/latest/recent` 等非 stars 排序軸
6. 為了救題而開始動 `keywords/language/numeric/date`

## 11. Handoff

iter11 後仍可能殘留的桶：

- `q009 DSK`
  - plural drift follow-up
- `q029 DSK`
  - topic retention residual
- `q018 GPT`
  - parser drift / date residual
- `q029 CLA`
  - topic retention residual

若 iter11 shipped，下一輪優先順序建議為：

1. plural drift 小修
2. parser-retention 尾巴（`q018 GPT` / `q029 CLA` / `q029 DSK`）
