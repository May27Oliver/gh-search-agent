# Iteration 7 Decoration Cleanup Spec

## 1. 目標

本輪 tuning 的單一目標是把 **English decoration token cleanup** 下放到
deterministic downstream，清掉會污染 `keywords` 但不承載主題語意的英文裝飾詞。

iter7 延續 iter6 / ITER5_NOTES §6 的策略：

- **不擴寫** `prompts/core/parse-v1.md`
- **不動** parser prompt / appendix prompt
- 優先把可 deterministic 做的 cleanup 放到 `keyword_rules.py`

本輪主題只做：

- `implementations`
- `projects`

可選 secondary 觀察：

- `project`（不列 primary success criteria）

## 2. 背景

iter6 shipped baseline（`eval_*_iter6_fix_20260425`）後，殘留的 over-extracted
token 可分三桶：

1. **DEC**：英文 decoration token
2. **PLU**：plural drift
3. **CJK**：multilingual canonicalization / drop

本輪只做最乾淨的一桶：**DEC**。

### 2.1 iter6 baseline 仍可直接由 decoration cleanup 吃回的題目

| qid | model | iter6 pred | 若清 decoration 後 |
|---|---|---|---|
| q007 | GPT | `['graphql', 'server', 'implementations']` | 翻正 |
| q007 | CLA | `['graphql', 'server', 'implementations']` | 翻正 |
| q007 | DSK | `['graphql', 'server', 'implementations']` | 翻正 |
| q018 | DSK | `['spring boot', 'starter', 'projects']` | 翻正 |

共 **4 個 primary target pairs**。

### 2.2 contract-only / secondary cases

| qid | model | iter6 pred | 為何不列 primary |
|---|---|---|---|
| q018 | GPT | `['starter', 'projects']`, 且 `created_before=null` | 去掉 `projects` 後仍卡 date blocker |
| q029 | CLA | `['japanese', 'sample', 'project']` | `project` 去掉後仍缺 `react` / `japanese` |
| q029 | DSK | `['react', 'sample', 'japanese']` | 若去 `japanese` 可翻正，但 `japanese` 不列 iter7 core |

### 2.3 明確不在本輪處理

- `templates -> template`（plural drift，留 follow-up / 另開）
- `japanese` 全域 stopword（generalization risk，留 iter8 或 narrow rule）
- `微服务框架`
- `サンプルプロジェクト`
- `repos`
- `stuff`

## 3. 單一判定原則

iter7 只移除 **不承載主題語意的 decoration token**。

### 3.1 本輪 core stopword set

本輪只把以下 token 納入 core decoration stopword：

- `implementations`
- `projects`

### 3.2 `project` 的處理

`project` 是 optional secondary，不進 iter7 primary core set。

理由：

- 在 q029 CLA 它看起來像 decoration
- 但一般化到真實世界 query，`project` 可能仍是 topic-bearing token
- dataset 目前不足以支持把它升為全域 stopword

因此：

- iter7 主版不依賴 `project`
- 若 iter7 主版穩定，且後續要嘗試 `project`，只能作為 follow-up / narrow rule

### 3.3 `japanese` 的處理

`japanese` **不進 iter7 core stopword**。

理由：

- 在 q029 它是內容語言描述，對 dataset 而言屬 decoration
- 但在一般 query 中，`japanese` 也可能是真 topic
- 將其升為全域 stopword generalization 風險過高

因此 `japanese` 明確 deferred 到 iter8 multilingual / narrow contextual rule。

## 4. 明確責任分界

iter7 **只處理**：

- `keywords` 的 decoration token cleanup
- downstream deterministic canonicalization
- shared runtime / scorer / validator normalization 一致性

iter7 **不處理**：

- parser prompt wording
- plural drift（`templates -> template`）
- multilingual canonicalization（`japanese`, `微服务框架`, `サンプルプロジェクト`）
- language over-inference
- sort defaults
- stars boundary
- validator / repair contract

## 5. 設計方向

### 5.1 主策略

沿用既有 keyword normalization pipeline，在 `keyword_rules.py` 新增 decoration
stopword，讓：

- runtime normalized keywords
- scorer canonicalization
- trace / validator input

全部共用同一套 cleanup 結果。

### 5.2 建議實作位置

建議只動：

- `src/gh_search/normalizers/keyword_rules.py`
- `tests/normalizers/test_keyword_rules.py`
- 如需要，補對應 integration tests

不動：

- `prompts/core/parse-v1.md`
- `prompts/appendix/parse-*.md`
- `src/gh_search/tools/parse_query.py`
- `src/gh_search/validator.py`
- `src/gh_search/eval/scorer.py`

### 5.3 建議插入層級

以現有 `normalize_keywords()` pipeline 來看，本輪 decoration token 應落在
**既有 single-token stopword cleanup 層**，不要新建另一層專門處理 decoration。

理由：

- `implementations` / `projects` 都是單 token
- 不需要新 bag-level logic
- 最不容易引入 order / stage drift

## 6. 本輪要救回的題目

### 6.1 Primary target pairs

