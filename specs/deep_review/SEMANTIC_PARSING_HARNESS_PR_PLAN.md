# Semantic Parsing Harness PR Plan

日期：`2026-05-10`  
狀態：`draft`  
對應母 spec：[SEMANTIC_PARSING_HARNESS_REFACTOR_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/deep_review/SEMANTIC_PARSING_HARNESS_REFACTOR_SPEC.md)

## 1. 這份 PR 計畫怎麼用

這份文件是把 semantic parsing harness refactor spec，拆成可以真的送 review 的 PR 順序。

原則很簡單：

- 一個 PR 只做一件大事。
- 一個 PR 盡量控制在 `<= 20` 個檔案。
- 一個 PR 盡量控制在 `<= 1000` 行 diff。
- dataset 治理、scorer、hardening、README 不要混成同一包。
- 每個 PR 都要能單獨說清楚目的、風險、驗證方式。

## 2. 切 PR 的總原則

### 2.1 先修地基，再補規則

順序固定為：

1. 先修 formal eval dataset 的口徑。
2. 再讓 eval runner / scorer 看得懂分桶。
3. 再補 paraphrase / alias / boundary harness。
4. 最後才動 hardening 規則與 README 敘事。

### 2.2 不要在第一個 PR 就複製整份 30 題 dataset

如果直接複製多份完整 JSON，diff 很容易爆量。  
為了控制 review 成本，建議先用「manifest / qid bucket 檔」表達分桶，再視需要補 full dataset。

建議優先用這種小檔案：

- `datasets/formal_eval_qids.json`
- `datasets/paraphrase_eval_qids.json`
- `datasets/boundary_eval_qids.json`
- `datasets/ambiguous_eval_qids.json`

這樣可以先把治理邏輯釘住，不會一開始就讓 PR 被大段 JSON 吃掉。

### 2.3 一個 semantic family 最多兩組一起改

不要把 `stars`、`ranking`、`language`、`date`、`multilingual` 全塞進一隻 PR。  
比較安全的節奏是：

- 一隻 PR 只做 `stars + ranking`
- 下一隻 PR 再做 `language + date`
- multilingual boundary 再獨立一隻

## 3. 建議 PR 序列

## PR1. Formal Eval Governance

目的：

- 先把「哪些題可以算正式分數」這件事固定下來。
- 把 `q010/q020/q021/q029` 從 formal eval 口徑中移出。

這隻 PR 要做的事：

1. 新增 formal / failure / ambiguous 的 qid manifest 檔。
2. 明確標出 `needs_revision` 四題不再計入正式 headline accuracy。
3. 選出 4 題 replacement candidates，先寫成候選名單，不在這隻 PR 內一次做完整 re-annotation pipeline。
4. 補一個 test，保證 formal eval manifest 不含 `needs_revision` qid。

建議碰的檔案：

- `datasets/formal_eval_qids.json`
- `datasets/ambiguous_eval_qids.json`
- `datasets/failure_eval_qids.json`
- `specs/datasets/HUMAN_REVIEW_SUMMARY.md`
- `tests/test_eval_dataset_governance.py`

不要做的事：

- 不改 scorer。
- 不改 hardening 規則。
- 不補 paraphrase dataset。

驗證方式：

- formal manifest 不含 `q010/q020/q021/q029`
- replacement candidates 有明確記錄
- dataset governance test 會紅會綠

預估大小：

- `5-8` 個檔案
- `150-350` 行 diff

## PR2. Eval Bucket Plumbing

目的：

- 讓 runner / scorer / schema 知道「這題屬於哪一桶」。
- 先把分桶能力接進系統，不先處理 paraphrase 語義。

這隻 PR 要做的事：

1. 為 eval item 增加 `bucket` 或等價欄位。
2. 讓 eval runner 可以依 bucket 載入題目。
3. 讓 scorer 能區分 `formal_eval` 與非正式桶。
4. 補 unit tests，確認 bucket 會影響評分與 summary。

建議碰的檔案：

- `src/gh_search/schemas/eval.py`
- `src/gh_search/eval/runner.py`
- `src/gh_search/eval/scorer.py`
- `tests/test_scorer.py`
- `tests/test_smoke_runner.py`
- `tests/test_eval_dataset_governance.py`

