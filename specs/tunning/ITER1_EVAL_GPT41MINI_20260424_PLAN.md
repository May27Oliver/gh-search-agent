# Eval Hardening Plan

> **Design constraint (must read before any change)**
>
> 所有 hardening / tuning 改動必須通過「換 model 後仍然成立」的測試。
> 優先投資 **model-agnostic 層**（scorer、deterministic normalizer、gate rules、eval harness）。
> **Model-specific 層**（parser prompt、few-shot、gate wording）必須隔離在 per-model appendix，
> 且 commit 前須跑至少 2 個 model 的 multi-model falsification。
> Release gate 是「跨 model 同時 `> 85%`」，不是單一 model 拿 85%。
> 詳見 §4。

## 1. 背景

- eval run id: `eval_gpt41mini_20260424`
- model: `gpt-4.1-mini`
- dataset: `datasets/eval_dataset_reviewed.json`
- score: `3 / 30 = 10.00%`

這份文件的目的不是描述單次分數，而是把本輪結果轉成後續可執行的 hardening / tuning 計畫。

## 2. 本輪總結

整體結果：

- `success`: 19
- `rejected`: 7
- `no_results`: 4
- `correct`: 3

核心判讀：

1. 系統大多數情況可以跑完整條 pipeline，沒有大量 execution failure。
2. 主要問題不是「跑不起來」，而是「產生的 structured query 不夠貼 ground truth」。
3. 目前失分主因集中在 parser / intention gate / query normalization，不在 GitHub client。

## 3. 錯誤分類

### 3.1 Ambiguity Gate 過度拒絕

影響題目：

- `q004`
- `q009`
- `q019`
- `q020`
- `q021`
- `q022`
- `q030`

症狀：

- `final_outcome = rejected`
- `terminate_reason = ambiguous_query`
- `predicted_structured_query = null`

判讀：

- `intention_judge` 太保守
- 把可 parse 的 query 提前擋掉
- 這類題目連 parser 都沒機會工作

### 3.2 Keyword Normalization / Phrase Handling 不穩

影響題目：

- `q002`
- `q003`
- `q005`
- `q006`
- `q007`
- `q008`
- `q010`
- `q011`
- `q014`
- `q016`
- `q017`
- `q018`
- `q023`
- `q028`

典型症狀：

- multi-word phrase 被拆開
- 單數變複數
- parser 自行擴寫或添加語意
- 多語 query 沒 canonicalize 成 dataset 預期形式

代表例子：

- `machine learning` -> `machine`, `learning`
- `framework` -> `frameworks`
- `spring boot` -> `spring`, `boot`
- `library` -> `libraries`

判讀：

- parser prompt 對 phrase preservation 不夠強
- 缺乏 deterministic keyword normalization 層

### 3.3 Date Parsing / Temporal Normalization 錯誤

影響題目：

- `q013`
- `q017`
- `q018`

典型症狀：

- `last year`
- `this year`
- `from 2024`

被轉成錯誤年份，或只補了一側邊界。

判讀：

- parser 在 relative time 和 year-range 規則上不穩
- 缺少 deterministic date normalization

### 3.4 Language Inference 過度推定

影響題目：

- `q001`

典型症狀：

- ground truth `language = null`
- parser 自行推成 `JavaScript`

判讀：

- parser 不應從 `React` 自動推定語言
- language 欄位應只在 query 明確指定時填入

### 3.5 Retrieval No Results

影響題目：

- `q024`
- `q026`
- `q027`
- `q029`

典型症狀：

- final outcome = `no_results`
- 但根因仍然是 parser 產生了錯 query

代表例子：

- typo 沒被修成 canonical keyword
- 中文詞彙原樣進 keyword
- 日文 query 被加了多餘語意

判讀：

- 這不是 GitHub API 的主要問題
- 仍然屬於 parser / normalization 問題

## 4. 核心原則：Model-Agnostic vs Model-Specific Layer

最終 release gate 是「`> 85%` accuracy **橫跨 model set**」，不是「`gpt-4.1-mini` 拿 85%」。任何 tuning 行動都必須通過一個測試：**換一個 model 之後還會成立嗎？**

因此在動手之前，先把系統分成兩層。

