# eval — 導覽

這個資料夾負責「自動跑一批題目、幫 agent 打分數」。目前給 `gh-search smoke` 子命令用（跑 3 題左右的縮小版評測），之後要做 30 題完整評測也可以重用這裡的程式碼。

你可以把它想像成**一場有標準答案的考試**：runner 扮演「主持考試的人」，負責讓 agent 逐題作答；scorer 扮演「改考卷的老師」，拿到作答結果之後跟標準答案比對。兩件事刻意切開，因為主持考試需要真的去打 API、讀檔案，而改考卷最好是一個純粹的比對函數——這樣才好測、結果才穩定。

## 先看哪個

這個資料夾只有兩個檔案，職責分得很清楚：

### 1. [`runner.py`](./runner.py) — 主持考試

`run_smoke_eval(dataset_path, llm, github, ...)` 會做這些事：

1. 從datasets讀 dataset（JSON 檔）。
2. 逐題跑**一次完整的 agent loop**，每題都有獨立的 session 目錄。跑的過程中會實際呼叫 LLM（叫 parse、叫 repair…）、實際打 GitHub API、實際把 log / artifact 寫到磁碟。
3. 每題跑完後，從 agent 的 `final_state` 抽出「實際的 outcome、實際的 terminate_reason、實際產生的 `StructuredQuery`」，連同「這題的標準答案」一起交給 scorer 判分。
4. 把每題的判分結果寫進 `per_item_results.jsonl`，全部跑完再寫一份 `model_summary.json`，回傳 `SmokeSummary`（正確率、對幾題、每種 outcome 各出現幾次）。

所以「叫 LLM、打網路、讀寫檔案」這些事**都發生在 runner 這一層**。

### 2. [`scorer.py`](./scorer.py) — 改考卷

核心函數是：

```python
score_item(
    eval_item,                  # 這題的題目 + 標準答案（runner 從 dataset 讀好傳進來）
    predicted_query,            # agent 實際產出的 StructuredQuery（runner 從 final_state 拿）
    actual_outcome,             # 這題最後的 outcome（success / rejected / ...）
    actual_terminate_reason,    # 這題最後的 terminate reason（若有）
)
```

它被呼叫到時，所有需要的資料 runner 都已經準備好當參數傳進來了。**scorer 自己完全不碰網路、不讀檔案、不叫 LLM**，只做純粹的欄位比對。

判分規則有兩類：

- **拒絕題**（dataset 裡 `expect_rejection=True`）：agent 的 outcome 必須落在「拒絕類」集合裡，**而且** `terminate_reason` 也要跟 dataset 標註的一致。例如標註是 `unsupported_intent` 就不能算 `ambiguous_query` 為正確，兩件事不能混。
- **正常題**：用 `normalized_exact_match` 逐欄位比對，規則如下表。

| 欄位                                | 怎麼比                                                 |
| ----------------------------------- | ------------------------------------------------------ |
| `keywords`                          | 轉小寫、排序後比（視為多重集合，順序無關、大小寫無關） |
| `language`                          | 轉小寫再比，null-safe                                  |
| `created_after` / `created_before`  | 字串相等（`YYYY-MM-DD`）                               |
| `min_stars` / `max_stars` / `limit` | 整數嚴格相等                                           |
| `sort` / `order`                    | enum 的 `.value` 相等                                  |

**所有欄位都對**才算這題 `is_correct = True`。目前沒有部分分數，只有 1 或 0。

## 為什麼要這樣切

- **runner 跟 scorer 分開**，是因為兩者的測試策略完全不同。runner 需要模擬整條 pipeline（`tests/test_smoke_runner.py` 會把 llm 跟 github 都 mock 掉跑跑看），而 scorer 只要給它幾組純資料就能狂測邊界（漏一個 keyword、日期差一天、sort 有填 order 沒填…），跑起來是毫秒級的。
- **scorer 必須保持純函數**。之後想加新判分規則（例如容許 `min_stars` 差 10 以內算對），請直接加在比對邏輯裡；想加「部分分數」請另外寫一個新函數（例如 `score_item_partial`），**不要改現有的 scorer**，以免讓歷次 eval 結果變得不可比較。
- dataset 的格式規則寫在 [`datasets/AGENTS.md`](../../../datasets/AGENTS.md)。加新欄位時 scorer 要同步更新。

## 測試

- `tests/test_scorer.py` — 每種 outcome、每種拒絕類型都有一題。要新加判分規則時**先在這裡寫失敗測試（RED）**，再去改 scorer 讓它變綠。
- `tests/test_smoke_runner.py` — 把 llm 跟 github 都 mock 掉，跑一份超小 dataset，確認 runner 串得起來、能把結果正確地餵給 scorer。
