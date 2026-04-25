# Iteration 9 Language Over-Inference Residual Spec

## 1. 目標

本輪 tuning 的單一目標是把 **residual language over-inference suppression**
下放到 deterministic downstream，清掉 parser / model 在 **沒有明示語言錨字**
時誤填的 `language` facet。

iter9 延續 iter6 / iter7 / iter8 的策略：

- **不擴寫** `prompts/core/parse-v1.md`
- **不動** parser prompt / appendix prompt
- 優先把 dataset-backed language evidence policy 放到 downstream

本輪主題只做：

- `language` facet 的明示證據判斷
- framework / topic token 不得自動升格成 `language`
- runtime / scorer / trace 共用同一份 language evidence policy

## 2. 背景

iter8 shipped baseline（`eval_*_iter8_20260425`）後，剩餘失分已收斂成：

1. language over-inference residual
2. DSK sort-default drift / noise
3. stars boundary / repair contract
4. 小量 plural / parser drift / date 尾巴

本輪只做第 1 桶。

### 2.1 iter8 baseline 中仍可直接由 language suppression 吃回的題目

| qid | model | iter8 pred | 若做 language suppression 後 |
|---|---|---|---|
| q001 | GPT | `language='JavaScript'`, keywords 已正確 | 翻正 |
| q029 | GPT | `language='JavaScript'`, keywords 已正確 | 翻正 |

共 **2 個 primary target pairs**。

### 2.2 contract-only / secondary cases

| qid | model | iter8 pred | 為何不列 primary |
|---|---|---|---|
| q009 | GPT | `language='Vue'`，且缺 `vue 3` | 清掉 language 後仍卡 parser topic retention |
| q029 | CLA | `language='JavaScript'`，且缺 `react` | 清掉 language 後仍卡 missing keyword |

### 2.3 明確不在本輪處理

- `q009 DSK templates -> template`（plural drift follow-up）
- `q013` / `q015` / `q026` / `q027 DSK` 的 `sort/order=null`
- `q020 DSK min_stars=1000`
- `q030` adversarial stars range / dataset audit
- `q018 GPT` 的 `created_before=null` 與 `spring boot` 缺失
- `q029 CLA` 的 `react` topic retention
- 任何 prompt-level language guard

## 3. 單一判定原則

iter9 只保留 **user query 明示支持** 的 `language` facet。

### 3.1 明示語言證據規則

當且僅當 `user_query` 中出現可 canonicalize 成語言名稱的明示語言錨字時，
才保留 `language`。

本輪 evidence map 應先對齊既有
`src/gh_search/normalizers/keyword_rules.py` 內的
`_LANGUAGE_TOKEN_TO_FACET` snapshot；**不新增 dataset 無證據的 typo alias**，
但若 dataset 確實有 typo language anchor（已收錄於 `notes`）則必須補進去，
否則 iter9 會把正確的 language 誤清。

本輪 evidence 來源應覆蓋既有 dataset / runtime 已需要的語言名稱與 alias：

- `python` / `py` / `pythn` -> `Python`
- `javascript` / `js` / `javscript` -> `JavaScript`
- `typescript` / `ts` -> `TypeScript`
- `java` -> `Java`
- `rust` -> `Rust`
- `go` / `golang` -> `Go`
- `c++` / `cpp` -> `C++`
- `c#` -> `C#`

`pythn` / `javscript` 的 dataset 證據：

- `q023` `user_query='pythn web frameework sorted by strs'`，gt `language='Python'`
- `q024` `user_query='javscript chatbot libs with min 500 starz plz'`，gt `language='JavaScript'`

兩題在 iter8 baseline 都 PASS，若 iter9 不認得 typo anchor 會把正確 language
清掉，違反 §10 #3 rollback 條件。

iter9 **不新增**新的語言推論，只做保留或清除。

matching policy 必須明寫為：