### 4.1 Model-Agnostic Layer（換 model 仍然有效）

這層的修改是對整個 task 的結構化投資，是優先投資目標：

- Scorer canonicalization rules（lowercase / phrase merge / lemmatize / language-redundancy）
- Deterministic normalizers（`dates.py`、`noisy_input.py` 之類）
- Intention gate 的 rule-based 判定（有 topic / language / stars / date 任一訊號則放行）
- Schema 本身與 contract 定義
- Eval harness（per-field recall、golden tests、regression gate、model matrix）
- Decoding 設定（`temperature = 0`）

### 4.2 Model-Specific Layer（換 model 可能失效或反效果）

這層是特定 model 的補丁，預期會隨 model 變動：

- Parser prompt 針對性措辭（例：「不要把 `framework` 改成 `frameworks`」）
- Few-shot examples
- Gate / parser prompt wording 對「保守程度」的微調

這層改動必須明確 tag，且不能和 core prompt 混在一起。

### 4.3 Prompt 架構

Parser prompt 實作上拆成兩段：

- **Core prompt**：schema、欄位語意、contract。model 無關，所有 model 共用。
- **Per-model appendix**：該 model 的已知 quirk。可有可無、可替換。

`prompt_version` 跟著分，例如：

```
prompt_version = "core-v2 + appendix-gpt41mini-v1"
```

換 model 時只動 appendix，不動 core。

### 4.4 Scorer 是最大的 model-agnostic hedge

Scorer canonicalization 是**目前唯一對所有現在與未來 model 都有效的投資**。例如 `example` vs `examples` 的 mismatch 在 scorer 層解掉後，任何 model 都不會再被這條規則扣分。

這是 Iteration 0 必須優先 scorer audit 的**第二個理由**：

- 第一個理由：先確定 metric 對不對
- 第二個理由：scorer 改動是 model-agnostic hedge，ROI 最高

### 4.5 Multi-Model Falsification

Commit 任何 prompt / few-shot / gate wording 改動之前，必須跑正式評測模型集中 **至少 2 個、且 provider 不同** 的 eval。同 provider 內比對（例如 OpenAI 家族互比）**不算** falsification，無法證明改動具有跨 provider / open-weight 的可遷移性。

#### 正式評測模型集（single source of truth）

來源：[`specs/target/MVP_SPEC.md`](../target/MVP_SPEC.md) §模型選型、[`specs/main/EVAL.md`](../main/EVAL.md)。

| model | 類型 | provider | 用途 |
|---|---|---|---|
| `gpt-4.1-mini` | closed-source | OpenAI | cheap baseline |
| `claude-sonnet-4` | closed-source | Anthropic | mid-tier 主力 |
| `DeepSeek-R1` | open-weight | DeepSeek | 正式參賽 open-weight |

#### Falsification 選型規則

- 至少 **2 個**，且必須 **跨 provider**（不可兩個都 OpenAI 或兩個都 closed-source）
- Early iteration 推薦預設組合：`gpt-4.1-mini` + `claude-sonnet-4`（快、便宜、跨 provider）
- 接近 release 時必須三個模型全跑（含 open-weight 的 `DeepSeek-R1`）

#### 通過判定（採 `±3%` noise band，對應 30 題 dataset 的單題變動 `3.3%`）

| 結果 | 判定 | 落地位置 |
|---|---|---|
| Target model 改善 `>= 3%`；其他 model 未回歸（`drop <= 3%`）；所有 model golden tests 不回歸 | Task-level 改進 | 進 `core` prompt / agnostic layer |
| Target model 改善；但其他 model 回歸 `> 3%` 或 golden tests 回歸 | Model-specific 改進 | 只能進 `appendix-{model}-v*` |
| Target model 改善 `< 3%`（雜訊帶內） | 無明顯收益 | 退回，下次再試 |
| Target model 回歸，或**任何 model 的 golden tests** 回歸 | 直接否決 | 退回，不分層 |

不再採用「兩個 model 都必須同步上升」的剛性規則——在早期 iteration，不同 model 的自然波動可能把真正的 task-level 改進一起擋掉。核心條件改為「**target 改善 + 其他 model 不得顯著回歸 + golden tests 全員 pass**」。

