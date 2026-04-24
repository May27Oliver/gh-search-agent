# Human Review Checklist

這份 checklist 用於人工審核：

1. candidate eval queries
2. ground truth structured query 草稿
3. failure case / adversarial cases

## A. Query Review

審核每一筆 `input_query` 時，確認以下項目：

- 這題是否真的屬於 GitHub repository search domain
- 是否像真實使用者會說的話，而不是文件語句
- 是否與其他題目重複或高度相似
- 是否過度模板化
- 是否覆蓋 spec 要求的 case type
- 是否覆蓋必要欄位：
  - `keywords`
  - `language`
  - `created_after` / `created_before`
  - `min_stars` / `max_stars`
  - `sort` / `order`
  - `limit`

若不符合，標記原因：

- `off_domain`
- `duplicate`
- `too_synthetic`
- `missing_coverage`
- `unclear_wording`

## B. Ground Truth Review

審核每一筆 `ground_truth_structured_query` 時，確認以下項目：

- 所有 schema 欄位都存在
- 未指定欄位已填 `null`
- 欄位型別正確
- 日期格式正確，為 `YYYY-MM-DD`
- `sort` / `order` 值合法
- `limit` 合理
- `keywords` 只保留有搜尋價值的詞
- 是否有偷偷腦補使用者沒講的條件
- 是否有把模糊需求過度具體化
- 是否有忽略衝突條件

若不符合，標記原因：

- `missing_field`
- `invalid_type`
- `invalid_date`
- `over_inference`
- `under_specified`
- `conflict_ignored`
- `wrong_keyword_extraction`

## C. GitHub Search Semantics Review

除了 schema 正確，還要確認語意是否真的對應 GitHub repository search。

請人工檢查：

- 這個 structured query 編譯後能否形成合理的 GitHub search
- `keywords` 是否真的適合進 GitHub search query
- `language` 是否是合理的 GitHub language filter
- stars / date 範圍是否與原句一致
- sort 與 order 是否與原句一致
- limit 是否符合原意

必要時可手動 compile 成 GitHub query string 進行 sanity check。

若不符合，標記原因：

- `github_semantics_mismatch`
- `wrong_filter_mapping`
- `wrong_sorting_logic`
- `wrong_range_mapping`

## D. Ambiguous / Adversarial Review

對模糊題、衝突題、對抗題，額外確認：

- 這題是否真的能測出模型弱點
- 是否太模糊到連人工都無法定義答案
- 若人工也無法穩定定義 ground truth，是否應改為 failure case dataset，而不是正式 eval dataset

如果有以下情況，建議不要放進正式 eval dataset：

- 人工標註者無法穩定達成一致答案
- 題目本身不屬於 repository search domain
- 題目只是在測閱讀理解，沒有查詢結構價值

## E. Final Acceptance Checklist

正式納入 eval dataset 前，每題至少要滿足：

- `input_query` 合理且不重複
- `case_type` 標記正確
- `language` 標記正確
- `difficulty` 標記合理
- `ground_truth_structured_query` 完整且合法
- GitHub search 語意正確
- 至少一位人工 reviewer 已確認

## F. Reviewer Metadata

建議每筆資料額外保留以下欄位，方便之後追溯：

- `review_status`
  - `pending`
  - `approved`
  - `needs_revision`
- `reviewer`
- `reviewed_at`
- `review_notes`

## G. Practical Workflow

建議實際流程如下：

1. 用 `DATASET_GENERATION_PROMPT.md` 生成 candidate queries
2. 人工篩掉 off-domain / 重複 / 不自然的題目
3. 用 `GROUND_TRUTH_GENERATION_PROMPT.md` 生成 structured query 草稿
4. 依本 checklist 人工審核與修正
5. 寫入正式 eval dataset
6. 跑 baseline models
7. 根據錯誤模式擴充 failure case dataset
