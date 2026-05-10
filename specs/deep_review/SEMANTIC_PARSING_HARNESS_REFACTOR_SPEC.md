# Semantic Parsing Harness Refactor Spec

日期：`2026-05-10`  
狀態：`draft`  
範圍：`gh-search` Phase 2 retrospective / Phase 3 cleanup

## 1. 這份 spec 在解什麼問題

目前專案的 hardening 方向本身沒有錯：

- 不一直往 prompt 塞規則。
- 把可重複的修正搬到 deterministic Python 邏輯。
- 用 `validate_query` 與 `keyword_rules` 當 shared normalization layer。

真正的問題是另外幾件事：

1. 正式 eval dataset 裡還混著 `needs_revision` 題目。
2. hardening 看起來太像在救目前這 30 題，不像在處理穩定的語義現象。
3. 測試大多只驗證原題和近鄰變體，還沒有一套像 semantic parsing harness 的結構化測法。

這份 spec 的目的不是再補幾條規則，而是把目前的 benchmark hardening，升級成一套比較像 semantic parsing evaluation system 的東西。

## 2. 這次要做到什麼

本輪修改要完成以下事情：

1. 清掉正式 eval 中不適合放進 headline accuracy 的題目。
2. 把 dataset 從單一題庫，拆成有分桶的 harness。
3. 把 hardening 規則分成可長期保留的通用規則，和暫時性的資料集修補規則。
4. 補上 semantic parsing 常見的測試策略，不只測原句，還測同義改寫、alias、邊界題、模糊題。
5. 讓 README、dataset、review 文件、正式分數彼此一致。

## 3. 這次不做什麼

這一輪先不要擴大範圍：

1. 不重寫整個 parser prompt。
2. 不新增新的 LLM provider。
3. 不改 `StructuredQuery` 的欄位集合，除非後續另開 spec。
4. 不要求一次刪光所有 heuristic；本輪先分層、先治理、先補證據。

## 4. 核心原則

### 4.1 正式 eval 只收穩定題

一題要能進 formal eval，至少要符合：

- 題意清楚。
- 目前 schema 能穩定表達。
- reviewer 不需要腦補。
- 不會因為換一個 reviewer 就出現不同 ground truth。

### 4.2 規則要圍繞語義現象，不要圍繞 qid

好例子：

- `more than / over / > / 超過` 都算同一種 lower-bound 語義。
- `popular / top / most starred` 都算同一種 ranking intent。

壞例子：

- 因為 `q027` 長這樣，所以只寫一條剛好救 `q027` 的規則。

### 4.3 Harness 要分桶

不是所有題都該混在同一份 dataset 裡。  
至少要把「正式評測題」和「模糊題 / 不可表達題 / failure case」拆開。

### 4.4 同一個意思要用 many-to-one 方式驗證

如果多種不同說法最後都應該得到同一個 `StructuredQuery`，那這件事要被明確測出來，不能只靠直覺認定。

## 5. 第一優先：先修資料集

### 5.1 先處理 4 題 `needs_revision`

以下四題不得繼續原封不動留在正式 headline accuracy：

- `q010`
- `q020`
- `q021`
- `q029`

處理規則如下：

1. 如果能改寫成穩定、可由 schema 表達的題目，就改寫後重新標註。
2. 如果無法穩定表達，就移去 `failure_case` 或 `ambiguous_or_unexpressible` bucket。
3. 在完成這件事之前，不再把含這四題的 30 題結果當正式主分數。

### 5.2 正式題數建議維持 30 題

建議 formal eval 仍維持 `30` 題，避免 README 敘事和實際題數脫節。

因此移出 4 題後，應補入 4 題新題。新題原則：

- 可穩定標註。
- 不模糊。
- 不依賴 schema 外能力。
- 盡量覆蓋目前 hardening 已經在處理的語義族。

建議補題方向：

1. 一題乾淨的 ranking intent。
2. 一題乾淨的 stars boundary。
3. 一題乾淨的 date constraint。
4. 一題乾淨的 multilingual but expressible keyword。

## 6. 新 harness 分桶設計

### 6.1 `formal_eval`

用途：

- 報 headline accuracy。
- 做跨模型比較。
- 當主要 regression 指標。

內容要求：

- 只收 `approved` 題。
- 每題保留一個 canonical wording 即可。

### 6.2 `paraphrase_eval`

用途：

- 驗證 same meaning / different wording 時，是否仍能得到同一個 `StructuredQuery`。

內容要求：

- 每個 canonical 題目至少有 `3-5` 個 meaning-preserving rewrites。
- 同一族至少包含 token-level 改寫和 sentence-level 改寫。

### 6.3 `alias_eval`

用途：

- 驗證 domain vocabulary / alias 對齊是否穩定。

建議覆蓋：

- stars comparator 的別說法。
- ranking vocabulary 的別說法。
- language mention 的別說法。
- keyword canonicalization 的別說法。
- multilingual topic alias。

### 6.4 `boundary_eval`

用途：

- 驗證系統不會把「看起來很像」的題目過度腦補成已支援語義。

這一桶要放的不是單純錯題，而是有語義邊界的題，例如：

- `newest`
- `recent-ish`
- `not too old but not too new`
- human language 和 programming language 容易混淆的句子

### 6.5 `ambiguous_or_unexpressible_eval`

用途：

- 驗證系統能不能誠實地保守處理，而不是亂湊一個近似答案。

這一桶不計入 headline accuracy，但要保留：

- 預期 outcome
- 建議處理方式
- 為何不能進 formal eval 的說明

### 6.6 `failure_case_eval`

用途：

- 保留已知失敗模式。
- 支援 retrospective。
- 讓之後的 hardening 有地方對照，不必再把邊界題塞回 formal eval。

