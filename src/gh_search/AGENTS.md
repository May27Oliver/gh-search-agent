# src/gh_search — 導覽

這是整個 `gh-search` 套件的根目錄。它做的事情一句話講完：**把使用者用自然語言寫的需求，轉成 GitHub 搜尋 repository 的查詢，然後把結果拿回來**。

你可以把它想成一個小型的 AI agent：使用者丟一句「我想找 Python 物流相關、星星超過一百的專案」，它會判斷這句話是不是合理的搜尋需求，解析成結構化資料，組成 GitHub 真的看得懂的查詢字串，再實際去呼叫 GitHub API。過程中每一步都會寫 log，方便之後回頭除錯。

## 先看哪個

第一次進 repo 建議的閱讀順序：

1. [`cli.py`](./cli.py) — 使用者實際敲指令時的入口。從 `main()` 一路往下看到 `_cmd_query()`，大致就知道這個程式怎麼跑起來。
2. [`agent/`](./agent/AGENTS.md) — agent 的主迴圈。當你想知道「它到底怎麼一步一步決定下一步做什麼」的時候，答案都在這裡。
3. [`schemas/`](./schemas/AGENTS.md) — 所有的資料模型與 enum。想知道 state 裡到底有哪些欄位、每個欄位會是什麼值，先看這個。
4. 其他資料夾先跳過沒關係，實際需要改到那個功能再進去看就好。

## 層次地圖

這個專案把程式碼切成四層，**import 方向永遠從上往下**，下層不可以反過來依賴上層。這是為了讓 domain（核心領域邏輯）保持乾淨，換 HTTP client 或換 LLM 都不會動到核心。

```text
presentation   : cli.py                # 使用者介面
application    : agent/                # 主迴圈，決定下一步做什麼
                 tools/                # 把 state 餵給 domain 或 infra，再把結果寫回 state
                 eval/                 # 計分與 smoke 評測
domain         : schemas/              # 不可變的資料結構 + enum（單一來源）
                 compiler.py           # 把結構化查詢轉成 GitHub 查詢字串
                 validator.py          # 檢查結構化查詢的語意有沒有矛盾
infrastructure : github/               # GitHub HTTP client
                 llm/                  # OpenAI 等 LLM adapter
                 logger/               # 把每次執行寫成檔案的 session logger
                 config.py             # 從環境變數讀設定
```

更詳細的分層規則寫在根目錄 [`AGENTS.md`](../../AGENTS.md) 的「DDD 分層」那一節。

## 檔案一覽

| 檔案 | 做什麼 |
|---|---|
| `__init__.py` | 對外只 export `__version__`，其他不動。 |
| `__main__.py` | 讓 `python -m gh_search` 可以跑起來。 |
| `cli.py` | argparse 建的 CLI，有三個子命令：`query`（跑一次查詢）、`check`（檢查環境變數）、`smoke`（跑 smoke eval）。 |
| `config.py` | 從 `.env` 或環境變數讀設定。**不會往上層目錄尋找 `.env`**（以前這樣做過，結果測試互相污染，現在改成只讀明確路徑）。 |
| `compiler.py` | 純函數：`StructuredQuery -> str`，輸出是 GitHub 真的認得的 q 參數字串。 |
| `validator.py` | 純函數：檢查「min 不能大於 max」「after 不能晚於 before」「至少要有一個條件」這類語意規則。 |

## 幾個共通的約定

- 所有 domain 物件（`schemas/` 裡的東西、`Repository`）都是 immutable（pydantic `frozen=True` 或 frozen dataclass）。**不能改欄位值**，只能用 `model_copy(update=...)` 或直接建新的實例。這樣做是因為 agent loop 在多輪之間會比較前後 state 的差異，如果中途被改壞，debug 起來會非常痛苦。
- 規格的權威順序是：`specs/main/*` > 資料夾 `AGENTS.md` > 程式碼註解 > 測試。遇到三者講得不一樣，**以 specs 為準**，並回報不一致的地方。
