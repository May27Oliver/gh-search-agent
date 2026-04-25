# Iteration 8 Multilingual Canonicalization Spec

## 1. 目標

本輪 tuning 的單一目標是把 **CJK / Japanese keyword canonicalization** 下放到
deterministic downstream，修正 parser 輸出的中日文複合詞、語境化描述詞與英文
canonical keyword 之間的對齊問題。

iter8 延續 `ITER5_NOTES §6` 與 iter6 / iter7 的策略：

- **不擴寫** `prompts/core/parse-v1.md`
- **不動** parser prompt / appendix prompt
- 優先把 dataset-backed multilingual rewrite 放到 `keyword_rules.py`

本輪主題只做：

- 中文複合詞 / 單詞 canonicalization
- 日文 sample-project pattern 的 narrow contextual cleanup
- runtime / scorer / trace 共用同一份 multilingual normalization

## 2. 背景

iter7 shipped baseline（`eval_*_iter7_20260425`）後，剩餘失分已明確分桶：

1. **CJK / 多語 keyword canonicalization**
2. language over-inference residual
3. sort defaults / ranking intent
4. stars boundary / repair contract
5. 小量 plural / date 尾巴

本輪只做 ROI 最高、且已在 iter7 handoff 明確 deferred 的第 1 桶。

### 2.1 iter7 baseline 中可直接由 multilingual canonicalization 吃回的題目

| qid | model | iter7 pred | 若做 multilingual cleanup 後 |
|---|---|---|---|
| q027 | GPT | `['scraping', '套件']` | 翻正 |
| q027 | CLA | `['scraping', '套件']` | 翻正 |
| q028 | GPT | `['微服务框架']` | 翻正 |
| q029 | DSK | `['react', 'sample', 'project', 'japanese']` | 翻正 |

共 **4 個 primary target pairs**。

### 2.2 contract-only / secondary cases

| qid | model | iter7 pred | 為何不列 primary |
|---|---|---|---|
| q027 | DSK | `['爬蟲套件']`，且 `sort/order=null` | multilingual 修掉 keywords 後仍卡 sort default |
| q029 | GPT | `['react', 'サンプルプロジェクト']`，且 `language='JavaScript'` | multilingual 修掉 keywords 後仍卡 language over-inference |
| q029 | CLA | `['japanese', 'sample', 'project']`，且 `language='JavaScript'`、缺 `react` | multilingual cleanup 可減少 noise，但仍非完整 correct |

### 2.3 明確不在本輪處理

- `React` / `Vue` 誤升格為 `language`（iter9）
- `templates -> template`（plural drift follow-up）
- `popular` / `trending` -> `sort=stars`（iter9）
- `q018 GPT created_before=null`
- `q013` / `q020` / `q030` 的 numeric boundary / repair 問題
- 全域 `project` / `japanese` stopword promotion

## 3. 單一判定原則

iter8 只收 **dataset-backed multilingual canonicalization / contextual drop**。

### 3.1 本輪只收 dataset 已證明需要的模式

本輪 core multilingual patterns 僅限：

- `爬蟲套件` -> `scraping`, `crawler`
- `scraping` + `套件` -> `scraping`, `crawler`（**order-insensitive**；只要兩者同時存在即觸發）
- `微服务框架` -> `microservice`, `framework`
- `サンプルプロジェクト` -> `sample`
- 當 keywords **同時包含** `sample` **AND** `project` **AND** `japanese`
  三者時，drop `project` 與 `japanese`（其他 token 如 `react` 不影響觸發）

其中最後一條是 **narrow contextual cleanup**，不是把 `project` / `japanese`
升成全域 stopword。

### 3.2 不做全域升格

下列 token 在 iter8 **不得**升為全域 alias / stopword：

- `套件` -> `crawler`
- `project` -> stopword
- `japanese` -> stopword

原因：

- `套件` 在一般 query 中可能只是 package / toolkit，不一定等於 `crawler`
- `project` / `japanese` 在一般 query 中可能是 topic-bearing token
- dataset 只支持在 q027 / q029 的狹窄語境下做 rewrite / drop

### 3.3 單一共享入口

iter8 仍遵守 iter2 / iter4 / iter7 的 single-source-of-truth contract：

- `normalize_keywords`
- `find_keyword_violations`

必須共用同一份 multilingual rewrite / drop 規則，不能讓 runtime、scorer、trace
各自有一套。

## 4. 明確責任分界

iter8 **只處理**：

- `keywords` 的 multilingual canonicalization
- multilingual contextual cleanup
- downstream deterministic normalization
- shared runtime / scorer / validator normalization 一致性