成本：每次多跑 30 題 × 1 個 closed-source model，`< $0.1`；`DeepSeek-R1` 若透過官方 API 或 hosted inference 執行，成本與延遲需另記錄，但仍遠小於方向錯誤的 rework 成本。

### 4.6 Model Matrix：Canonical Artifact

每一次 iteration 必須在固定路徑產出 cross-model 彙整，否則該 iteration 不算完成。

#### 檔案佈局

單模型 eval run（現狀不變）：

```
artifacts/eval/<eval_run_id>/
  per_item_results.jsonl
  model_summary.json
  run_config.json
```

Cross-model 彙整（新增層）：

```
artifacts/eval/iterations/<iteration_id>/
  model_matrix.json      # 機器可讀
  model_matrix.md        # 人類可讀（為 report / PR description 用）
  refs.json              # 指回組成這個 iteration 的 <eval_run_id> 清單
```

`<iteration_id>` 命名規則：`iter_{N}_{slug}_{YYYYMMDD}`，例如 `iter_0_baseline_20260424`、`iter_1_gate_relax_20260428`。

#### `model_matrix.json` Schema

```json
{
  "iteration_id": "iter_0_baseline_20260424",
  "prompt_version": "core-v2 + appendix-gpt41mini-v1",
  "dataset": "datasets/eval_dataset_reviewed.json",
  "dataset_size": 30,
  "rows": [
    {
      "model_name": "gpt-4.1-mini",
      "provider": "openai",
      "eval_run_id": "eval_gpt41mini_20260424",
      "accuracy": 0.10,
      "correct": 3,
      "total": 30,
      "rejected": 7,
      "no_results": 4,
      "golden_passed": "3/3",
      "per_field_recall": {
        "keywords": 0.0,
        "language": 0.0,
        "created_after": 0.0,
        "created_before": 0.0,
        "min_stars": 0.0,
        "max_stars": 0.0
      }
    },
    { "model_name": "claude-sonnet-4", "provider": "anthropic", "...": "..." },
    { "model_name": "DeepSeek-R1", "provider": "deepseek", "...": "..." }
  ]
}
```

#### 產出責任

- 由 **eval runner** 產出。建議在 CLI 層新增 `gh-search eval matrix --iteration-id <id> --models <m1,m2,...>`，負責：
  1. 依序驅動指定 model 各跑一次 smoke
  2. 讀取各自的 `model_summary.json` 與 `per_item_results.jsonl`
  3. 計算 per-field recall、`golden_passed`
  4. 聚合寫入 `model_matrix.{json,md}` + `refs.json`
- 過渡期可先用 `scripts/build_model_matrix.py` 作為 post-processing aggregator（讀既有 eval run，不驅動跑 eval），先把 artifact 落地再把自動化補上。
- **owner**：agent loop / eval subsystem。CLI subcommand 與 matrix schema 任一改動需在此節同步更新。

#### Release gate 與 Iteration gate

所有 gate 一律作用於 `model_matrix.json.rows` 的 **每一個 row**（row-wise）：

- Release gate：所有 row `accuracy > 85%`，且所有 row `golden_passed == "3/3"`
- Iteration pass（§10）：每個 row 同時滿足該 iteration 標準，否則 iteration 不算通過

## 5. Scorer Review

在調 parser 之前，必須先回答一個問題：

目前的 canonical scorer 是否把「語意等價但表面不完全一致」的 query 過度判錯？

這輪最明顯的例子：

- `['machine learning']` vs `['machine', 'learning']`
- `['example']` vs `['examples']`
- `['framework']` vs `['frameworks']`
- `language='Rust'` 且 keywords 多帶一個 `rust`

這些案例裡，至少有一部分比較像 scorer brittleness，而不是 parser 真正理解錯誤。

### 5.1 先做 scorer 審查，再決定 parser 修法

先執行這三步：

1. 抽樣審查所有 keyword mismatch 題
2. 標記每題屬於：
   - truly wrong
   - semantically equivalent but schema-different
   - unclear / needs dataset decision
3. 只在 metric 確認後，再決定要不要把修正壓到 parser / normalizer

### 5.2 建議的 scorer 調整順序

先做最便宜的 canonicalization：

