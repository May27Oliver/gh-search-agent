# Iteration 10 Stars / Numeric Semantics Spec

## 1. 目標

本輪 tuning 的單一目標是把 **stars / numeric evidence semantics**
下放到 deterministic downstream，修正 parser / model 在 `min_stars` /
`max_stars` 上的三種殘留錯誤：

- **exclusive boundary drift**
  - 例如 `over 500` 被吐成 `500`，正確應為 `501`
- **numeric hallucination**
  - 例如 `lots of stars` / `popular stuff` 被硬塞 `min_stars`
- **contradictory range rewriting**
  - 例如 `超過 500 但少於 100` 被交換成看似合理的 `100..500`

iter10 延續 iter6 - iter9 的策略：

- **不擴寫** `prompts/core/parse-v1.md`
- **不動** parser prompt / appendix prompt
- 優先把 dataset-backed numeric evidence policy 放到 downstream

本輪所有 numeric ground truth 一律對齊
`datasets/eval_dataset_reviewed.json`，**不是** `candidate_dataset`。

## 2. 背景

iter9 shipped baseline（`eval_*_iter9_rerun_20260425`）後，剩餘失分已收斂成：

1. stars / numeric semantics
2. DSK sort-default drift / noise
3. 小量 plural / parser drift / date 尾巴

本輪只做第 1 桶。

### 2.1 iter9 baseline 中仍可直接由 numeric normalization 吃回的題目

| qid | model | iter9 blocker | 預期 iter10 |
|---|---|---|---|
| q013 | CLA | `min_stars=500`，應為 `501` | CORRECT |
| q020 | DSK | 憑空多出 `min_stars=100` | CORRECT |
| q026 | GPT | 憑空多出 `min_stars=1` | CORRECT |

共 **3 個 primary target pairs**。

### 2.2 contract-only / secondary cases

| qid | model | iter9 blocker | 為何不列 primary |
|---|---|---|---|
| q030 | GPT | `100..500`，應保留 `501..99` | 這題帶有刻意矛盾區間；iter10 只保證 numeric contract，不承諾 validator / repair 行為 |
| q030 | CLA | `100..500`，應保留 `501..99` | 同上 |
| q030 | DSK | `99..501`，應保留 `501..99` | 同上 |

### 2.3 明確不在本輪處理

- `q013` / `q015 DSK` 的 `sort/order=null`
- `q027 DSK` 的 `sort/order=null`
- `q009 GPT / DSK` 的 topic retention / plural drift
- `q018 GPT` 的 `created_before=null` 與 `spring boot` 缺失
- `q029 CLA` 的 `react` topic retention
- 任何 prompt-level stars / ranking guard
- 任何 repair loop / validator policy 改寫

## 3. 單一判定原則

iter10 只保留 **user query 明示支持** 的 numeric filters，並嚴格保留比較詞的語意。

### 3.1 明示 numeric evidence 規則

只有當 `user_query` 明確出現數字 + comparator 證據時，才允許保留或改寫
`min_stars` / `max_stars`。

iter10 的 numeric normalization 應採 **query-driven rewrite**，不是只依賴
incoming `min_stars` / `max_stars` 做局部修補。也就是：

- query 有明示 comparator + number -> 不論 parser 原本有沒有給值，都依 query 內容**重算**對應 boundary
- query 沒有明示 number -> 即使 parser 吐了 `min_stars/max_stars`，也應清掉
- normalization 不新增 ranking / sort 推論，只收斂 numeric facets

若 query 只有：

- `popular`
- `lots of stars`
- `trending`
- `high-star`

這類 ranking / popularity 訊號，**不得**單獨推出任何 numeric threshold。

本輪這條規則只鎖 dataset 內已出現的 vague popularity terms。
CJK 等價詞若**沒有**明示 numeric comparator（例如單獨的 `熱門` / `受歡迎`），
不在 iter10 額外擴寫 enforce；若與明示 numeric comparator 並存（例如 `熱門` +
`超過 1000`），仍按 numeric comparator 正常計算。

換句話說：

- `popular stuff on github` -> 只能影響 `sort=stars desc`，不能產生 `min_stars`
- `rect native ui kit with lots of stars` -> 只能影響 `sort=stars desc`，不能產生 `min_stars`

### 3.2 comparator 語意必須嚴格保留

iter10 應以 deterministic 規則重算 numeric boundaries。

至少覆蓋本 dataset 已出現的比較詞：

