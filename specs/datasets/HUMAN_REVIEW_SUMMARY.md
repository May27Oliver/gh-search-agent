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

## 2026-05-10 更新：分桶治理（PR1）

對應 spec：[SEMANTIC_PARSING_HARNESS_REFACTOR_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/deep_review/SEMANTIC_PARSING_HARNESS_REFACTOR_SPEC.md)、[SEMANTIC_PARSING_HARNESS_PR_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/deep_review/SEMANTIC_PARSING_HARNESS_PR_PLAN.md)。

### 狀態變更（intent，尚未生效）

PR1 只把 governance scaffold 建起來：3 份 qid manifest 檔，加上 source-driven 的一致性測試。

**runner / scorer / [EVAL_EXECUTION_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL_EXECUTION_SPEC.md) 還沒改 — 目前實際執行的 headline accuracy 仍以 30 題 `eval_dataset_reviewed.json` 計算，包含 4 題 `needs_revision`。** Cutover 點是 PR2 (Eval Bucket Plumbing)，那隻 PR 接通 runner 後，formal manifest 才正式生效。

在 PR2 落地前，[README.md §最終結果](/Users/chenweiqi/Documents/interview/gofreight/README.md) 報的成績屬於「過渡期口徑」，不能直接當 26 題的 stable headline accuracy 拿去比較。

新增 3 份 manifest（intent，待 PR2 接通才生效）：

- [datasets/formal_eval_qids.json](/Users/chenweiqi/Documents/interview/gofreight/datasets/formal_eval_qids.json)：26 題 approved，PR2 後計入 headline accuracy
- [datasets/failure_eval_qids.json](/Users/chenweiqi/Documents/interview/gofreight/datasets/failure_eval_qids.json)：`q010` / `q020` / `q021` / `q029`，PR2 後移出 formal eval
- [datasets/ambiguous_eval_qids.json](/Users/chenweiqi/Documents/interview/gofreight/datasets/ambiguous_eval_qids.json)：保留空集合，留給後續 PR 重分

`q010` / `q020` / `q021` / `q029` 在原始 reviewed dataset 內仍保留 `review_status=needs_revision` 與 `recommended_dataset=failure_case` 的標註，PR1 不重寫題本身，只把它們從未來正式分數中拆出。

### Replacement candidate slots（待後續 PR 補題）

依 spec §5.2，formal eval 仍以 30 題為目標，因此移出 4 題後需補回 4 題。下列為候選方向，**尚未挑題、尚未標註**，PR1 不做完整 re-annotation pipeline：

| Slot | 補題方向 | 對應原題 |
| --- | --- | --- |
| `slot_A` | 一題乾淨的 ranking intent | replaces `q020`（原題模糊到無 topic） |
| `slot_B` | 一題乾淨的 stars boundary | replaces `q010`（原題 `newest` 無法穩定表達） |
| `slot_C` | 一題乾淨的 date constraint | replaces `q021`（原題 `not too old but not too new` 無法映射） |
| `slot_D` | 一題乾淨的 multilingual but expressible keyword | replaces `q029`（原題自然語言 ≠ programming language） |

每個 slot 仍待後續 PR 完成 candidate query → ground truth → human review 的完整流程。

### 驗證方式

[tests/test_eval_dataset_governance.py](/Users/chenweiqi/Documents/interview/gofreight/tests/test_eval_dataset_governance.py) 用 source-driven equality 釘住四件事，測試裡完全不出現 qid 字串：

1. `formal manifest == 所有 review_status=approved 的 qid`（雙向相等，少放或多放都會紅）
2. `failure manifest == 所有 review_status=needs_revision 且 recommended_dataset=failure_case 的 qid`
3. `ambiguous manifest == 所有 review_status=needs_revision 且 recommended_dataset=ambiguous_or_unexpressible 的 qid`
4. 每一題 `needs_revision` 都必須宣告合法的 `recommended_dataset`（防漏網：避免之後加題時忘填、繞過上述 equality）

加上三桶互不重疊、每個 qid 都能在 reviewed dataset 中找到的結構性測試。