- case-insensitive
- token-bounded matching，不得用 naive substring
- 對含特殊字元的 anchor（例如 `c++`, `c#`）必須 `re.escape`
- anchor 命中後，需先 canonicalize 成語言名稱
- **只有當 query 命中的 canonical language 與 `pred.language` 一致時才保留**

也就是：

- `user_query` 有 `java`，但 `pred.language='JavaScript'` -> 清掉
- `user_query` 有 `react` / `vue`，但它們不在 evidence map -> 清掉
- `user_query` 有 `python` 且 `pred.language='Python'` -> 保留
- `user_query` 有 `c++` 且 `pred.language='C++'` -> 保留

### 3.2 framework / topic token 不得升格成 language

下列類型在 iter9 **不得**視為 language evidence：

- framework / library / stack 名稱
  - 例如 `react`, `vue`, `react native`, `spring boot`
- topic phrase
  - 例如 `react component library`, `vue 3 admin dashboard`
- repo ecosystem 常識推論
  - 例如「React 通常是 JavaScript，所以填 JavaScript」

iter9 的規則不是「更聰明地猜 language」，而是：

- **沒有明示語言錨字，就清掉 `language`**

### 3.3 單一共享入口

iter9 應維持 language evidence 的 single-source-of-truth，避免未來：

- `keyword_rules.py` 的 language leak token map
- `validate_query.py` 的 language evidence detector

各自維護兩套 alias / canonicalization 規則而 drift。

本 repo 目前實際狀態是：

- `keyword_rules.py` 內只有 **一份** `_LANGUAGE_TOKEN_TO_FACET`
- `validate_query.py` / `validator.py` / `parse_query.py` 目前沒有第二份 language map

因此 iter9 建議先走 **read-only SSoT 路徑**：

- 直接由 `validate_query` 讀取既有 `_LANGUAGE_TOKEN_TO_FACET`
- 不預先抽 `language_rules.py`
- 以 unit / contract tests 鎖住這份 map 是 single canonical source

若未來真的出現第二個 production 使用點，再抽 `language_rules.py`。

## 4. 明確責任分界

iter9 **只處理**：

- `language` 欄位的 downstream suppression
- explicit language evidence detection
- shared runtime / validator / scorer contract 一致性

iter9 **不處理**：

- `keywords` 補回缺失 topic（例如 `vue 3`、`react`）
- multilingual canonicalization
- plural drift
- sort defaults
- numeric boundary
- parser prompt wording

## 5. 設計方向

### 5.1 主策略

沿用 validate-before-semantic-validation 的既有流程，在 `validate_query`
的 normalization 階段加入 **language evidence normalization**，讓：

- runtime 最終 `structured_query.language`
- validator 看到的 `language`
- per-item artifact trace

全部共用同一套 suppression 結果。

### 5.2 建議實作位置

建議只動：

- `src/gh_search/tools/validate_query.py`
- `tests/normalizers/test_language_evidence.py`（新檔）
- `tests/test_tool_validate_query.py`

不動：

- `prompts/core/parse-v1.md`
- `prompts/appendix/parse-*.md`
- `src/gh_search/normalizers/keyword_rules.py`（沿用既有
  `_LANGUAGE_TOKEN_TO_FACET`，不新增第二份 map）
- `src/gh_search/tools/parse_query.py`
- `src/gh_search/validator.py`
- `src/gh_search/eval/scorer.py`
- `src/gh_search/normalizers/__init__.py`

### 5.3 建議插入層級

建議放在 [validate_query.py](/Users/chenweiqi/Documents/interview/gofreight/src/gh_search/tools/validate_query.py:66)
的 `_normalize_structured_query()` 內：

```python
def _normalize_structured_query(
    sq: StructuredQuery,
    user_query: str,
) -> StructuredQuery:
    ...
```

1. 先做 `normalize_keywords(...)`
2. 再用 `user_query` 判斷 `language` 是否有明示證據
3. 若無證據，將 `sq.language` 清成 `None`

