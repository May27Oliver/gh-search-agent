# GitHub Search CLI Agent

把自然語言查詢轉成 GitHub repository search，透過 bounded agent loop 完成：

`intention_judge -> parse_query -> validate_query（檢查並修正查詢結構） -> compile_github_query -> execute_github_search`

這份 repo 是 take-home 最終交付版本，包含：

- 可執行的 CLI agent
- 可回查的執行紀錄與評測結果檔案
- 30 題 reviewed eval dataset
- 3 個正式模型的跨平台比較
- 從 baseline 到 final 的修正與調整記錄

## 最終結果

正式 final pipeline 對 `datasets/eval_dataset_reviewed.json`（30 題）的最終成績：

| model             | provider  | deployed model id / access                                                      | final accuracy | correct |
| ----------------- | --------- | ------------------------------------------------------------------------------- | -------------- | ------- |
| `gpt-4.1-mini`    | OpenAI    | `gpt-4.1-mini` via OpenAI API                                                   | `93.33%`       | `28/30` |
| `claude-sonnet-4` | Anthropic | `claude-sonnet-4` via Anthropic API                                             | `96.67%`       | `29/30` |
| `DeepSeek-R1`     | DeepSeek  | 正式模型名 `DeepSeek-R1`，實際呼叫 id 為 `deepseek-reasoner`，透過 DeepSeek API | `93.33%`       | `28/30` |

這表示 take-home 的主要驗收門檻都已達成：

- CLI 可端到端執行
- reviewed dataset 已建立且可重跑
- 3 模型比較已完成，包含 closed-source 與 open-weight
- 所有正式評測模型都超過 `85% accuracy`

## Before / After

最早 baseline（`iter_0_baseline_20260424`）只有單模型 `gpt-4.1-mini`，accuracy 為 `10.00%`（`3/30`）。

經過幾輪用程式規則做的後處理修正後，最終版本達到：

| stage                     | GPT     | Claude  | DeepSeek |
| ------------------------- | ------- | ------- | -------- |
| early baseline            | `3/30`  | -       | -        |
| final pipeline (`iter11`) | `28/30` | `29/30` | `28/30`  |

改善主因不是一直加提示詞，而是把那些已經在評測資料裡反覆出現、而且判斷規則很明確的錯誤，改成由後處理程式穩定修正。這樣比一直把更多例外情況塞進 parser 的提示詞更穩，也更容易測試、追查問題，並套用到不同模型上。

## 系統設計

### Runtime flow

1. `intention_judge`
   - 判斷 query 是否屬於可支援的 GitHub repo search
2. `parse_query`
   - 由模型產出 `structured_query`
3. `validate_query`（檢查並修正查詢結構）
   - 用固定規則修正常見錯誤，或移除不該出現的欄位
4. `compile_github_query`
   - 轉成 GitHub Search API query string
5. `execute_github_search`
   - 執行 GitHub repository search，回傳摘要結果

### 為什麼把 hardening 放在 `validate_query`（檢查並修正查詢結構）

這份作業後半段的核心做法是：

- 不持續把更多規則塞進 parser 的提示詞
- 盡量把評測資料裡反覆出現的已知錯誤，改成由程式規則在後處理階段穩定修正
- 讓不同模型共用同一套修正規則

這樣做的好處是：

- 比較容易套用到不同模型
- 比較容易寫測試
- 比較容易找出是哪一層出了問題
- 對像 DeepSeek 這種對提示詞長度和複雜度比較敏感的模型更穩

## 代表性失敗案例

正式的 failure case 資料檔在：

- [datasets/failure_cases.jsonl](datasets/failure_cases.jsonl)

這份資料檔記錄了 baseline 與 hardened 階段的真實失敗案例，且每筆都附：

- `run_id`
- `session_id`
- `eval_run_id`
- `session_log_path`

可直接回查對應的執行紀錄與評測檔案。

幾個代表性案例：

