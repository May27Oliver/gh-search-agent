# github — 導覽

這個資料夾只做一件事：**呼叫 GitHub 的 Search Repositories API，把結果拿回來，順便把各種錯誤分類清楚**。它只負責網路溝通，不負責組查詢字串（那是 `compiler.py` 的工作）。

換句話說，這裡你看不到任何「怎麼把語言過濾器接到查詢裡」這類邏輯，只會看到「我拿到一個字串 `q`、一組 sort/order，就呼叫 GitHub、然後回傳結果或丟例外」。

## 先看哪個

全部東西都在 [`client.py`](./client.py) 裡，而且只有三樣：

1. **`Repository`** — 一個 frozen dataclass，代表一筆搜尋結果。只有四個欄位：`name`、`url`、`stars`、`language`。
2. **`GitHubClient.search_repositories(q, sort, order, per_page)`** — 同步 HTTP 呼叫，成功時回傳 `list[Repository]`。
3. **一組自定義例外** — `GitHubError` 是 base，底下有四種具體例外，分別對應到 GitHub 四種典型的失敗狀況（見下一節）。

## 錯誤分類

上層的 `execute_github_search` tool 會根據丟出來的例外是哪一種，決定 `ExecutionStatus` 要設成什麼。所以**這邊的例外分類必須穩定**，不要亂動。

| HTTP 狀況 | 丟什麼例外 | 代表什麼 |
|---|---|---|
| 401 Unauthorized | `GitHubAuthError` | token 沒帶或是錯的，檢查 `GITHUB_TOKEN`。 |
| 422 Unprocessable | `GitHubInvalidQueryError` | 查詢字串 GitHub 不接受，通常是 compiler 組錯了。 |
| 403 且 `X-RateLimit-Remaining: 0` | `GitHubRateLimitError` | 被 GitHub 限流，要等一下再試。 |
| 連線錯誤 / timeout / 其他非 2xx | `GitHubTransportError` | 網路層問題，不屬於上面那三種。 |

## 測試

`tests/test_github_client.py` 用 `responses` 這個套件把 HTTP 假掉，每一種錯誤狀況都有對應的測試。**改 client 行為之前請先改測試**（TDD 的習慣），不然很容易動到一種錯誤卻忘了另一種。

## 這裡刻意**不做**的事

- 不 import 任何 domain 型別（例如 `StructuredQuery`）。這個資料夾只認原始字串跟 primitive。這樣 domain 層才不會因為 GitHub API 改了就跟著動。
- **不加 retry、不加 backoff、不加 cache**。目前沒有這些需求，加了就是過度設計。真的遇到問題再加，不要先預設。
