# eval — 導覽

這個資料夾負責「自動跑一批題目、幫 agent 打分數」。目前給 `gh-search smoke` 子命令用（跑 3 題左右的縮小版評測），之後要做 30 題完整評測也可以重用這裡的程式碼。

你可以把它想像成**一場有標準答案的考試**：runner 扮演「主持考試的人」，負責讓 agent 逐題作答；scorer 扮演「改考卷的老師」，拿到作答結果之後跟標準答案比對。兩件事刻意切開，因為主持考試需要真的去打 API、讀檔案，而改考卷最好是一個純粹的比對函數——這樣才好測、結果才穩定。

## 先看哪個

這個資料夾只有兩個檔案，職責分得很清楚：

### 1. [`runner.py`](./runner.py) — 主持考試

`run_smoke_eval(dataset_path, llm, github, ...)` 會做這些事：

1. 從datasets讀 dataset（JSON 檔）。
   如果 dataset 有 `metadata.reference_date`，runner 會把它當作 relative-date 題目的標註基準往下傳。
2. 逐題跑**一次完整的 agent loop**，每題都有獨立的 session 目錄。跑的過程中會實際呼叫 LLM（叫 parse、叫 repair…）、實際打 GitHub API、實際把 log / artifact 寫到磁碟。
3. 每題跑完後，從 agent 的 `final_state` 抽出「實際的 outcome、實際的 terminate_reason、實際產生的 `StructuredQuery`」，連同「這題的標準答案」一起交給 scorer 判分。
4. 把每題的判分結果寫進 `per_item_results.jsonl`，全部跑完再寫一份 `model_summary.json`，回傳 `SmokeSummary`（正確率、對幾題、每種 outcome 各出現幾次）。

所以「叫 LLM、打網路、讀寫檔案」這些事**都發生在 runner 這一層**。

如果你要真的打開 code 講給別人聽，建議閱讀順序是：

1. 先看 `run_smoke_eval()`，理解它怎麼把 dataset item 變成一次完整 session。
2. 再看 `_write_session_finalization()`，因為它最能說明「eval 跑完之後，會落哪些檔案」。
3. 最後看 `_per_item_entry()`，這會回答「外層 summary JSONL 到底收了哪些欄位」。

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

判分有兩種題型：

- **拒絕題**（dataset 標 `expect_rejection=True`）：agent 必須真的拒絕，**而且**拒絕的理由要跟標準答案一樣。例如標準答案說「不支援這類查詢（`unsupported_intent`）」，agent 卻回「太模糊（`ambiguous_query`）」，兩件事是不同判斷，不能混在一起算對。
- **正常題**：用 `normalized_exact_match` 一格一格欄位對。規則如下：

| 欄位                                | 怎麼比                                                                                                                |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `keywords`                          | 兩邊都先過一次 `normalize_keywords()`（這個 function 會幫忙統一大小寫、處理單複數、把同義詞收成同一個），再排序當清單比。順序、大小寫不影響結果。 |
| `language`                          | 轉小寫再比；兩邊都是 `None` 也算對。                                                                                  |
| `created_after` / `created_before`  | 日期字串完全一樣（格式 `YYYY-MM-DD`）才算對。                                                                         |
| `min_stars` / `max_stars` / `limit` | 數字完全一樣才算對。                                                                                                  |
| `sort` / `order`                    | enum 拿 `.value` 出來比（`SortField.STARS` 等於 `"stars"`）。                                                         |

**每一格欄位都要對**，這題才算 `is_correct = True`。沒有半對半錯，只有 1 分跟 0 分。最終分數就是「對的題數 ÷ 總題數」。

每題判分結果都會記到 `ScoreResult`，裡面有：
- `field_results`：每一格欄位過了沒
- `mismatch_reasons`：人類看得懂的「差在哪」描述

跑完評測後可以直接打開 `per_item_results.jsonl`，一眼看到每題是卡在哪個欄位上。

## 為什麼選這個評分方法

選評分方法之前有評估過幾個方案，都被刷掉了：