| case                      | baseline / hardened | 症狀                                                       | 後續處理                                  |
| ------------------------- | ------------------- | ---------------------------------------------------------- | ----------------------------------------- |
| `q001`                    | baseline            | 把 `React` 誤當成 `JavaScript`，還憑空加上 `min_stars=100` | Iter9 清掉多餘的 language 推斷            |
| `q027`                    | baseline            | 中文 `爬蟲套件` 沒轉成英文關鍵字，造成查得到但結果品質差   | Iter8 補多語關鍵字正規化                  |
| `q030`                    | baseline            | `>500 且 <100` 被拒絕或前後對調，無法保留原本的衝突條件    | Iter10 保留 `501..99` 這組原始條件        |
| `q013/q015/q026/q027` DSK | hardened            | 數字條件都對了，但還是穩定漏掉 `sort=stars desc`           | Iter11 補 ranking intent 對應的排序規則   |
| `q018` GPT                | hardened residual   | `spring boot` / `created_before` 仍偶爾遺失                | 視為 parser/date 尾巴，沒有再硬加規則去補 |

## Hardening 紀錄

完整調整記錄在：

- [specs/tunning/README.md](specs/tunning/README.md)

最後幾輪最有效的修正：

| iteration | 主題                               | 主要效果                                             |
| --------- | ---------------------------------- | ---------------------------------------------------- |
| Iter7     | 清理裝飾詞                         | 清掉 `projects` / `implementations` 這類不該留下的字 |
| Iter8     | 多語關鍵字正規化                   | 收斂中日文複合詞                                     |
| Iter9     | 清掉多餘的 language 推斷           | 防止 `React/Vue` 被誤填進 `language`                 |
| Iter10    | stars / 數字條件修正               | 保留嚴格邊界與互相衝突的星數條件                     |
| Iter11    | ranking intent 對應 stars 排序規則 | 補回 DSK 穩定遺失的 `sort/order`                     |

Iter10 / Iter11 之後，三模型已全部站上 `90%+`。

## 模型比較

### 最終比較

| model             | provider  | accuracy | 剩餘的小尾巴                               |
| ----------------- | --------- | -------- | ------------------------------------------ |
| `gpt-4.1-mini`    | OpenAI    | `28/30`  | `q009` 缺 `vue 3`、`q018` parser/date 尾巴 |
| `claude-sonnet-4` | Anthropic | `29/30`  | `q029` 缺 `react`                          |
| `DeepSeek-R1`     | DeepSeek  | `28/30`  | `q009` 單複數尾巴、`q029` 裝飾詞殘留       |

### 最終 outcome 分布

iter11 的結果分布：

| model             | success | execution_failed | max_turns_exceeded |
| ----------------- | ------- | ---------------- | ------------------ |
| `gpt-4.1-mini`    | `24`    | `4`              | `2`                |
| `claude-sonnet-4` | `25`    | `3`              | `2`                |
| `DeepSeek-R1`     | `26`    | `2`              | `2`                |

## Learnings

1. 很多失分不是「模型不夠強」，而是模型產出的欄位沒有再被穩定修正。
2. 對這類題目來說，用 `validate_query`（檢查並修正查詢結構）做後處理，比一直往提示詞塞更多範例更穩。
3. DeepSeek-R1 對提示詞複雜度特別敏感，所以把規則往後處理搬，效果反而更好。
4. 多語、數字邊界、排序意圖這三類問題，只要範圍切乾淨，就很適合拆成小步驟逐輪修。
5. 可回查的評測紀錄很重要。若沒有 `per_item_results`、`run_id/session_id`、retrieved repo 摘要，就很難知道到底是模型漂移，還是這輪修改真的有副作用。

## 已知限制

目前仍有幾個刻意沒有再擴大處理的小尾巴：

- 少量主題詞 / 裝飾詞殘留
  - 例如 `q009` 的 `vue 3`
  - 例如 `q029` 的 `project`
- 少量 parser/date 尾巴
  - 例如 `q018 GPT`