| query phrase | semantic | normalized result |
|---|---|---|
| `over N` / `more than N` / `超過 N` | exclusive lower bound | `min_stars = N + 1` |
| `under N` / `less than N` / `少於 N` | exclusive upper bound | `max_stars = N - 1` |
| `min N` / `minimum N` | inclusive lower bound | `min_stars = N` |
| `max N` / `maximum N` | inclusive upper bound | `max_stars = N` |

本輪也應相容既有 parser 常見表達：

| query phrase | semantic | normalized result |
|---|---|---|
| `at least N` / `>= N` | inclusive lower bound | `min_stars = N` |
| `at most N` / `<= N` | inclusive upper bound | `max_stars = N` |
| `> N` | exclusive lower bound | `min_stars = N + 1` |
| `< N` | exclusive upper bound | `max_stars = N - 1` |

numeric evidence 必須**錨在 stars context** 上，不能只因 query 中出現數字就觸發。
實作上至少應滿足：

- comparator + number 需與 `star` / `stars` / `starz` / `星` 位於同一 clause
- 不得把 `limit`、年份、或其他非 stars 數字誤當成 numeric threshold

例如：

- `find me 20 popular TypeScript ORM libraries with more than 2k stars`
  - 只允許 `more than 2k stars -> min_stars=2001`
  - 不得誤把 `20` 當成 stars threshold

數字 token 應支援：

- plain integer：`500`
- abbreviated suffix：`10k -> 10000`
- CJK mixed query：`超過 500`、`少於 100`

本輪**不要求**覆蓋：

- decimal suffix：`1.5k`
- comma-separated：`1,000`
- `M` / `m` suffix

### 3.3 矛盾區間必須保留，不可自動修正

若 query 明示了互相衝突的條件，例如：

- `超過 500 但少於 100`

iter10 必須保留原始語意：

- `min_stars = 501`
- `max_stars = 99`

不得：

- 交換成 `99..501`
- 放寬成 `100..500`
- 自動移除其中一邊
- 根據常識修成「比較合理」的區間

這與 [eval_dataset_reviewed.json](/Users/chenweiqi/Documents/interview/gofreight/datasets/eval_dataset_reviewed.json:1)
中 `q030` 的 reviewer note 一致：

- 保留原始衝突條件
- 交由 validator / repair / failure analysis 處理

iter10 也**不檢查** numeric range 的可解性或合理性；只保留 deterministic
計算結果。換句話說，即使 normalize 後得到 `min_stars > max_stars`，也不在
iter10 自動修正，仍交由 validator / repair 處理。

### 3.4 iter10 不處理 sort / ranking defaults

若 query 有：

- `popular`
- `trending`
- `ranked by stars`

這些語意仍可由既有路徑處理 `sort` / `order`，但 iter10 **不以此為目標欄位**，
也不為了修 `q013/q015 DSK` 去碰 sort-default policy。

## 4. 明確責任分界

iter10 **只處理**：

- `min_stars` / `max_stars` 的 downstream normalization
- explicit numeric evidence detection
- exclusive / inclusive comparator semantics
- contradictory range preservation

iter10 **不處理**：

- `sort` / `order` 補回
- keyword 補回或 canonicalization
- language suppression
- multilingual / plural drift
- validator 規則改寫
- repair prompt / parser prompt wording

## 5. 設計方向

### 5.1 主策略

沿用 `validate_query` 的 normalization 階段，在 keyword / language 之後加入
**numeric evidence normalization**，讓：

- runtime 最終 `structured_query.min_stars/max_stars`
- validator 看到的 numeric filters
- per-item artifact trace

全部共用同一套結果。

### 5.2 建議實作位置

建議只動：

- `src/gh_search/tools/validate_query.py`
- `tests/normalizers/test_numeric_evidence.py`（新檔）
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
3. **numeric evidence normalization**

之後再進 validator。

示意：

```python
def _normalize_structured_query(
    sq: StructuredQuery,
    user_query: str,
) -> StructuredQuery:
    ...
    normalized_min_stars, normalized_max_stars = _normalize_star_bounds(
        min_stars=sq.min_stars,
        max_stars=sq.max_stars,
        user_query=user_query,
    )
```

理由：

- iter10 處理的是 final structured facet，不是 parser prompt wording
- `user_query` 只有在 `validate_query(state)` 這層最自然可得
- 可以在進 semantic validation 前就固定最終 numeric semantics

## 6. 本輪要救回的題目

### 6.1 Primary target pairs

| qid | model | iter9 blocker | 預期 iter10 |
|---|---|---|---|
| q013 | CLA | `min_stars=500`，應為 `501` | CORRECT |
| q020 | DSK | `min_stars=100`，gt `None` | CORRECT |
| q026 | GPT | `min_stars=1`，gt `None` | CORRECT |