| 方案                                  | 為什麼**沒**選                                                                                                                                                                |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 字面對字面（raw exact match）         | 模型輸出的寫法很多（`React` 跟 `react`、`logistics library` 跟 `logistics-library`、`Python` 跟 `python`），字面比會把「只是寫法不一樣」當成答錯，分不出「真的錯」跟「只是表面不同」。 |
| 用 LLM 來當裁判（LLM-as-judge）       | 每次跑分數會飄；要花錢；放不進 CI；面試或交接的時候，需要的是穩定可比的數字，不是會跳的數字。                                                                                |
| 模糊比對（例如 keyword 重疊率 ≥ 0.8） | 那個 0.8 門檻是人挑的，調一次就讓歷次結果無法比較；而且 GitHub Search 是「欄位都對才會搜到對的 repo」，半對的查詢實際上沒意義。                                              |
| 給部分分數（每格 0~1 再加權平均）     | 加權沒有客觀根據——`min_stars` 錯一格跟 `language` 錯一格，對搜尋結果的影響完全不同；權重怎麼調都會改變結論，等於分數可以被人為挪動。                                          |

**選 normalized exact match 是因為它同時做到四件事：**

1. **每次跑結果都一樣。** scorer 是純函數，輸入相同就輸出相同，可以放進 CI，也可以拿來跨 iter 比較分數有沒有進步。
2. **判分用的規則跟 agent 實際用的規則同一套。** scorer 用的 `normalize_keywords()` **跟 parser、validator 是同一個 function**——這是 KEYWORD_TUNING_SPEC §8.3 規定的單一規則來源。如果 scorer 自己另外做一套 lowercase / sort，就會出現 agent 用一套規則、scorer 用另一套規則，分數會跟實際行為脫鉤。
3. **把「寫法不同」跟「意思真的不同」分開算。** `React` 跟 `react` 算同一題，但 `react` 跟 `react native` 不算；`logistics-library` 跟 `logistics library` 算同一題，但 `logistics` 跟 `delivery` 不算。這樣分數才反映語意差異，不是表面差異。
4. **對就 1 不對就 0，跟實際後果一致。** `min_stars=99` 跟 `min_stars=100` 在 GitHub Search 是不同的查詢，會搜到不同 repo——實務上半對等於沒對，給部分分數反而會把問題藏起來。

拒絕題之所以連拒絕理由（`terminate_reason`）都要對，是因為**不同的拒絕理由，後面的處理方式也不一樣**：`unsupported_intent` 應該回使用者「我們不支援這類查詢」；`ambiguous_query` 應該追問請使用者澄清。如果只看「有沒有拒絕」就算對，會把這兩種完全不同的判斷錯誤合併在一起，看不出 agent 真正搞錯的是什麼。

## 為什麼要這樣切（程式結構）

- **runner 跟 scorer 分開寫**，是因為這兩件事適合用完全不同的方式測。runner 要模擬整條 pipeline，會把 llm 跟 github 都 mock 掉再跑（看 `tests/test_smoke_runner.py`）；scorer 是純函數，只要餵幾組假資料就能狂測各種邊界（漏一個 keyword、日期差一天、sort 有填但 order 沒填⋯），毫秒級就跑完。混在一起寫會讓兩邊都難測。
- **scorer 必須維持純函數**。之後想加新規則（例如「`min_stars` 差 10 以內也算對」），請直接加在比對邏輯裡；想要「部分分數」請另外開一個新 function（例如 `score_item_partial`），**不要動現有的 scorer**——一動歷次評測結果就無法跨 iter 比較，這對 iter5–iter11 之間判斷有沒有進步特別重要。
- dataset 的格式規則寫在 [`datasets/AGENTS.md`](../../../datasets/AGENTS.md)。加新欄位時 scorer 要記得同步。

## 測試

- `tests/test_scorer.py` — 每種 outcome、每種拒絕類型都有一題。要新加判分規則時**先在這裡寫失敗測試（RED）**，再去改 scorer 讓它變綠。
- `tests/test_smoke_runner.py` — 把 llm 跟 github 都 mock 掉，跑一份超小 dataset，確認 runner 串得起來、能把結果正確地餵給 scorer。