- 本專案只支援 GitHub repository search，不處理 issue / PR / code search
- `README language` / repository natural-language content 等需求不在目前 schema 內，僅能保守保留為 `keywords`

這些限制都有明確記錄，但不影響最後交件標準。

## 專案結構

```text
src/gh_search/
  cli.py
  config.py
  compiler.py
  validator.py
  agent/
  eval/
  github/
  llm/
  logger/
  normalizers/
  schemas/
  tools/

datasets/
  eval_dataset_reviewed.json
  failure_cases.jsonl

artifacts/
  eval/
  logs/

specs/
  main/
  tunning/
```

## 環境需求

- Python 3.10+
- OpenAI API key
- GitHub personal access token

若要跑三模型比較，另外需要：

- `ANTHROPIC_API_KEY`
- `DEEPSEEK_API_KEY`

## 安裝

### 一鍵安裝

```bash
./install.sh
```

常用選項：

```bash
./install.sh --clean
./install.sh --no-dev
./install.sh --help
```

安裝後啟用 venv：

```bash
source .venv/bin/activate
```

### 手動安裝

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e '.[dev]'
```

## 設定

先建立 `.env`：

```bash
cp .env.example .env
```

填入：

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
DEEPSEEK_API_KEY=...
GITHUB_TOKEN=...
GH_SEARCH_MODEL=gpt-4.1-mini
GH_SEARCH_MAX_TURNS=5
GH_SEARCH_LOG_ROOT=artifacts/logs
```

說明：

- `OPENAI_API_KEY`：OpenAI provider
- `ANTHROPIC_API_KEY`：Claude provider
- `DEEPSEEK_API_KEY`：DeepSeek provider；canonical model name 是 `deepseek-r1`，實際呼叫 id 仍會對應到 `deepseek-reasoner`
- `GITHUB_TOKEN`：GitHub Search API token
- `GH_SEARCH_MODEL`：提供需要 config 預設模型的命令使用；`gh-search query` 若沒帶 `--model`，固定使用 `gpt-4.1-mini`
- `GH_SEARCH_MAX_TURNS`：agent loop 最大輪數
- `GH_SEARCH_LOG_ROOT`：session logs 路徑

目前只 tune / support 這三個 model name：`gpt-4.1-mini`、`claude-sonnet-4`、`deepseek-r1`。請直接用這三個 canonical 名稱，不要用舊 alias。

## 使用方式

### 檢查設定

```bash
gh-search check
```

### 跑單次查詢

```bash
gh-search query "find the top 5 Python repositories about AI sorted by stars descending"
```

不帶 `--model` 時，`query` 會固定使用 `gpt-4.1-mini`。

也可指定模型：

```bash
gh-search query "..." --model gpt-4.1-mini
gh-search query "..." --model claude-sonnet-4
gh-search query "..." --model deepseek-r1
```

### 跑 smoke eval

```bash
gh-search smoke
```

不帶 `--eval-run-id` 時，`smoke` 會自動使用 `model_name + UTC timestamp`，例如 `gpt-4.1-mini_20260425T010203Z`。

也可以自己指定 run id：

```bash
gh-search smoke --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_local_demo
```

## 測試

完整測試：

```bash
pytest -q
```

## Logs 與 Artifacts

每次 `query` 執行後，session logs 寫到：

```text
artifacts/logs/sessions/{session_id}/
```

每次 `smoke` eval 會寫到：

```text
artifacts/eval/{eval_run_id}/
```

這些檔案可用來：

- 回放 tool-calling 過程
- 比對 `predicted_structured_query` 與 ground truth
- 檢查實際找回哪些 repo
- 追查錯誤是在哪一層發生

## 參考文件

- [specs/target/MVP_SPEC.md](specs/target/MVP_SPEC.md)
- [specs/main/README.md](specs/main/README.md)
- [specs/tunning/README.md](specs/tunning/README.md)
- [specs/datasets/HUMAN_REVIEW_SUMMARY.md](specs/datasets/HUMAN_REVIEW_SUMMARY.md)
