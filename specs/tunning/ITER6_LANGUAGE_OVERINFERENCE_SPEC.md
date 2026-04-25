# Iteration 6 Language Over-Inference Spec

## 1. 目標

本輪 tuning 的單一目標是把 **`language` 欄位的 over-inference** 從 parser
prompt 層移到 **post-parse downstream** 處理。

也就是：

- parser 仍可先輸出 `language`
- downstream 依據 **明示語言證據** 決定保留或清除
- **不再**透過擴寫 `prompts/core/parse-v1.md` 來壓 parser 猜語言

本輪的核心工程決策：

- **不讓 core parse prompt 繼續膨脹**
- **不動** `prompts/core/parse-v1.md`
- 先驗證「language over-inference 是否可完全下放 downstream」

## 2. 背景

iter5 / iter5 verify / iter5 follow-up 的結果已經提供兩個明確訊號：

1. GPT / Claude 對 parse prompt 長度相對穩定
2. DeepSeek-R1 對 parse prompt complexity 顯著敏感，回歸集中在：
   - sort default missing
   - decoration leak
   - CJK -> EN canonicalization
   - noisy-input JSON robustness

依 [ITER5_NOTES.md](./ITER5_NOTES.md) §6 的結論，後續 iter6/7/8 **不應再把
parser 規則寫長**。因此 iter6 改採 downstream 策略，而不是 parser prompt
策略。

### 2.1 目前主要 target

iter5 主版仍存在的 language over-inference 代表題：

| qid | 模型 | GT | iter5 pred | 問題 |
|---|---|---|---|---|
| q001 | GPT | `language=null` | `language='JavaScript'` | `react` 被自動升格成語言 |
| q009 | GPT | `language=null` | `language='Vue'` | `vue 3` 被自動升格成語言 |
| q029 | GPT | `language=null` | `language='JavaScript'` | `React` 被自動升格成語言 |
| q029 | CLA | `language=null` | `language='JavaScript'` | `React` 被自動升格成語言 |

說明：

- q001 / q029 是最典型的 **framework/topic -> JavaScript** 誤推論
- q009 GPT 則表現為 **framework name -> language facet**
- 這些都屬於 parser 的世界知識推論，不是使用者明示條件

### 2.2 為什麼不繼續改 parser prompt

若用 parser prompt 壓這些 case，短期看似可解，但代價是：

- 進一步拉長 `parse-v1.md`
- 讓 DeepSeek-R1 再次跨過 prompt-complexity threshold
- 在 sort / decoration / multilingual 等已知脆弱區再引入不穩定

因此 iter6 的原則是：

**parser prompt 不加長；改由 downstream 對 `language` 欄位做 evidence-based contraction。**

## 3. 單一判定原則

最終輸出的 `language` 只有在 **query 內存在明示語言證據** 時才保留。

### 3.1 可保留的情況（explicit evidence）

以下情況可保留 `language`：

- query 直接出現語言名：
  - `python`
  - `rust`
  - `golang`
  - `typescript`
  - `java`
  - `swift`
- query 出現 typo / alias，但可 deterministic canonicalize 到語言名：
  - `pythn -> Python`
  - `golang -> Go`
  - `ts -> TypeScript`

### 3.2 不可保留的情況（implicit inference）

以下情況不得僅因常識推論而保留 `language`：

- framework / library / stack 名稱：
  - `react`
  - `vue`
  - `spring boot`
  - `rails`
- topic / ecosystem 名稱
- 由 repo domain 常識推測出的語言
- 與 `keywords` 同義、但不是使用者明示的語言 facet

### 3.3 與 keyword normalization 的關係與 ownership

iter6 不處理 keyword canonicalization 本身，但 `language` evidence 可重用既有
alias / typo 觀念：

- `golang` 可視為 explicit `Go`
- `pythn` 可視為 explicit `Python`

本輪拍板 **單一資料源**：

- 新增 `src/gh_search/normalizers/language_rules.py`
- 由它擁有：
  - explicit language evidence aliases
  - language evidence detector
  - language facet normalizer helper

原因：

- 避免把 `language` evidence policy 混進 `keyword_rules.py`
- 避免在 `validator.py` inline 小 dict，之後和 `keyword_rules.py` drift
- 讓 iter6 / iter7 / iter8 之後若要共享語言 alias，可由 `keyword_rules.py`
  反向 import 這個單一來源，而不是各自維護一份

本輪 **不要求** 立刻重構 `keyword_rules.py` 去 import 它；但 iter6 的新增 alias
只准寫在 `language_rules.py`。

## 4. 明確責任分界

本輪 **只處理**：

- parser 已輸出的 `language` 是否應保留
- `language` 清除 / 保留的 downstream 契約
- 對應 trace / validation / test