iter8 **不處理**：

- parser prompt wording
- parser topic retention（例如 `q029 CLA` 缺 `react`）
- `language` 欄位清除
- sort defaults
- stars boundary
- repair / contradiction contract

## 5. 設計方向

### 5.1 主策略

沿用既有 keyword normalization pipeline，在 `keyword_rules.py` 新增 **shared
multilingual rewrite helper**，讓：

- runtime normalized keywords
- scorer canonicalization
- trace / validator input

全部共用同一套 multilingual cleanup 結果。

### 5.2 建議實作位置

建議只動：

- `src/gh_search/normalizers/keyword_rules.py`
- `tests/normalizers/test_keyword_rules.py`
- `tests/test_tool_validate_query.py`（若現有 integration tests 蓋不到）

不動：

- `prompts/core/parse-v1.md`
- `prompts/appendix/parse-*.md`
- `src/gh_search/tools/parse_query.py`
- `src/gh_search/validator.py`
- `src/gh_search/eval/scorer.py`

### 5.3 建議插入層級

本輪不新增第二套 cleanup pipeline。

建議做法：

1. 在 `keyword_rules.py` 內新增 shared multilingual helper
2. 由 `normalize_keywords` 與 `find_keyword_violations` 共用
3. placement 以 **Stage 1 canonicalization 後、Stage 5 phrase merge 前** 為主

理由：

- `微服务框架` / `爬蟲套件` / `サンプルプロジェクト` 都不是單純 plural / stopword
- 需要在 canonical token bag 上做 rewrite / narrow contextual drop
- rewrite 後輸出的 `sample` / `crawler` / `microservice` / `framework` 都已是
  canonical 英文 token，不應再保留原 CJK token 進入後續 stage
- 又不能把 multilingual 邏輯散落到 validator / scorer

## 6. 本輪要救回的題目

### 6.1 Primary target pairs

| qid | model | iter7 blocker | 預期 iter8 |
|---|---|---|---|
| q027 | GPT | `套件` 未對齊 `crawler` | CORRECT |
| q027 | CLA | `套件` 未對齊 `crawler` | CORRECT |
| q028 | GPT | `微服务框架` 未拆成 `microservice/framework` | CORRECT |
| q029 | DSK | `project` / `japanese` multilingual noise | CORRECT |

共 **4 個 primary target pairs**。

### 6.2 Contract-only targets

| qid | model | iter7 blocker | iter8 驗收方式 |
|---|---|---|---|
| q027 | DSK | `爬蟲套件` + `sort/order=null` | 只檢查 multilingual keywords 是否對齊，不要求整題翻正 |
| q029 | GPT | `サンプルプロジェクト` + `language='JavaScript'` | 只檢查 multilingual keywords 是否對齊 `['react', 'sample']` |

### 6.3 Secondary / deferred

| qid | model | 狀態 |
|---|---|---|
| q029 | CLA | multilingual cleanup 後仍會缺 `react` 且卡 language，留 iter9 |
| q001 | GPT | language over-inference residual，留 iter9 |
| q009 | GPT / DSK | language over-inference + plural drift，留 iter9 / follow-up |

### 6.4 預期增分

iter8 主版只依賴 primary target 與 contract-only target，不把 `q029 CLA` 的 partial
cleanup 算進 success criteria。

保守預期：

- GPT：`23/30 -> 25/30`（`q027`、`q028` 翻正；`q029 GPT` 只驗 contract，不計 headline）
- CLA：`26/30 -> 27/30`（`q027` 翻正）
- DSK：`23/30 -> 24/30`（`q029` 翻正；`q027 DSK` 只驗 contract，仍卡 sort）

## 7. 驗證方法

### 7.1 Unit：keyword_rules multilingual cleanup

至少新增以下測試：

- `['scraping', '套件'] -> ['scraping', 'crawler']`
- `['爬蟲套件'] -> ['scraping', 'crawler']`
- `['微服务框架'] -> ['microservice', 'framework']`
- `['react', 'サンプルプロジェクト'] -> ['react', 'sample']`
- `['react', 'sample', 'project', 'japanese'] -> ['react', 'sample']`

guard cases：

- `['套件']` 維持原樣（鎖住不得把 `套件` 升成全域 `crawler`）
- `['project']` 維持原樣（鎖住不得升成全域 stopword）
- `['japanese']` 維持原樣（鎖住不得升成全域 stopword）
- `['sample', 'project']` 維持原樣（沒 `japanese` 不得觸發 contextual drop）
- `['sample', 'japanese']` 維持原樣（沒 `project` 不得觸發 contextual drop）
- `['project', 'japanese']` 維持原樣（沒 `sample` 不得觸發 contextual drop）
- `['microservice', 'framework']` 不受影響
- `['react', 'sample']` 不受影響