1. lowercase
2. phrase merge
3. 常見單複數 lemmatize
4. 明確允許 `language` 已表達的語詞不必重複放在 `keywords`

不建議一開始就做太寬鬆的 fuzzy match。原則是：

- 保留 deterministic
- 保留可解釋性
- 只處理「資料集規約差異」，不要把真正錯誤也洗成正確

### 5.3 Scorer Review 通過標準

- 先完成 14 題 keyword mismatch 的人工標註
- 明確區分：
  - scorer 問題
  - parser 問題
- 再開始下一輪 parser tuning

## 6. 修正優先級

### P0. 放鬆 Ambiguity Gate

目標：

- 讓更多「仍可映射到 GitHub repo search」的題目進入 parser

修正方向：

1. `intention_judge` 只拒絕真正 off-domain 的 query
2. 對於有 topic / language / stars / date 任一訊號的 query，優先放行
3. 不要因為 query 不夠精確就直接判 `ambiguous_query`

預期收益：

- 合理回收約 4 題
- `q019`、`q020` 可能仍應維持 rejected
- `q030` 可能屬於 adversarial contradictory constraint，不應算成 gate 的主要責任

建議影響檔案：

- `src/gh_search/tools/intention_judge.py`
- 對應 prompt / tests

驗證：

- `q004`、`q009`、`q021`、`q022` 至少大多數不再被提前拒絕
- `rejected` 題數由 `7` 降到 `<= 4`

如果驗證不過：

- 繼續縮小 `ambiguous` 判定條件
- 只保留真正無法落到 GitHub repo search domain 的拒絕

### P1. Parser Output Policy

目標：

- 減少 phrase 被拆詞、詞形變化、語意擴寫與過度語言推定造成的 mismatch

修正方向：

1. 先改 parser prompt 與 few-shot examples：
   - 保留原始 phrase
   - 不要擅自拆開 `machine learning`、`spring boot`、`react native`
   - 不要把 `framework` 改寫成 `frameworks`
   - 不要加入 query 中不存在的新詞
   - 不要在 query 未明示時自行填 `language`
2. 將 parser decoding 固定為 deterministic
3. 只有 prompt / few-shot 仍不穩時，才新增 lightweight normalization layer

預期收益：

- 這一類影響 14 題，是最大失分來源
- 也一併處理 `q001` 的 language over-inference

建議影響檔案：

- `src/gh_search/tools/parse_query.py`
- 對應 unit tests
- 若 prompt-only 不夠，再考慮新增 `src/gh_search/normalizers/keywords.py`

驗證：

- keyword mismatch 題數至少減半
- `success but wrong` 的案例明顯下降

如果驗證不過：

- 增加 few-shot examples
- 再加入 deterministic post-processing，而不是一開始就開新 module

### P2. 補 deterministic Date Normalization

目標：

- 把 `last year`、`this year`、`from 2024` 等時間語意穩定映射

修正方向：

1. 把 relative date parsing 從 prompt-only 改為 deterministic rule
2. 明定：
   - `last year`
   - `this year`
   - `from YEAR`
   - `in YEAR`
   - `before YEAR`
   - `after YEAR`

預期收益：

- 可回收至少 3 題直接時間失分

建議影響檔案：

- `src/gh_search/tools/parse_query.py`
- 可能新增 `src/gh_search/normalizers/dates.py`

驗證：

- `q013 q017 q018` 的日期欄位錯誤清零

如果驗證不過：

- 把 date extraction 提前到 parser 前的 preprocessor

### P3. Multilingual / Noisy Input

目標：

- 處理 typo、中文、日文 query 的 canonicalization

修正方向：

1. 先做 ablation：
   - 把 typo / 非英文 query 人工改乾淨後再送 parser
   - 確認根因是 typo、多語，還是 schema 本身不清楚
2. parser prompt 先要求輸出 canonical English keywords
3. 只有 prompt 仍不穩時，才新增小型 typo / translation dictionary

預期收益：

- 主要回收 `q024 q026 q027 q029`

建議影響檔案：

- `src/gh_search/tools/parse_query.py`
- 若 prompt-only 不夠，再考慮新增 `src/gh_search/normalizers/noisy_input.py`

驗證：