不要做的事：

- 不改 query normalization 邏輯。
- 不引入 paraphrase cluster scoring。

驗證方式：

- formal bucket 仍能正常出主分數
- ambiguous / failure bucket 不混進 headline accuracy
- runner summary 可看出 bucket 分布

預估大小：

- `6-10` 個檔案
- `250-600` 行 diff

## PR3. Paraphrase Harness Skeleton

目的：

- 先把 same-meaning / different-wording 的測試骨架搭起來。
- 讓系統第一次具備 many-to-one evaluation。

這隻 PR 要做的事：

1. 新增 paraphrase dataset skeleton。
2. 為 paraphrase item 增加 `cluster_id` 或等價欄位。
3. 讓 scorer 支援「同一 cluster 應對應同一個 target」。
4. 補最小可用測試，只先放 `1-2` 個 semantic families。

建議第一批 family：

- `stars_lower_bound`
- `ranking_intent`

建議碰的檔案：

- `datasets/eval_dataset_paraphrase.json`
- `src/gh_search/schemas/eval.py`
- `src/gh_search/eval/scorer.py`
- `tests/test_scorer.py`
- `tests/test_paraphrase_harness.py`

不要做的事：

- 不一次塞滿全部 family。
- 不在這隻 PR 內重構所有 hardening 規則。

驗證方式：

- 同 cluster 的不同句子會被視為同一 target
- paraphrase dataset 至少有一組 token-level 改寫
- 至少有一組 sentence-level 改寫

預估大小：

- `5-9` 個檔案
- `250-700` 行 diff

## PR4. Hardening Rule Layering

目的：

- 把現在的 hardening 從「一包混在一起」拆成兩層：
- `domain-stable normalization`
- `dataset-backed heuristic`

這隻 PR 要做的事：

1. 在 normalizer / trace / docs 中加入 rule classification。
2. 讓 trace 或 artifact 可看出某次修正屬於哪一層。
3. 補測試，確認規則分類能被穩定輸出。
4. 先不改太多規則內容，先把分類框架釘住。

建議碰的檔案：

- `src/gh_search/normalizers/keyword_rules.py`
- `src/gh_search/normalizers/__init__.py`
- `src/gh_search/tools/validate_query.py`
- `src/gh_search/schemas/logs.py`
- `src/gh_search/agent/loop.py`
- `tests/normalizers/test_keyword_rules.py`
- `tests/test_tool_validate_query.py`

不要做的事：

- 不順手大改所有 multilingual 規則。
- 不在這隻 PR 內補大量新 dataset。

驗證方式：

- trace 可分辨通用規則與資料集修補規則
- 至少三類規則已完成分類

預估大小：

- `7-12` 個檔案
- `250-650` 行 diff

## PR5. Semantic Family Pack A: Stars + Ranking

目的：

- 把最穩定、最值得保留的兩個 family 先做紮實。

這隻 PR 要做的事：

1. 補 `stars_lower_bound` / `stars_upper_bound` paraphrase 與 alias 測試。
2. 補 `ranking_intent` paraphrase 與 alias 測試。
3. 必要時微調對應 hardening 規則，讓它們更像 semantic family 規則，而不是單題規則。
4. 若 formal eval replacement 題與這兩類相關，可在這隻 PR 補回。

建議碰的檔案：

- `datasets/eval_dataset_paraphrase.json`
- `datasets/eval_dataset_alias.json`
- `src/gh_search/normalizers/keyword_rules.py`
- `src/gh_search/tools/validate_query.py`
- `tests/normalizers/test_numeric_evidence.py`
- `tests/normalizers/test_ranking_intent.py`
- `tests/test_keyword_integration.py`
- `tests/test_paraphrase_harness.py`

不要做的事：

- 不把 language/date 一起塞進來。

驗證方式：

- `more than / over / > / 超過` 都能落到同一 lower-bound 語義
- `popular / top / most starred` 都能落到同一 ranking intent

預估大小：

- `8-14` 個檔案
- `400-850` 行 diff

## PR6. Semantic Family Pack B: Language + Date