## 7. Hardening 規則要分層

### 7.1 `domain-stable normalization`

定義：

- 在 GitHub repository search 這個 domain 中合理長期保留。
- 不需要綁某一題才成立。

目前優先整理的族：

1. stars comparator normalization
2. ranking intent normalization
3. language evidence suppression / cleanup
4. phrase-level canonicalization（只保留跨題都成立的部分）

### 7.2 `dataset-backed heuristic`

定義：

- 目前有效，但證據主要來自現有 dataset。
- 泛化能力還沒被充分證明。

常見例子：

- 只在少數題目出現的 multilingual rewrite
- 只由一兩題支撐的 phrase merge
- 很窄的 noise-token cleanup

### 7.3 為什麼一定要分層

不分層時，所有規則看起來都像同一種東西，外部 reviewer 很容易解讀成：

`你不是在做通用 normalization，你是在 patch benchmark。`

分層後，文件可以誠實說清楚：

- 哪些規則是我們相信可長期保留的。
- 哪些規則只是目前先救分，但還需要更多證據。

## 8. 這次要補的 semantic parsing 策略

下面這些不是抽象概念，而是要真的進 dataset 和 tests。

### 8.1 Same-meaning paraphrase families

同一個語義要有一組等價改寫，而不是只有一個 canonical 句子。

優先補的族：

1. `stars_lower_bound`
2. `stars_upper_bound`
3. `ranking_intent`
4. `language_evidence`
5. `date_constraints`

例：

- `more than 500 stars`
- `over 500 stars`
- `> 500 stars`
- `star 超過 500`

這幾句如果語義相同，就應該得到同一個 `StructuredQuery`。

### 8.2 Sentence-level rewrite families

不要只補 token 替換，還要補整句重寫。

每個重要語義族至少要有：

- 直白說法
- 口語說法
- 語序改寫

這在 semantic parsing 論文裡很重要，因為很多系統不是倒在單字替換，而是倒在整句表達方式變了。

### 8.3 Alias / domain vocabulary coverage

這一層是把「使用者說的詞」和「系統懂的概念」對齊。

應優先整理的 alias：

1. `over / more than / > / 超過`
2. `under / less than / < / 少於`
3. `popular / top / most starred / ranked by stars`
4. `python / py`
5. multilingual concept variants（只收語義穩定、可解釋的）

### 8.4 Boundary-case coverage

要刻意測那些「表面很像，但其實不能直接等同」的題。

至少要補：

1. `newest` 是否被錯當成 `sort=updated`
2. `日本語で書かれた` 是否被誤當 programming language
3. `not too old but not too new` 是否被硬補成假日期範圍

這一桶的重點不是讓模型答對，而是防止系統過度自信。

### 8.5 Ambiguity handling

這一桶要測的是：

- 系統會不會誠實說自己表達不了。
- 系統會不會保守保留 unsupported / ambiguous。
- 系統會不會亂湊一個看似合理但其實不穩的答案。

### 8.6 Many-to-one semantic clusters

不要只是「多補幾題」，而是要清楚定義：

- 哪幾句其實是同一個意圖。
- 這一組句子都應該收斂到同一個 target。

這件事是 semantic parsing 論文一直在強調的，也正是目前 repo 最缺的證據。

## 9. 建議的資料與測試落點

### 9.1 Dataset

建議新增或重整為：

- `datasets/eval_dataset_formal.json`
- `datasets/eval_dataset_paraphrase.json`
- `datasets/eval_dataset_alias.json`
- `datasets/eval_dataset_boundary.json`
- `datasets/eval_dataset_ambiguous.json`
- `datasets/eval_dataset_failure.json`

如果短期不想拆這麼多檔，至少要在現有 dataset 中新增清楚的 `bucket` 欄位，先把用途分開。

### 9.2 Tests

建議新增：

- `tests/test_paraphrase_harness.py`
- `tests/test_alias_harness.py`
- `tests/test_boundary_cases.py`
- `tests/test_ambiguity_handling.py`

### 9.3 Scorer

scorer 需要支援至少三種評法：

1. formal 題目的 canonical exact evaluation
2. paraphrase cluster 的 many-to-one evaluation
3. ambiguity bucket 的 outcome-based evaluation

### 9.4 README

README 之後要同步說清楚：

1. 哪一份 dataset 才算正式主分數。
2. 哪些 dataset 是 robustness / failure / boundary 用。
3. hardening 規則有哪些層級。
4. 哪些限制仍然存在。

## 10. 建議執行順序

1. 先處理 `q010/q020/q021/q029`。
2. formal eval 補回 4 題。
3. dataset 分桶。
4. hardening 規則分層。
5. 先補 `stars / ranking / language / date` 四組 semantic families。
6. 再補 multilingual / boundary / ambiguity harness。
7. 最後才重跑正式 eval 並更新 README。

## 11. 驗收標準

本輪完成時，至少要滿足：

1. headline accuracy 不再建立在 `needs_revision` 題目上。
2. review 文件、dataset、README 三者不再互相衝突。
3. 至少有一份獨立的 paraphrase robustness dataset 或 bucket。
4. 至少三類 hardening 規則已標記為 `domain-stable` 或 `dataset-backed`。
5. 至少一組 sentence-level rewrite family 已進測試。
6. 至少一桶 ambiguous / unexpressible 題目已從 formal eval 拆出。

## 12. 一句話總結

這份 spec 的重點不是再多補幾條規則，而是把目前這套系統從「修這 30 題」往前推一步，變成：

**formal 題目夠乾淨、同義改寫成家族、模糊題獨立分桶、規則分層可解釋的 semantic parsing harness。**