- `no_results` 題數由 `4` 降到 `<= 1`

如果驗證不過：

- 再做人手定義的小型 normalization dictionary
- 暫時不要依賴模型自己翻譯與修 typo

## 7. Regression Guard

目前唯一已知穩定答對的題目：

- `q012`
- `q015`
- `q025`

每一題回歸都等於總分直接掉 `3.3%`，所以這 3 題必須凍結成 golden tests。

要求：

1. 為 `q012`、`q015`、`q025` 建立 snapshot / golden tests
2. 每輪 tuning 後必須全部維持 correct
3. 若任一題回歸，該 iteration 不算通過

## 8. 建議執行順序

### Iteration 0

- 跑 multi-model baseline：
  - 從正式評測模型集（`gpt-4.1-mini` / `claude-sonnet-4` / `DeepSeek-R1`）選 **至少 2 個、且跨 provider**
  - 推薦起手組合：`gpt-4.1-mini` + `claude-sonnet-4`
- 產出 `artifacts/eval/iterations/iter_0_baseline_YYYYMMDD/model_matrix.{json,md}`
- 比對各 model failure mode 是否重疊，標註每題為 task-level vs model-specific 問題
- 完成 scorer review
- pin 住 decoding 設定（`temperature = 0`）
- 建立 golden tests（`q012`、`q015`、`q025`），matrix 中每個 model row 都必須 pass

目標：

- 先確定 metric 對不對
- 先確認要修的是 model-agnostic 還是 model-specific 層
- 先防止既有 3 題在任何 model 上回歸

### Iteration 1

- 放鬆 ambiguity gate
- 強化 parser output policy

目標：

- 先把 `rejected` 大幅降下來
- 先讓更多題進入可評分狀態

### Iteration 2

- 只在必要時加 deterministic keyword normalization
- 加 deterministic date normalization
- 處理 typo / multilingual 的 prompt-first 修法

目標：

- 解決大多數 `success but wrong`

## 9. 每輪驗證方式

每一輪調整後都必須做這三件事：

1. 跑單元測試

```bash
pytest -q tests
```

2. 重跑正式 eval dataset

```bash
GH_SEARCH_MODEL=gpt-4.1-mini gh-search smoke \
  --dataset datasets/eval_dataset_reviewed.json \
  --eval-run-id <new_eval_run_id>
```

3. 若本輪涉及 cross-model 驗證，先分別跑各 model 的 eval run，再聚合成 matrix

```bash
GH_SEARCH_MODEL=gpt-4.1-mini gh-search smoke \
  --dataset datasets/eval_dataset_reviewed.json \
  --eval-run-id eval_gpt41mini_<iteration_id>

GH_SEARCH_MODEL=claude-sonnet-4 gh-search smoke \
  --dataset datasets/eval_dataset_reviewed.json \
  --eval-run-id eval_claude_sonnet4_<iteration_id>

python scripts/build_model_matrix.py \
  --iteration-id <iteration_id> \
  --dataset datasets/eval_dataset_reviewed.json \
  --runs eval_gpt41mini_<iteration_id> eval_claude_sonnet4_<iteration_id>
```

若是 Iteration 2 或接近 release，則補齊第三個正式模型：

```bash
GH_SEARCH_MODEL=DeepSeek-R1 gh-search smoke \
  --dataset datasets/eval_dataset_reviewed.json \
  --eval-run-id eval_deepseek_r1_<iteration_id>

python scripts/build_model_matrix.py \
  --iteration-id <iteration_id> \
  --dataset datasets/eval_dataset_reviewed.json \
  --runs eval_gpt41mini_<iteration_id> eval_claude_sonnet4_<iteration_id> eval_deepseek_r1_<iteration_id>
```

4. 對比新舊 `per_item_results.jsonl` 與 `model_matrix.json`

至少比較：

- accuracy
- `rejected` 題數
- `no_results` 題數
- keyword mismatch 題數
- date mismatch 題數
- per-field recall：
  - keywords
  - language
  - created_after / created_before
  - min_stars / max_stars
- `q012`、`q015`、`q025` 是否維持 correct

另外固定記錄：

- `temperature = 0`
- `prompt_version`（例如 `core-v2 + appendix-gpt41mini-v1`）
- model snapshot date / run date