| qid | model | iter6 blocker | 預期 iter7 |
|---|---|---|---|
| q007 | GPT | `implementations` | CORRECT |
| q007 | CLA | `implementations` | CORRECT |
| q007 | DSK | `implementations` | CORRECT |
| q018 | DSK | `projects` | CORRECT |

共 **4 個 primary target pairs**。

### 6.2 Contract-only target

| qid | model | iter6 blocker | iter7 驗收方式 |
|---|---|---|---|
| q018 | GPT | `projects` + `created_before=null` | 只檢查 `projects` 是否被清掉，不要求整題翻正 |

### 6.3 Secondary / deferred

| qid | model | 狀態 |
|---|---|---|
| q029 | CLA | 若未來引入 `project` narrow rule 才觀察 |
| q029 | DSK | 若未來引入 `japanese` narrow rule 才觀察 |
| q009 | GPT / DSK | `templates` plural drift，不在 iter7 |

### 6.4 預期增分

iter7 主版只依賴 primary target 與 contract-only target，不把 `q029` 的 optional gain
算進 success criteria。

保守預期：

- GPT：`23/30 -> 24/30`（`q007` 翻正；`q018` GPT 只驗 contract，因 `created_before=null` 仍未翻正，不計 headline）
- CLA：`25/30 -> 26/30`（`q007` 翻正）
- DSK：`18/30 -> 20/30`（`q007`、`q018` 翻正）

若後續 follow-up 願意處理 `project` narrow rule，則 `q029 CLA` 可列 bonus；若願意做
`japanese` contextual drop，則 `q029 DSK` 才可能列 bonus。但這兩者都不屬 iter7 主版。

## 7. 驗證方法

### 7.1 Unit：keyword_rules decoration cleanup

至少新增以下測試：

- `['graphql', 'server', 'implementations'] -> ['graphql', 'server']`
- `['spring boot', 'starter', 'projects'] -> ['spring boot', 'starter']`
- case-insensitive：`['GraphQL', 'Server', 'IMPLEMENTATIONS'] -> ['graphql', 'server']`
- 既有 keyword 不受影響：
  - `['project management']` 不做 substring 刪除
  - `['project']` 維持原樣（鎖住 `project` 不進 iter7 主版）
  - `['sample']` 不受影響
  - `['template']` 不受影響

### 7.2 Integration：validate_query snapshot

確認：

- q007 類 raw parse output 含 `implementations`
  - downstream 後 `structured_query.keywords` 不再含該 token
- q018 類 raw parse output 含 `projects`
  - downstream 後不再含該 token
- scorer 與 runtime 使用同一 canonicalization 結果

### 7.3 Shared-contract：find_keyword_violations

額外補一條 contract 測試，確保 `find_keyword_violations` 與 `normalize_keywords`
共用同一份 stopword set（避免 single-source-of-truth 漏網，重演 iter6 evidence
dict bug）：

- `find_keyword_violations` 對 `['graphql', 'server', 'implementations']` 應將
  `implementations` 視為 violation
- 與 `normalize_keywords` 後 `keywords` 移除的 token 集合一致
- 若兩者對 stopword set 看法不一致，contract 測試必須失敗

### 7.4 Cross-model full smoke rerun

```bash
gh-search smoke --model gpt-4.1-mini    --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_gpt41mini_iter7_20260425
gh-search smoke --model claude-sonnet-4 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_claude_sonnet4_iter7_20260425
gh-search smoke --model DeepSeek-R1     --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_deepseek_r1_iter7_20260425
```

## 8. 通過標準

本輪採實質判準，通過需同時滿足：

1. §6.1 的 **4 個 primary target pairs 全部翻正**
2. §6.2 的 `q018 GPT`：
   - `projects` token 被清掉
   - 不要求整題翻正
3. 不引入新的 keyword regression
4. DeepSeek headline accuracy 不得下降超過 2 題
5. `pytest -q` 全綠

> DeepSeek `±2` 內波動的 noise 判讀屬程序，已併入 §8.2 实质通過與
> §9 step 4 收斂順序，不列為達標條件。

### 8.1 完整達標

若 4/4 primary target 全翻正，且 `q018 GPT` contract 成立，三模型 headline
均不下降，則視為完整達標。

### 8.2 實質通過

若 4/4 primary target 全翻正，但某模型 headline 在 `±2` 內波動且只落在
`ITER5_NOTES §1.1` 已知 DeepSeek 脆弱 pattern，可視為實質通過。

## 9. 驗證不過時的調整順序

若 unit / integration / smoke 未過，iter7 只允許做以下收斂，**不得擴 scope**：

1. 先確認 stopword 是否只做 **exact token match**
   - 不做 substring 刪除
   - 不新增 bag-level / phrase-level rule
2. 若出現誤刪 topic token
   - 維持 `implementations` / `projects` 兩個 core token
   - 不把 `project` 提前納入主版
3. 若 q007 / q018 仍未吃到
   - 檢查 cleanup 是否落在 shared normalization path
   - 優先修 pipeline 插入點，不新增第二套 keyword cleanup