目的：

- 補第二批比較穩定、但比 stars/ranking 更容易漂的 family。

這隻 PR 要做的事：

1. 補 `language_evidence` paraphrase / alias 測試。
2. 補 `date_constraints` paraphrase 測試。
3. 收斂 language leak 與 date phrasing 的 hardening 規則。
4. 讓這兩族也進 paraphrase harness。

建議碰的檔案：

- `datasets/eval_dataset_paraphrase.json`
- `datasets/eval_dataset_alias.json`
- `src/gh_search/normalizers/keyword_rules.py`
- `src/gh_search/tools/validate_query.py`
- `tests/normalizers/test_language_evidence.py`
- `tests/test_parser_prompt_date_rules.py`
- `tests/test_keyword_integration.py`
- `tests/test_paraphrase_harness.py`

不要做的事：

- 不碰 ambiguous multilingual boundary。

驗證方式：

- `python repos`、`repos written in python`、`py repos` 的處理一致
- `after 2023`、`before 2020`、`from 2024` 的 mapping 穩定

預估大小：

- `8-14` 個檔案
- `400-850` 行 diff

## PR7. Boundary + Ambiguity Handling + README Sync

目的：

- 最後才處理那些本來就不該硬解的題。
- 把 boundary / ambiguous / failure 的故事收斂到 README 與正式文件。

這隻 PR 要做的事：

1. 新增 boundary dataset。
2. 新增 ambiguity handling tests。
3. 讓 scorer / runner 對這些桶輸出 outcome-based summary。
4. 更新 README，說清楚：
   - 哪份 dataset 才算正式主分數
   - 哪些是 robustness / boundary / failure 用
   - 哪些 hardening 仍屬 heuristic

建議碰的檔案：

- `datasets/eval_dataset_boundary.json`
- `datasets/eval_dataset_ambiguous.json`
- `src/gh_search/eval/scorer.py`
- `src/gh_search/eval/runner.py`
- `tests/test_boundary_cases.py`
- `tests/test_ambiguity_handling.py`
- `README.md`
- `specs/datasets/HUMAN_REVIEW_SUMMARY.md`

不要做的事：

- 不再大改 stars/ranking/language/date 規則。

驗證方式：

- `newest` 不會被自動硬等同 `sort=updated`
- `not too old but not too new` 不會被亂補成假日期
- README、dataset、summary 三者口徑一致

預估大小：

- `7-12` 個檔案
- `300-700` 行 diff

## 4. PR 之間的依賴

依賴順序建議固定如下：

1. `PR1 -> PR2`
2. `PR2 -> PR3`
3. `PR3 -> PR4`
4. `PR4 -> PR5`
5. `PR5 -> PR6`
6. `PR6 -> PR7`

說明：

- `PR1` 不做分桶治理，後面每一隻 PR 都會建立在不穩 dataset 上。
- `PR2` 不先把 bucket plumbing 接好，後面的 paraphrase / ambiguity dataset 沒地方掛。
- `PR4` 不先把 hardening 分層，後面 family PR 還是會看起來像 benchmark patch。

## 5. 每隻 PR 的 review 檢查表

每一隻 PR 開之前，都先用同一張表檢查：

1. 這隻 PR 有沒有只做一件大事？
2. 檔案數有沒有壓在 `20` 以內？
3. diff 有沒有壓在 `1000` 行以內？
4. 有沒有先寫測試，再補實作？
5. 有沒有把不相干的 README / refactor 順手混進來？
6. reviewer 能不能在 10 分鐘內理解這隻 PR 的目的？

如果第 6 點做不到，就代表 PR 還太大。

## 6. 最後建議

這個 refactor 最容易失敗的方式，就是把它當成「一次大重構」來做。  
比較穩的做法，是把它當成三種工作交錯前進：

1. dataset 治理
2. harness 能力
3. semantic family hardening

每次只推進一小步，讓每隻 PR 都能被 reviewer 清楚判斷：

- 這隻 PR 有沒有把問題定義得更乾淨？
- 這隻 PR 有沒有讓 evidence 更完整？
- 這隻 PR 有沒有真的把規則從單題修補，往語義 family 推進？