### 7.2 Integration：validate_query snapshot

確認：

- q027 類 raw parse output 含 `套件` / `爬蟲套件`
  - downstream 後 `structured_query.keywords` 對齊 `scraping/crawler`
- q028 GPT raw parse output 含 `微服务框架`
  - downstream 後對齊 `microservice/framework`
- q029 GPT / DSK raw parse output 含 `サンプルプロジェクト` 或 `project+japanese`
  - downstream 後 keywords 對齊 `react/sample`
- scorer 與 runtime 使用同一 canonicalization 結果

### 7.3 Shared-contract：find_keyword_violations

iter8 必須補 multilingual contract 測試，確保 `find_keyword_violations` 與
`normalize_keywords` 對同一 raw token 看法一致。

至少覆蓋：

- `['微服务框架']` 會被報成 multilingual rewrite
- `['爬蟲套件']` 會被報成 multilingual rewrite
- `['react', 'sample', 'project', 'japanese']` 中 `project` / `japanese`
  會被報成 contextual multilingual drop

是否使用新 issue code（例如 `multilingual_canonicalization`,
`multilingual_context_drop`）可由實作決定；但 contract test 必須鎖死：

- **被 rewrite / drop 的 token 集**
- **與 `normalize_keywords` 最終結果一致**

### 7.4 Cross-model full smoke rerun

```bash
gh-search smoke --model gpt-4.1-mini    --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_gpt41mini_iter8_20260425
gh-search smoke --model claude-sonnet-4 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_claude_sonnet4_iter8_20260425
gh-search smoke --model DeepSeek-R1     --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_deepseek_r1_iter8_20260425
```

## 8. 通過標準

本輪採實質判準，通過需同時滿足：

1. §6.1 的 **4 個 primary target pairs 全部翻正**
2. §6.2 的兩個 contract-only target 都成立
3. 不引入新的 **non-multilingual** keyword regression
4. DeepSeek headline accuracy 不得下降超過 2 題
5. `pytest -q` 全綠

> DeepSeek `±2` 內波動的 noise 判讀屬程序，沿用 `ITER5_NOTES §1.2`，不列為達標條件。

### 8.1 完整達標

若 4/4 primary target 全翻正，且兩個 contract-only target 成立，三模型 headline
均不下降，**且至少達到 §6.4 的保守預期增分**，則判定為 **完整達標**。

### 8.2 實質通過

若有 1 個 primary target 因 out-of-scope blocker 未翻正，但 multilingual keyword side
已正確，且沒有新增 regression，則可判定為 **實質通過**，前提是 spec 內要明確寫出
阻塞欄位不屬 iter8。

## 9. 驗證不過時的調整順序

1. **先查 target-pair per-item diff**
   - 確認 primary target 沒翻正時，阻塞欄位是否真的是 multilingual side
2. **若 rewrite 不生效**
   - 檢查 multilingual helper 是否只有 `normalize_keywords` 看得到，
     `find_keyword_violations` / scorer 沒共用
3. **若 guard case 被打壞**
   - 先收窄 contextual 條件，不可把 `project` / `japanese` / `套件`
     升成全域規則
4. **若 DSK headline 在 ±2 內波動**
   - 依 `ITER5_NOTES §1.2` 當 noise candidate 判讀，不直接算迭代失敗
5. **若 primary target < 3/4**
   - 視為本輪 spec / implementation 邏輯未收斂，應 rollback

## 10. Rollback 條件

符合任一即 rollback：

1. §6.1 的 primary target 少於 3/4 翻正
2. `q027 DSK` 或 `q029 GPT` 的 contract-only target 任一未成立
3. 新增 2 題以上 non-multilingual keyword regression
4. 為了救 q027 / q029 而把 `套件`、`project`、`japanese` 升成全域 alias / stopword
5. 任何實作需要修改 `prompts/core/parse-v1.md`

## 11. 交接

若 iter8 shipped，剩餘題目可再分三桶：

1. **iter9：language over-inference residual**
   - `q001 GPT`
   - `q009 GPT / DSK`
   - `q029 GPT / CLA`
2. **iter9 / iter10：sort defaults / ranking intent**
   - `q001 DSK`
   - `q010 DSK`
   - `q027 DSK`
   - `q020` / `q030`
3. **small follow-up**
   - `q009 DSK templates -> template`
   - `q018 GPT created_before`

iter8 不應順手把這些問題一起收進來。
