# Human Review Summary

審核日期：`2026-04-23`

審核人：`Oliver Chen`

審核依據：

- [HUMAN_REVIEW_CHECKLIST.md](/Users/chenweiqi/Documents/interview/gofreight/datasets/HUMAN_REVIEW_CHECKLIST.md:1)

## 結果摘要

- candidate queries：30 題
- ground truth drafts：30 題
- reviewed dataset：30 題
- `approved`：26 題
- `needs_revision`：4 題

正式 review 後的合併資料檔：

- [eval_dataset_reviewed.json](/Users/chenweiqi/Documents/interview/gofreight/datasets/eval_dataset_reviewed.json:1)

## 已修正項目

以下題目已在 reviewed dataset 中直接修正：

- `q003`：移除不必要的 `sort=stars`
- `q004`：移除由 `good` 推定出的排序
- `q011`：修正 `after 2023` 的日期邊界為 `2024-01-01`
- `q012`：修正 `before 2020` 的日期邊界
- `q013`：修正 `over/under` 的嚴格數值邊界
- `q015`：修正 `more than 2k` 的嚴格數值邊界
- `q017`：修正 `under 100` 的嚴格數值邊界
- `q025`：修正 `after 2022` 的日期邊界為 `2023-01-01`
- `q027`：修正 `超過 1000` 的嚴格數值邊界
- `q030`：保留衝突條件，但修正為嚴格數值邊界

## 需要再修的題目

以下 4 題目前不建議直接納入正式 eval dataset，較適合改寫或移入 failure case dataset：

1. `q010`
   問題：`newest` 無法被目前 schema 精確表示，`sort=updated` 只是近似代理
   建議：改寫成 `most recently updated` 或加入明確日期條件

2. `q020`
   問題：查詢過度模糊，沒有穩定可標註的搜尋主題
   建議：移至 failure case dataset，或改寫成有明確 topic 的 query

3. `q021`
   問題：`not too old but not too new` 無法穩定映射到具體日期範圍
   建議：改寫成可標註的日期區間

4. `q029`
   問題：`日本語で書かれた` 指的是自然語言內容，不是 GitHub repository programming language
   建議：移至 failure case dataset，或改寫成語意可由現有 schema 表達的查詢

## 結論

目前這批資料已經足夠作為第一輪 eval 的基礎，但若要形成最終正式版 dataset，還需要再補至少 4 題可穩定標註的新題目，或將上述 4 題改寫後重新標註。