若本輪改動涉及 prompt / few-shot / gate wording（model-specific layer）：

- 必須跑 `>= 2` 個 model
- 提供 model matrix 對比（accuracy、rejected、no_results、per-field recall、golden_passed）
- 通過標準需**所有 model row 同時滿足**，否則該改動不得進 core prompt
- 若改動僅對單一 model 有效，只能以 `appendix-{model}-v*` 形式保留在 per-model appendix

## 10. 每輪通過標準

### Iteration 0 通過標準

- multi-model baseline 完成：**至少 2 個正式評測模型、且跨 provider**（§4.5）
- `artifacts/eval/iterations/iter_0_*/model_matrix.{json,md}` 已產出並符合 §4.6 schema
- 已完成 task-level vs model-specific failure 標註
- scorer review 完成
- golden tests 建立完成，**matrix 中每個 model row 都 pass**
- 已確認 `temperature = 0`
- `prompt_version` 已採用 `core-*` / `appendix-*` 分層命名

### Iteration 1 通過標準

以下條件必須對 `model_matrix.json.rows` 中 **每一個 model row 同時成立**（row-wise gate）：

- `accuracy >= 25%`
- `rejected` 題數 `<= 4`
- `q012`、`q015`、`q025` 在該 model 上不得回歸

任一 model row 未達標，該 iteration **不算通過**，不得進入 Iteration 2。解讀時仍套用「注意」中的 `±3%` noise band。

### Iteration 2 通過標準

到此 iteration **必須跑滿所有三個正式評測模型**（含 `DeepSeek-R1`）。以下條件對 `model_matrix.json.rows` 中 **每一個 model row 同時成立**（row-wise gate）：

- `accuracy >= 50%`
- keyword mismatch 題數相對 `iter_0_baseline` 同 model row **減半**
- date mismatch 題數 `<= 1`
- `no_results` 題數 `<= 1`
- `q012`、`q015`、`q025` 在該 model 上不得回歸

任一 model row 未達標，該 iteration **不算通過**。

注意：

- 30 題 dataset 的單題變動約等於 `3.3%`
- 這些門檻只能當 iteration guide，不應被解讀為高精度統計結論
- 每輪應至少附帶 `±3%` 的解讀帶寬

### Final target

- 所有正式模型 `> 85% accuracy`

補充：

- 由於目前 dataset 只有 30 題，最終報告應同時附：
  - error breakdown
  - per-field recall
  - case-type breakdown
  - **model matrix**（所有正式模型的 per-model accuracy / rejected / no_results / golden_passed）
- 若時間允許，應優先把 dataset 擴到 `>= 100` 題，再把 `85%` 當較穩定的 release gate

## 11. 本輪結論

目前系統不是 execution-first 的失敗，而是 parser-first 的失敗。

換句話說：

- GitHub client 不是當前主要瓶頸
- scorer 有可能是重要瓶頸之一，至少需要先完成 review
- 真正應該優先修的是：
  - scorer canonicalization policy
  - `intention_judge`
  - `parse_query`
  - 只有必要時才加入 parser 後的 normalization layer

所以後續 hardening 應以：

`scorer review -> gate relaxation -> parser output policy -> date normalization -> multilingual/noisy prompt-first strategy`

作為主軸，而不是先更換模型或修改 GitHub execution 層。

最重要的前提（對 Codex 與任何後續協作者同樣適用）：

**所有改動必須通過「換 model 是否仍然成立」的測試。**

- Model-agnostic 層（scorer、deterministic normalizer、gate rules、eval harness）是優先投資目標
- Model-specific 層（parser prompt、few-shot、gate wording）必須隔離在 per-model appendix
- 任何 model-specific 改動 commit 前須通過 multi-model falsification（`>= 2` 個 model 參與；target model 必須改善，其他 model 不得顯著回歸，golden tests 必須全員通過）
- Release gate 是「**跨 model 同時 `> 85%`**」，不是「`gpt-4.1-mini` 單獨 `> 85%`」

若某個改動只對 `gpt-4.1-mini` 有效，預設視為 overfitting；要保留必須明確標為 appendix-only，並在該 model 不再是 target 時第一時間砍掉。
