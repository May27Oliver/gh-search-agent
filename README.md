# GitHub Search CLI Agent

把自然語言查詢轉成 GitHub repository search，透過 bounded agent loop 完成：

`intention_judge -> parse_query -> validate_query -> compile_github_query -> execute_github_search`

這個專案目前已完成 Phase 1，可用來：
- 跑單次 CLI 查詢
- 寫出每輪 session logs
- 執行 smoke eval

## 環境需求

- Python 3.10+
- OpenAI API key
- GitHub personal access token

## 安裝

### 一鍵安裝（推薦）

專案內附 `install.sh`，會自動檢查 Python 版本、建立 `.venv`、安裝依賴，並在第一次執行時從 `.env.example` 建立 `.env`：

```bash
./install.sh
```

常用選項：

```bash
./install.sh --clean     # 先砍掉舊的 .venv 再重建（遇到 dependency conflict 時最穩）
./install.sh --no-dev    # 只裝 runtime 依賴，不裝 dev extras
./install.sh --help      # 看所有選項
```

安裝完成後啟用 venv：

```bash
source .venv/bin/activate
```

預設會用 `python3`；若想指定別的 Python，可帶環境變數：

```bash
PYTHON_BIN=/opt/homebrew/bin/python3.11 ./install.sh
```

### 手動安裝

如果偏好自己操作，步驟等同於 `install.sh` 裡做的事：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e '.[dev]'
```

如果 `pip` 顯示其他既有套件的 dependency conflict warning，通常代表你不是在乾淨環境裡安裝。最穩的做法是重建 `.venv` 後再裝一次（或直接跑 `./install.sh --clean`）。

## 設定

如果是用 `./install.sh` 安裝的，`.env` 已經自動從 `.env.example` 複製過來，直接編輯即可。若是手動安裝，先複製環境變數範本：

```bash
cp .env.example .env
```

然後在 `.env` 填入：

```env
OPENAI_API_KEY=...
GITHUB_TOKEN=...
GH_SEARCH_MODEL=gpt-4.1-mini
GH_SEARCH_MAX_TURNS=5
GH_SEARCH_LOG_ROOT=artifacts/logs
```

說明：
- `OPENAI_API_KEY`：Phase 1 預設 parser model 使用 `gpt-4.1-mini`
- `ANTHROPIC_API_KEY`：若要跑 `claude-sonnet-4`
- `DEEPSEEK_API_KEY`：若要跑 `DeepSeek-R1`
- `GITHUB_TOKEN`：GitHub Search API token
- `GH_SEARCH_MODEL`：可覆寫預設模型
- `GH_SEARCH_MAX_TURNS`：agent loop 最大輪數
- `GH_SEARCH_LOG_ROOT`：session logs 輸出路徑

## 使用方式

安裝後可直接用 `gh-search`：

```bash
gh-search --help
```

也可以用 module 方式執行：

```bash
python -m gh_search --help
```

### 1. 檢查設定

```bash
gh-search check
```

成功時會看到類似：

```text
config ok (model=gpt-4.1-mini, max_turns=5, log_root=artifacts/logs)
```

### 2. 跑單次查詢

建議先用目前 schema 較容易處理的 query，例如：

```bash
gh-search query "找出 Python AI 相關、依 stars 由高到低排序的前 5 個 repo"
```

或英文：

```bash
gh-search query "find the top 5 Python repositories about AI sorted by stars descending"
```

可選參數：

```bash
gh-search query "..." --model gpt-4.1-mini --max-turns 5
```

也可切到其他正式評測模型：

```bash
gh-search query "..." --model claude-sonnet-4
gh-search query "..." --model DeepSeek-R1
```

注意：
- 目前支援的是 GitHub repository search
- `stars` 指的是 repo 的總 stars，不是「今天新增 stars」
- 如果 query 太模糊、與 GitHub search 無關、或 5 輪內無法收斂，系統會誠實失敗並輸出原因

### 3. 跑 smoke eval

```bash
gh-search smoke
```

也可以指定 dataset 或 eval run id：

```bash
gh-search smoke --dataset datasets/smoke_eval_dataset.json --eval-run-id smoke_local_001
```

## 測試

跑完整測試：

```bash
pytest -q
```

如果你只想先驗證主要 Phase 1 路徑，也可以先跑：

```bash
pytest -q tests/test_cli_scaffold.py tests/test_scorer.py tests/test_agent_loop.py tests/test_cli_query.py tests/test_smoke_runner.py
```

`tests/test_github_client.py` 需要 `responses` 套件，因此請確認你是用 `.[dev]` 安裝。

## Logs 與 Artifacts

每次 `query` 執行後，session logs 會寫到：

```text
artifacts/logs/sessions/{session_id}/
```

至少包含：
- `run.json`
- `turns.jsonl`
- `final_state.json`
- `artifacts/`

每次 `smoke` eval 也會額外寫出 eval-level artifacts 到：

```text
artifacts/eval/{eval_run_id}/
```

這些檔案可用來回放每一輪 tool calling、追查 failure cases、以及做後續 error analysis。

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
  schemas/
  tools/

datasets/
specs/main/
tests/
artifacts/
```

## 規格文件

實作時主要參考：
- [specs/main/MAIN_SPEC.md](specs/main/MAIN_SPEC.md)
- [specs/main/SCHEMAS.md](specs/main/SCHEMAS.md)
- [specs/main/TOOLS.md](specs/main/TOOLS.md)
- [specs/main/LOGGING.md](specs/main/LOGGING.md)
- [specs/main/EVAL.md](specs/main/EVAL.md)
- [specs/main/EVAL_EXECUTION_SPEC.md](specs/main/EVAL_EXECUTION_SPEC.md)
- [specs/main/PHASE1_PLAN.md](specs/main/PHASE1_PLAN.md)

完整母規格在：
- [specs/target/MVP_SPEC.md](specs/target/MVP_SPEC.md)