本輪 **不處理**：

- parser prompt wording
- decoration token（iter7）
- multilingual keyword alias/drop（iter8）
- stars / sort defaults
- contradictory constraints
- scorer canonicalization 改版

以下情況明確 out of scope：

- `q007 implementations`
- `q018 projects`
- `q019 DSK repos`
- `q027/q029` 的 multilingual topic normalization
- `q015/q013 DSK` 的 sort default

## 5. 本輪要救回的題目

### 5.1 Primary target pairs（language mismatch removal）

| qid | model | iter5 問題 | 預期 iter6 結果 |
|---|---|---|---|
| q001 | GPT | `language='JavaScript'` | `language=null` |
| q009 | GPT | `language='Vue'` | `language=null` |
| q029 | GPT | `language='JavaScript'` | `language=null` |
| q029 | CLA | `language='JavaScript'` | `language=null` |

共 **4 個 target pairs**。

這 4 個 pair 的驗收重點是：

- **language mismatch 必須消失**
- 不要求 4 個 pair 都 end-to-end 翻正

因為其中 3 個 pair 仍有本輪明確 out-of-scope blocker：

| pair | iter6 清掉 language 後的殘留 blocker |
|---|---|
| q009 GPT | `keywords` 少 `vue 3` |
| q029 GPT | multilingual keyword canonicalization |
| q029 CLA | multilingual keyword canonicalization |

只有 `q001 GPT` 在 language 清掉後預期可直接翻正。

### 5.2 Secondary positive set（explicit language 保留）

這些題目已有明示語言證據，本輪不得被誤清空：

| qid | 語言 evidence | GT language |
|---|---|---|
| q004 | `golang` | `Go` |
| q011 | `python` | `Python` |
| q015 | `TypeScript` | `TypeScript` |
| q017 | `python` | `Python` |
| q025 | `golang` / `Go` | `Go` |
| q028 | `golang` | `Go` |

補充 caveat：

- `q015 DSK` 在 iter5 verify 裡 headline `is_correct` 曾受 sort default noise 影響，
  因此 iter6 驗收時對 `q015 DSK` **只看 `language='TypeScript'` 是否仍保留**，
  不把其 headline `is_correct` 波動直接算成 language policy regression。

## 6. 設計方向

### 6.1 主策略：downstream language evidence policy

現行 [validate_query.py](/Users/chenweiqi/Documents/interview/gofreight/src/gh_search/tools/validate_query.py:66)
的 `_normalize_structured_query()` 只有：

- line 67：`normalize_keywords(...)`
- line 68-70：若 keyword 有變才 `model_copy(...)`

因此 iter6 的具體插入點拍板如下：

- **就在 `_normalize_structured_query()` 裡**
- **放在 line 67 的 `normalize_keywords(...)` 之後**
- **放在 line 68-70 的 return 判斷之前**

讓 keyword 與 language 在同一個 post-parse normalization snapshot 內被更新，
再交給 `validate_structured_query()`（line 42-43）做 semantic validation。

對 `structured_query.language` 執行 deterministic policy：

1. 從 `state.user_query` 偵測 explicit language evidence
2. 若 `sq.language` 有值，但 evidence 不足：
   - 清掉 `sq.language`
   - 記錄 trace / issue reason
3. 若 `sq.language` 有值，且 evidence 存在：
   - 保留

### 6.2 建議實作位置

建議只動以下範圍：

- `src/gh_search/normalizers/language_rules.py`（新增，單一 alias / evidence source）
- `src/gh_search/tools/validate_query.py`
- `src/gh_search/validator.py`（若要補 trace / issue 型別引用）
- `src/gh_search/schemas/logs.py` / trace model（若需要補 trace 欄位）
- 對應 tests

**不動**：

- `prompts/core/parse-v1.md`
- `prompts/appendix/parse-*.md`
- `src/gh_search/eval/scorer.py`

### 6.3 建議資料結構

`language_rules.py` 建議提供小型 helper：

```python
def normalize_language_facet(
    raw_language: str | None,
    user_query: str,
) -> tuple[str | None, list[ValidationIssue]]:
    ...
```

回傳：

- `normalized_language`
- audit / trace 用的 issues

`validate_query._normalize_structured_query()` 內則組成：

```python
normalized_keywords = normalize_keywords(...)
normalized_language, language_issues = normalize_language_facet(
    raw_language=sq.language,
    user_query=state.user_query,
)
```

再一次性 `model_copy(...)` 回傳同一個 normalized snapshot。

issue code 建議：

- `language_inferred_without_evidence`
- `language_alias_canonicalized`
- `language_kept_with_explicit_evidence`

本輪不要求這些 issue 進 blocking validation path；可先走 trace / audit。

