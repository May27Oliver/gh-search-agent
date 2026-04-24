# datasets — 導覽

這個資料夾放的是**評測用的題庫**。都是 JSON 檔，裡面是一題題的自然語言查詢，以及（如果有的話）對應的「標準答案」。沒有原始程式碼。

你可以把它想像成一份有解答的考卷：agent 要作答，`eval/` 底下的程式會拿這份解答幫它打分數。

## 裡面有哪幾份檔案

| 檔案 | 內容 | 用途 |
|---|---|---|
| `candidate_dataset.json` | 第一輪產生的 30 筆自然語言查詢，還沒附標準答案。 | 當作種子資料，之後才慢慢補上標註。 |
| `ground_truth_structured_query.json` | 針對 candidate 的結構化查詢草稿標註。 | 標註工程師的輸出，還沒完全審過。 |
| `eval_dataset_reviewed.json` | 人工審過、對齊 `StructuredQuery` schema 的完整 eval 題庫。 | Phase 2 完整 eval 會用這份。 |
| `smoke_eval_dataset.json` | 精簡過的 3 題（2 題正常 + 1 題拒絕）。 | `gh-search smoke` 子命令預設跑這份，快速驗證整條 pipeline 還活著。 |

## 每題的欄位長什麼樣

每一筆題目都大致長這樣（用註解標出哪些是必填、哪些情境才填）：

```jsonc
{
  "id": "smoke_001",
  "input_query": "使用者實際輸入的自然語言句子",
  "case_type": "normal | compound_constraints | rejection | ...",
  "language": "en | zh | ...",
  "expect_rejection": false,

  // 只有「拒絕題」才填，標出期待的終止原因
  "expected_terminate_reason": "unsupported_intent",

  // 只有「正常題」才填，是標準答案
  "ground_truth_structured_query": {
    "keywords": ["..."],
    "language": "Python",
    "created_after": "YYYY-MM-DD",
    "created_before": null,
    "min_stars": 100,
    "max_stars": null,
    "sort": "stars",
    "order": "desc",
    "limit": 10
  }
}
```

欄位結構跟 `src/gh_search/schemas/structured_query.py` 完全對齊。判分的細節在 [`src/gh_search/eval/AGENTS.md`](../src/gh_search/eval/AGENTS.md)。

## 踩過的坑（請避免再犯）

- **日期邊界**：我們的 prompt 規則是「使用者講 after YYYY → 轉成 `YYYY+1-01-01`」。所以 dataset 的 `created_after` 要直接填「實際應該產生的那個日期」（例如 `2024-01-01`），而 `input_query` 寫使用者會口語講的說法（「after 2023」）。smoke_002 一開始就搞反過、導致分數看起來很差，請不要再踩同一顆雷。
- **拒絕題一定要標 `expected_terminate_reason`**。`unsupported_intent`（問題根本不是在找 repo）跟 `ambiguous_query`（意圖是找 repo，但描述太模糊）是兩件事，scorer 會分開認。
- **keywords 大小寫**：scorer 比對前會把 keywords 轉小寫，所以不用刻意統一大小寫；但**不要**寫一串同義詞組合（例如 `["react", "reactjs", "React.js"]`）去想「多塞幾個增加命中率」，那會讓標準答案本身不乾淨。

## 加新題目的流程

1. 把新題目加到對應 dataset 檔。請保持按 `id` 字母序排列，方便 diff 閱讀。
2. 跑 `gh-search smoke --dataset datasets/smoke_eval_dataset.json`，確認 pipeline 還跑得起來。
3. 如果新題目跟現有 prompt 規則衝突（例如日期邊界、keyword 拆法），**優先修 prompt 或標準答案讓它們對齊**，**不要**偷偷放寬 scorer 去包庇新題目——那會讓後面所有題目的判分都失真。