共 **3 個 primary target pairs**。

### 6.2 Contract-only targets

| qid | model | iter9 blocker | iter10 驗收方式 |
|---|---|---|---|
| q030 | GPT | `100..500` | 只檢查 `validate_query` 後的 numeric fields 被改成 `501..99`，不要求整題翻正 |
| q030 | CLA | `100..500` | 只檢查 `validate_query` 後的 numeric fields 被改成 `501..99`，不要求整題翻正 |
| q030 | DSK | `99..501` | 只檢查 `validate_query` 後的 numeric fields 被改成 `501..99`，不要求整題翻正 |

### 6.3 Positive / guard set

iter10 必須證明沒有破壞既有正確 numeric semantics。

至少觀察：

| qid | model | 必須維持 |
|---|---|---|
| q013 | GPT | `min_stars=501`, `max_stars=9999` |
| q013 | DSK | `min_stars=501`, `max_stars=9999`（即使仍卡 sort） |
| q011 | GPT / CLA / DSK | `min_stars=1000` |
| q015 | GPT / CLA / DSK | `min_stars=2001` |
| q017 | GPT / CLA / DSK | `max_stars=99` |
| q020 | GPT / CLA | `min_stars=None`, `max_stars=None` |
| q024 | GPT / CLA / DSK | `min_stars=500` |
| q027 | GPT / CLA / DSK | `min_stars=1001` |
| q026 | CLA / DSK | `min_stars=None`, `max_stars=None` |

### 6.4 預期增分

保守預期：

- GPT：`26/30 -> 27/30`（`q026` 翻正）
- CLA：`27/30 -> 28/30`（`q013` 翻正）
- DSK：`25/30 -> 26/30`（`q020` 翻正）

`q030` 三模型只驗 numeric contract，不計 headline。

## 7. 驗證方法

### 7.1 Unit：numeric evidence policy

至少新增以下測試：

- exclusive lower bound
  - `over 500 stars` -> `min_stars=501`
  - `more than 2k stars` -> `min_stars=2001`
  - `超過 500 star` -> `min_stars=501`

- exclusive upper bound
  - `under 10k stars` -> `max_stars=9999`
  - `less than 100 stars` -> `max_stars=99`
  - `少於 100 stars` -> `max_stars=99`

- inclusive lower bound
  - `min 500 starz` -> `min_stars=500`
  - `at least 1000 stars` -> `min_stars=1000`

- inclusive upper bound
  - `max 500 stars` -> `max_stars=500`
  - `at most 100 stars` -> `max_stars=100`

- vague popularity must not create numeric filters
  - `popular stuff on github` + incoming `min_stars=100` -> clear to `None`
  - `ui kit with lots of stars` + incoming `min_stars=1` -> clear to `None`

- stars-context anchoring
  - `find me 20 popular TypeScript ORM libraries with more than 2k stars`
    + incoming `min_stars=20` -> normalized to `2001`
  - 同題 + correct incoming `min_stars=2001` -> 維持 `2001`

- contradictory range must be preserved
  - `超過 500 但少於 100 的 rust 專案`
    + incoming `100..500` -> normalized to `501..99`
  - 同題 + incoming `99..501` -> normalized to `501..99`

- idempotence
  - 已正確的 `501..9999` 經過 normalization 後維持不變
  - 已正確的 `2001..None` 維持不變

### 7.2 Integration：validate_query snapshot

確認：

- integration test 應直接餵 raw parser fixture 的 `predicted_structured_query` 給
  `validate_query`，不重新呼叫 LLM
- `q030` 的 contract 驗收以 **`validate_query` 回傳的 normalized `structured_query`**
  為準，不以 smoke 的最終 `final_outcome` / headline 為準；因為此題目前可能在
  repair loop 中走到 `max_turns_exceeded`
- `q013 CLA` 類 raw parse output 含 `min_stars=500`
  - downstream 後 `min_stars=501`
- `q024` 類 raw parse output 若含 `min_stars=500`
  - downstream 後仍維持 `min_stars=500`
- `q020 DSK` 類 raw parse output 含 `min_stars=100`
  - downstream 後 `min_stars=None`
- `q026 GPT` 類 raw parse output 含 `min_stars=1`
  - downstream 後 `min_stars=None`
- `q030 GPT/CLA/DSK` 類 raw parse output
  - downstream 後 numeric fields 對齊 `501..99`

### 7.3 Guard：numeric-only scope

iter10 應補 guard test，鎖住本輪只動 numeric semantics。

至少覆蓋：

