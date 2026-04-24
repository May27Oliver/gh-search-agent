# Tuning Specs

這個目錄存放評測後的調參、hardening、error analysis 與回歸驗證規格。

目前文件：

- [EVAL_GPT41MINI_20260424_PLAN.md](EVAL_GPT41MINI_20260424_PLAN.md)
  - 針對 `eval_gpt41mini_20260424` 的結果分析
  - 錯誤分類
  - 修正優先級
  - 驗證方式與通過標準
- [ITER0_SCORER_REVIEW.md](ITER0_SCORER_REVIEW.md)
  - 針對 14 題 keyword mismatch 的人工標註（§5.3）
  - 區分 scorer brittleness vs parser error vs multilingual/translation miss
- [ITER0_NOTES.md](ITER0_NOTES.md)
  - Iteration 0 執行 log、完成項目、blockers、下一步建議
- [KEYWORD_TUNING_SPEC.md](KEYWORD_TUNING_SPEC.md)
  - `keywords` 欄位的 tuning policy
  - technical phrase dictionary
  - singular/plural 容錯
  - modifier stopwords
  - multilingual / typo canonicalization
- [ITER3_INTENTION_JUDGE_TUNING_SPEC.md](ITER3_INTENTION_JUDGE_TUNING_SPEC.md)
  - Iteration 3 的 `intention_judge` 調整規格
  - dataset-aligned permissive gate
  - recoverable reject 題目與測試策略
  - cross-model 驗證與通過標準

使用方式：

1. 先讀 `artifacts/eval/{eval_run_id}/per_item_results.jsonl`
2. 對照本目錄內的 tuning plan 找出本輪主要失分來源
3. 依照優先級執行 prompt / parser / judge / normalization 調整
4. 重跑 eval，產生新一輪 artifacts
5. 把新結果追加成下一份 tuning plan 或 iteration record