### 6.4 證據來源

evidence detector 可先從小範圍做起，只收 dataset 已出現的語言詞：

- `python`
- `golang` / `go`
- `typescript` / `ts`
- `rust`
- `java`
- `swift`

以及 typo / alias：

- `pythn`
- `golang`

刻意不在本輪處理：

- framework -> language 的隱性映射
- CJK 多語語言詞
- `Vue` 是否應視為語言名稱（dataset 明確不採）

## 7. 驗證方式

### 7.1 Unit：language evidence policy

新增測試覆蓋：

- `react component libraries` + raw `language='JavaScript'`
  - output `language=None`
- `vue 3 admin dashboard templates` + raw `language='Vue'`
  - output `language=None`
- `日本語で書かれた React のサンプルプロジェクト` + raw `language='JavaScript'`
  - output `language=None`
- `golang cli tools` + raw `language='Go'`
  - output `language='Go'`
- `pythn web frameework` + raw `language='Python'`
  - output `language='Python'`
- `popular TypeScript ORM libraries...` + raw `language='TypeScript'`
  - output `language='TypeScript'`

這組 case 的 raw input 要對齊 iter5 實測：

- q001 GPT raw `language='JavaScript'`
- q009 GPT raw `language='Vue'`
- q029 GPT / CLA raw `language='JavaScript'`
- q029 DSK raw `language=None`，**不是** iter6 target，不應拿來測

### 7.2 Integration：validate_query contract

確認：

- `validate_query()` 會把 `language` 寫回 normalized state
- 不會影響 keyword normalization 的既有路徑
- 不會把 issue 當 blocking validation error（除非本輪實作另有明確決策）

### 7.3 Cross-model smoke rerun

正式驗收仍以三模型 full smoke 為準：

```bash
gh-search smoke --model gpt-4.1-mini    --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_gpt41mini_iter6_20260425
gh-search smoke --model claude-sonnet-4 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_claude_sonnet4_iter6_20260425
gh-search smoke --model DeepSeek-R1     --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_deepseek_r1_iter6_20260425
```

## 8. 通過標準

本輪採實質判準，通過需同時滿足：

1. §5.1 的 **4 個 target pairs**：
   - `language` mismatch 必須 **4/4 全部消失**
   - 其中 `q001 GPT` 應 end-to-end 翻正
2. §5.2 的 explicit-language positive set **零 language regression**
3. 不動 `prompts/core/parse-v1.md` / appendix prompt / scorer / judge
4. DeepSeek headline accuracy **不得下降超過 2 題**
5. 若 DeepSeek 僅在 `±2` 內波動，需對照 per-item 判斷是否落在
   `ITER5_NOTES §1.1` 的既有 stochastic patterns
6. `pytest -q` 全綠

### 8.1 完整達標

若 4/4 target pairs 的 language mismatch 全消失，且 `q001 GPT` 翻正，
三模型總分均不下降，則視為完整達標。

### 8.2 實質通過

若 4/4 target pairs 的 language mismatch 全消失，但 `q001 GPT` 因其他
out-of-scope blocker 未翻正，則可視為實質通過，但需在 `ITER6_NOTES.md`
逐題記錄。

## 9. Rollback 條件

符合任一即 rollback：

1. explicit-language positive set 出現 **2 題以上 regression**
2. 任一模型 headline accuracy 下降 **超過 2 題**
3. DeepSeek 的 regression 明顯集中在非本輪 target，且超出
   `ITER5_NOTES §1.1` 已知 noise pattern
4. 為救 q001/q009/q029 被迫開始擴寫 core parse prompt
5. downstream 實作演變成大量 case-by-case exceptions

## 10. DeepSeek Guardrail

iter6 的附加工程前提：

- **不再把更多規則寫進 core parse prompt**
- 若 smoke 後發現 GPT / Claude 仍有 1-2 個 language case 必須在 prompt 層
  修，優先考慮：
  - `parse-gpt-4.1-mini-v1.md`
  - `parse-claude-sonnet-4-v1.md`
- `parse-deepseek-r1-v1.md` 應保持最短，必要時甚至可維持空白

這不是因為已證明 DSK 遇到的是「硬性上下文上限」，而是因為 iter5 已足夠證明：

**DeepSeek-R1 對 parse prompt complexity 有顯著較高的穩定性風險。**

## 11. 下一輪交接

若 iter6 成功，下一輪優先項：

1. **iter7** — decoration token cleanup
   - `projects`
   - `implementations`
   - `repos`
2. **iter8** — multilingual canonicalization
   - `爬蟲套件`
   - `微服务框架`
   - `サンプルプロジェクト`
3. **後續** — sort defaults / stars boundary / validator-repair contract