4. 若 DSK headline 明顯退步
   - 先依 `ITER5_NOTES §1.2` rerun / 檢查 target pair
   - 若 regression 落在 sort default / CJK canonicalization 等既有脆弱 pattern，先視為 noise candidate
5. 若要靠 `japanese`、`templates -> template`、prompt wording 才能救題
   - 不在 iter7 內處理，直接 defer 到 iter8 / follow-up

## 10. Rollback 條件

符合任一即 rollback：

1. primary target 少於 4/4
2. `q018 GPT` 的 `projects` 仍未被清掉
3. 出現新的 keyword regression 2 題以上
4. 為了救 q029 而把 `japanese` 升成全域 stopword
5. 為了救 q009 而把 `templates -> template` 混進 iter7 主版

## 11. Iter7 後的交接

## 11. 實際結果（2026-04-25 rerun）

### 11.1 Headline 結果

| 模型 | iter6 fix | iter7 | Δ |
|---|---|---|---|
| `gpt-4.1-mini` | 23/30 (76.67%) | **23/30 (76.67%)** | **+0** |
| `claude-sonnet-4` | 25/30 (83.33%) | **26/30 (86.67%)** | **+1** |
| `deepseek-r1` | 18/30 (60.00%) | **23/30 (76.67%)** | **+5** |

對應 run artifact：

- `eval_gpt41mini_iter7_20260425`
- `eval_claude_sonnet4_iter7_20260425`
- `eval_deepseek_r1_iter7_20260425`

### 11.2 Iter7 真正造成的 delta

本輪真正由 decoration cleanup 直接造成的結果是：

- **4/4 primary target pairs 全部翻正**
  - `q007 GPT`
  - `q007 CLA`
  - `q007 DSK`
  - `q018 DSK`
- **`q018 GPT` contract-only 達成**
  - iter6 `['starter', 'projects']`
  - iter7 `['spring boot', 'starter']`
  - 但仍因 `created_before=null` 未整題翻正
- **keyword regression = 0**

也就是說，Iter7 的直接因果增益應記為：

- `+4 primary`
- `+1 contract`

而不是單純以 headline `+0 / +1 / +5` 當成本輪因果效果。

### 11.3 非因果 bonus / regression（不歸因於 Iter7）

下列 headline 變化存在，但都不屬於 decoration cleanup 的直接因果：

| 題目 | 變化 | 因果來源 |
|---|---|---|
| GPT `q026` | `min_stars: 1 -> None`，翻正 | GPT 參數漂移，非 iter7 |
| GPT `q001` | `language: None -> JavaScript`，退步 | GPT language over-inference 漂移 |
| GPT `q028` | `microservice framework -> 微服务框架`，退步 | CJK canonicalization 漂移 |
| DSK `q013` / `q015` / `q025` / `q026` | `sort/order: None -> stars/desc`，翻正 | DSK sort-default 穩定化（`ITER5_NOTES §1.1` Pattern A） |
| DSK `q028` | `微服务框架 -> microservice framework`，翻正 | DSK CJK 漂移（這次正好對） |
| DSK `q001` / `q010` | `sort` / `order` 漂回 `None`，退步 | DSK sort-default 漂移（這次漂反） |

因此：

- GPT headline 持平，不代表 Iter7 無效；它同時吃到 `q007`，但被 scope 外漂移抵消
- DSK headline `+5` 很亮眼，但不能把全部增分都算成 decoration cleanup

### 11.4 通過標準對照

| 條件 | 結果 | 備註 |
|---|---|---|
| §6.1 4/4 primary 翻正 | ✅ | `q007 GPT/CLA/DSK` + `q018 DSK` |
| §6.2 `q018 GPT` contract 成立 | ✅ | `projects` 已清掉 |
| §8 #3 無新 keyword regression | ✅ | 0 keyword regression；其餘 regression 皆在 deferred bucket |
| §8 #4 DSK headline 不下降 >2 | ✅ | DSK `+5` |
| §8 #5 `pytest -q` 全綠 | ✅ | `395 passed` |
| §10 rollback triggers | ✅ 未觸發 | 全部未觸發 |

### 11.5 最終判定

Iter7 **完整達標（§8.1）**，不僅是實質通過。

理由：

- 4/4 primary target 全翻正
- `q018 GPT` contract 成立
- 三模型 headline 均未下降（GPT `+0` / CLA `+1` / DSK `+5`）
- 沒有新的 keyword regression

## 12. Iter7 後的交接

若 iter7 成功，下一輪優先項：

1. **iter8** — multilingual canonicalization
   - `爬蟲套件`
   - `微服务框架`
   - `サンプルプロジェクト`
   - 若需要，再評估 `japanese` narrow contextual drop
2. **iter7 follow-up 或另開** — plural drift
   - `templates -> template`
3. **iter9** — sort defaults / ranking intent
   - `popular -> sort=stars, order=desc`
   - `trending -> sort=stars, order=desc`
   - 對應 `ITER5_NOTES §1.1` 的 DSK Pattern A（sort-default missing）