`validate_query(state)` 需同步改成把 `state.user_query` 傳進去。

理由：

- iter9 處理的是 final structured facet，不是 keyword bag rewrite
- `user_query` 只有在 `validate_query(state)` 這層最自然可得
- 可以在進 semantic validation 前就固定最終 `language`

## 6. 本輪要救回的題目

### 6.1 Primary target pairs

| qid | model | iter8 blocker | 預期 iter9 |
|---|---|---|---|
| q001 | GPT | `language='JavaScript'` | CORRECT |
| q029 | GPT | `language='JavaScript'` | CORRECT |

共 **2 個 primary target pairs**。

### 6.2 Contract-only targets

| qid | model | iter8 blocker | iter9 驗收方式 |
|---|---|---|---|
| q009 | GPT | `language='Vue'` + 缺 `vue 3` | 只檢查 `language` 被清掉，不要求整題翻正 |
| q029 | CLA | `language='JavaScript'` + 缺 `react` | 只檢查 `language` 被清掉，不要求整題翻正 |

### 6.3 Secondary / deferred

| qid | model | 狀態 |
|---|---|---|
| q009 | DSK | `templates -> template`，留 plural drift follow-up |
| q013 / q015 / q026 / q027 | DSK | sort-default drift，留獨立 investigation / iter10+ |
| q030 | GPT / CLA / DSK | stars boundary / dataset audit，留後續 |
| q018 | GPT | parser drift / date residual，留後續 |

### 6.4 預期增分

iter9 主版只依賴 primary target 與 contract-only target，不把任何缺詞修復算進 success
criteria。

保守預期：

- GPT：`24/30 -> 26/30`（`q001`、`q029` 翻正；`q009 GPT` 只驗 contract，不計 headline）
- CLA：`27/30 -> 27/30`（`q029 CLA` 只驗 contract，不計 headline）
- DSK：`23/30 -> 23/30`

headline upside 刻意保守，因為 iter9 只清錯誤 `language`，不補回缺失 keyword。

## 7. 驗證方法

### 7.1 Unit：language evidence policy

至少新增以下測試：

- 無明示語言錨字時清掉 `language`
  - `react component libraries` + `language='JavaScript'` -> `None`
  - `vue 3 admin dashboard templates` + `language='Vue'` -> `None`
  - `日本語で書かれた React のサンプルプロジェクト` + `language='JavaScript'` -> `None`

- 有明示語言錨字時保留 `language`
  - `javascript testing frameworks` + `language='JavaScript'` -> 保留
  - `c++ game engines` + `language='C++'` -> 保留
  - `python scraping repos` + `language='Python'` -> 保留
  - `java spring boot starter projects from 2024` + `language='Java'` -> 保留
  - `rust repos created this year with over 500 stars` + `language='Rust'` -> 保留

- alias evidence 也視為明示
  - `golang cli tools` + `language='Go'` -> 保留
  - `js chatbot libraries` + `language='JavaScript'` -> 保留

- idempotence
  - `pred.language=None` + 任意 query -> 仍為 `None`

- unknown / non-canonical predicted language 會被清掉
  - `vue 3 admin dashboard templates` + `language='Vue'` -> `None`
  - `react component libraries` + `language='JavaScriptish'` -> `None`
  - `react component libraries` + `language=''` -> `None`
  - `react component libraries` + `language='  '` -> `None`

- token-boundary / special-char matching
  - `find me java tutorials` + `language='JavaScript'` -> `None`
  - `python で書かれた爬蟲` + `language='Python'` -> 保留
  - `c++ game engines` + `language='C++'` -> 保留

### 7.2 Integration：validate_query snapshot

確認：

- integration test 應直接餵 raw parser fixture 的 `predicted_structured_query` 給
  `validate_query`，不重新呼叫 LLM
- q001 GPT 類 raw parse output 含 `language='JavaScript'`
  - downstream 後 `language=None`
