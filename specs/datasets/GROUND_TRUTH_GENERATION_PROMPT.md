# Ground Truth Generation Prompt

以下 prompt 用於為 **已人工挑選過的 queries** 生成 structured query 草稿。

重要原則：

- 這一步是產生 **ground truth draft**
- 不是最終標準答案
- 產出後必須人工審核與修正

本專案 schema：

```json
{
  "keywords": ["logistics", "optimization"],
  "language": "Python",
  "created_after": "2024-01-01",
  "created_before": null,
  "min_stars": 100,
  "max_stars": null,
  "sort": "stars",
  "order": "desc",
  "limit": 5
}
```

規則：

- 所有欄位都必須存在
- 未指定時明確填入 `null`
- 日期格式必須為 `YYYY-MM-DD`
- `sort` 只允許：`stars`、`forks`、`updated`
- `order` 只允許：`asc`、`desc`
- `limit` 預設 `10`
- 若輸入明顯模糊或衝突，也不要硬猜；應在 `notes` 中說明不確定處，並仍輸出最保守的結構

建議直接貼給 Claude / 其他模型：

```text
你是一位負責撰寫 LLM structured output evaluation ground truth 的資料標註工程師。

我會提供一批 GitHub repository search 的自然語言查詢。請你針對每一題，輸出對應的 structured query 草稿。

任務目標：
- 將自然語言查詢轉成 GitHub repository search 用的標準化 structured query
- 請嚴格遵守指定 schema
- 不要輸出 GitHub query string
- 不要輸出超出 schema 的欄位
- 若查詢存在模糊、衝突、或不完整條件，請採保守策略，不要自行腦補過多未明示條件

Schema：
{
  "keywords": ["string"],
  "language": "string or null",
  "created_after": "YYYY-MM-DD or null",
  "created_before": "YYYY-MM-DD or null",
  "min_stars": "number or null",
  "max_stars": "number or null",
  "sort": "stars | forks | updated | null",
  "order": "asc | desc | null",
  "limit": "number or null"
}

標註規則：
- 所有欄位都必須存在
- 未指定欄位填 `null`
- `keywords` 只保留有搜尋價值的詞
- 去除停用詞與無意義裝飾詞
- 如果 query 明確要求 top / popular，只有在語意足夠清楚時才推定 `sort` 與 `order`
- 如果 query 中沒有明確 limit，請填 `10`
- 如果 query 中出現相對時間（如 recent、last year），請盡量保守，不要任意硬轉；若無法安全確定，保留為 `null` 並在 notes 註明
- 如果 query 本身有衝突條件，保留衝突資訊並在 notes 註明，不要偷偷修掉

請輸出 JSON array，每筆包含：
- id
- input_query
- ground_truth_structured_query
- notes

ground_truth_structured_query 必須完全符合 schema。

只輸出合法 JSON，不要輸出 markdown，不要輸出解釋。
```

建議使用方式：

1. 把人工挑選過的 candidate queries 丟進這個 prompt
2. 取得 structured query 草稿
3. 逐題人工審核
4. 審核後再寫入正式 eval dataset

注意：

- 不能直接把模型輸出當作 final ground truth
- 每題都必須人工確認其 GitHub Search API 語意是否正確