- normalization 不得改動 `keywords`
- normalization 不得改動 `language`
- normalization 不得改動 `sort` / `order`
- `popular` / `trending` 只靠既有路徑處理，不得被 iter10 誤轉成 numeric threshold
- `q011/q017/q024/q027` 這類已正確 numeric 題不得被 iter10 誤清或誤改

### 7.4 Cross-model full smoke rerun

```bash
gh-search smoke --model gpt-4.1-mini    --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_gpt41mini_iter10_20260425
gh-search smoke --model claude-sonnet-4 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_claude_sonnet4_iter10_20260425
gh-search smoke --model DeepSeek-R1     --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_deepseek_r1_iter10_20260425
```

## 8. 通過標準

本輪採實質判準，通過需同時滿足：

1. §6.1 的 **3 個 primary target pairs 全部翻正**
2. §6.2 的 contract-only targets：
   - `q030 GPT / CLA / DSK` 的 numeric fields 全部對齊 `501..99`
3. §6.3 的 positive / guard set 不得出現新的 numeric regression
4. `pytest -q` 全綠

### 8.1 完整達標

若 3/3 primary 全翻正，且 `q030` 三模型 contract 全成立，同時：

- GPT headline 達到 `26 -> 27`
- CLA headline 達到 `27 -> 28`
- DSK headline 達到 `25 -> 26`

則判定為 **完整達標**。

### 8.2 實質通過

若 primary / contract 全命中，但 headline 未完全達到 §6.4，只要差額可清楚歸因於：

- parser drift
- out-of-scope keyword missing
- DSK 既有 sort-default noise
- `q030` 既有 validator / repair 行為

且 **不是 iter10 patch 造成的新 numeric regression**，可判為 **實質通過**。

其中 `q030` 若在 integration contract 已成立，但 smoke 仍因 repair loop / validator
互動而未反映到 headline，應優先視為 **headline 外因素**，不得直接判 iter10 失敗。

## 9. 驗證不過時的調整順序

若驗證未過，依下列順序收斂：

1. 先確認失敗是否真的屬 numeric policy
   - 若是 `sort/order`、keyword 缺詞、language 漂移，屬 out-of-scope
2. 若 `q020` / `q026` 仍有 hallucinated threshold
   - 先檢查是否誤把 `popular` / `lots of stars` / `trending` 當 numeric evidence
3. 若 `q013` / `q030` 的 boundary 仍錯
   - 先修 comparator exclusivity、`k` suffix、CJK comparator parsing
4. 若為了救 `q030` 想開始自動修正矛盾區間
   - 停止；那已經是 repair / contradiction policy，不屬 iter10
5. 若為了救 `q013/q015 DSK` 去碰 sort defaults
   - 停止；那是 DSK investigation scope，不屬 iter10

## 10. Rollback 條件

符合任一條件就 rollback：

1. `q013 CLA`、`q020 DSK`、`q026 GPT` 任一未翻正，且原因是 numeric normalization 本身
2. `q030 GPT / CLA / DSK` 任一 contract 不成立
3. 任一 §6.3 positive / guard case 出現新的 numeric regression
4. 為了救題而開始修改 prompt / appendix
5. 為了救題而開始自動「修正」矛盾區間
6. 為了救 `q013/q015/q027 DSK` 而擴 scope 去碰 sort-default policy

## 11. Handoff

iter10 後仍可能殘留的桶：

- `q013 / q015 / q027 DSK`
  - sort defaults / ranking intent / provider drift
- `q009 DSK`
  - plural drift follow-up
- `q018 GPT`
  - parser drift / date residual
- `q029 CLA`
  - topic retention residual

若 iter10 shipped，下一輪優先順序建議為：

1. DSK sort-default investigation
2. plural drift 小修
3. `q018 GPT` / `q029 CLA` 類 parser-retention 尾巴

## 12. 實作順序

iter10 建議按 TDD 收斂：

1. 先寫 `tests/normalizers/test_numeric_evidence.py`
   - exclusive lower / upper（含 `k` suffix、CJK）
   - vague popularity 不得注入 numeric
   - 矛盾區間保留 `501..99`
   - idempotence
2. 再擴 `tests/test_tool_validate_query.py`
   - 用 raw parser fixture 餵 `validate_query`
   - 覆蓋 `q013 CLA`、`q020 DSK`、`q026 GPT`
   - 覆蓋 `q030` 三模型 contract-only 驗收
3. 補 guard tests
   - `keywords` / `language` / `sort` / `order` 不得被 iter10 動到
4. 再實作 `_normalize_star_bounds(...)`，並接入 `_normalize_structured_query()` 第三步
5. `pytest -q` 全綠後，再跑 §7.4 的三模型 smoke rerun