- q009 GPT 類 raw parse output 含 `language='Vue'`
  - downstream 後 `language=None`
- q029 GPT / CLA 類 raw parse output 含 `language='JavaScript'`
  - downstream 後 `language=None`
- explicit-language 正例經過 `validate_query` 後仍保留原語言

### 7.3 Shared-contract：language map ownership

iter9 必須補 contract 測試，鎖住 language evidence map 的單一來源。

至少覆蓋：

- `keyword_rules` 的 `_LANGUAGE_TOKEN_TO_FACET` 與 validate_query language
  suppression 使用同一份 token -> language canonicalization
- `js` / `javascript`、`golang` / `go`、`cpp` / `c++`
  對兩邊都得到一致 canonical 結果

若兩邊 alias table 漂移，contract test 必須失敗。

### 7.4 Cross-model full smoke rerun

```bash
gh-search smoke --model gpt-4.1-mini    --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_gpt41mini_iter9_20260425
gh-search smoke --model claude-sonnet-4 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_claude_sonnet4_iter9_20260425
gh-search smoke --model DeepSeek-R1     --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_deepseek_r1_iter9_20260425
```

## 8. 通過標準

本輪採實質判準，通過需同時滿足：

1. §6.1 的 **2 個 primary target pairs 全部翻正**
2. §6.2 的 contract-only targets：
   - `q009 GPT` 的 `language` 被清掉
   - `q029 CLA` 的 `language` 被清掉
3. explicit-language 正例不得出現新的 language regression
4. `pytest -q` 全綠

### 8.1 完整達標

若 2/2 primary target 全翻正，且 2 個 contract-only target 都成立，同時：

- GPT headline 達到 `24 -> 26`
- CLA headline 不下降
- DSK headline 不下降

則判定為 **完整達標**。

### 8.2 實質通過

若 primary / contract 全命中，但 headline 未完全達到 §6.4，只要差額可清楚歸因於：

- parser drift
- out-of-scope keyword missing
- DSK 既有 sort-default noise

且 **不是 iter9 patch 造成的新 language regression**，可判為 **實質通過**。

## 9. 驗證不過時的調整順序

若驗證未過，依下列順序收斂：

1. 先確認失敗是否真的屬 language policy
   - 若是 `vue 3` 缺詞、`react` 缺詞、sort default、stars boundary，屬 out-of-scope
2. 若 explicit-language 正例被誤清掉
   - 先補 language evidence alias / tokenization
   - 不要引入 framework denylist 大雜燴
3. 若 contract-only 題沒清掉 `language`
   - 檢查是否誤用 `keywords` 當 evidence，而不是 `user_query`
4. 若想為了救 `q009 GPT` 或 `q029 CLA` 去補回缺詞
   - 停止；那已經是 parser topic-retention scope，不屬 iter9

## 10. Rollback 條件

符合任一條件就 rollback：

1. `q001 GPT` 或 `q029 GPT` 任一未翻正
2. `q009 GPT` / `q029 CLA` 任一 contract 不成立
3. 任一 explicit-language 正例被誤清掉 `language`
4. 為了救題而開始修改 prompt / appendix
5. 為了救題而把 framework / topic token（例如 `react`, `vue`）升成 ad-hoc denylist 規則
6. 為了救 `q009 DSK` 或 sort / stars 題而擴 scope

## 11. Handoff

iter9 後仍可能殘留的桶：

- `q009 DSK templates -> template`
  - plural drift follow-up
- `q013 / q015 / q026 / q027 DSK`
  - sort defaults / ranking intent
- `q020` / `q030`
  - stars semantics / boundary / dataset audit
- `q018 GPT`
  - parser drift / date residual

若 iter9 shipped，下一輪優先順序建議為：

1. stars semantics / boundary（先人工 audit `q030` GT）
2. DSK sort-default investigation
3. plural drift 小修
