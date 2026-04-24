# Dataset Generation Prompt

以下 prompt 用於產生 **candidate eval queries**，不是最終 ground truth。

目標：

- 產生 30 筆 GitHub repository search 相關的自然語言查詢
- 查詢必須口語化、像真實使用者會說的話
- 只生成 repository search 類需求，不要生成 GitHub API 教學、token、webhook、rate limit、issues、pull requests、actions 等非本專案範圍內容

建議直接貼給 Claude / 其他模型：

```text
你是一位專精於 LLM evaluation dataset 設計的工程師。

請為一個「自然語言轉 GitHub repository search structured query」系統產生 30 筆候選 dataset。

任務背景：
- 這個系統的目標是把使用者的自然語言查詢，轉成 GitHub repository search 的結構化查詢
- 請只生成與 GitHub repository search 相關的使用者查詢
- 不要生成 authentication、token、rate limit、webhook、GitHub Actions、issue API、pull request API、repository creation、user profile 查詢等非 repository search 類問題

輸出內容要求：
- 請生成像真實使用者會輸入的自然語言查詢
- 查詢可以是英文、中文、或少量其他語言
- 查詢不要過度工整，要保留部分真實世界的口語感
- 不要產生 ground truth
- 不要附帶任何額外說明

資料集要求：
- 共 30 筆
- 必須涵蓋以下類型：
  - 10 筆一般查詢
  - 8 筆複合限制查詢
  - 4 筆模糊或容易誤解的查詢
  - 4 筆 typo / noisy 查詢
  - 4 筆非英文查詢
- 必須涵蓋以下搜尋條件：
  - keywords
  - language
  - created_after / created_before
  - min_stars / max_stars
  - sort / order
  - limit
- 可以包含少量 adversarial cases，例如衝突條件或模糊條件，但必須明確標記在 case_type 或 notes

輸出格式：
請只輸出合法 JSON array，每筆物件必須包含以下欄位：
- id
- input_query
- case_type
- language
- difficulty
- why_this_case_is_useful

欄位限制：
- case_type 只能是：
  - normal
  - compound_constraints
  - ambiguous
  - typo_or_noisy
  - multilingual
  - adversarial
- difficulty 只能是：
  - easy
  - medium
  - hard

請避免：
- 題意重複
- 明顯脫離 GitHub repository search domain
- 過度模板化到不像真人會說的話

只輸出 JSON，不要輸出 markdown，不要輸出解釋。
```

建議使用方式：

1. 先生成 30 到 50 筆候選題
2. 人工刪除重複、過於生硬、或不屬於 repository search 的題目
3. 挑出最終 30 筆正式 eval dataset

注意：

- 這份 prompt 的產出不能直接當 final dataset
- 產出結果必須經過人工 review
- ground truth 必須在下一步另外生成並人工校正
