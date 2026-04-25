# Tuning Specs

這個目錄存放評測後的調參、hardening、error analysis 與回歸驗證規格。

目前文件：

- [ITER1_EVAL_GPT41MINI_20260424_PLAN.md](ITER1_EVAL_GPT41MINI_20260424_PLAN.md)
  - 早期 baseline / iteration 1 規劃
- [ITER0_SCORER_REVIEW.md](ITER0_SCORER_REVIEW.md)
  - 針對 14 題 keyword mismatch 的人工標註（§5.3）
  - 區分 scorer brittleness vs parser error vs multilingual/translation miss
- [ITER0_NOTES.md](ITER0_NOTES.md)
  - Iteration 0 執行 log、完成項目、blockers、下一步建議
- [ITER2_KEYWORD_TUNING_SPEC.md](ITER2_KEYWORD_TUNING_SPEC.md)
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
- [ITER4_PHRASE_POLICY_SPEC.md](ITER4_PHRASE_POLICY_SPEC.md)
  - phrase merge policy
  - plural drift / sub-token canonicalization
  - Iter4 實際 rerun 結果與 handoff
- [ITER5_DATE_TUNING_SPEC.md](ITER5_DATE_TUNING_SPEC.md)
  - date parsing / relative year handling / dataset-anchored today
  - Iter5 acceptance criteria 與 shipped constraints
- [ITER5_NOTES.md](ITER5_NOTES.md)
  - Iter5 shipped 結論
  - follow-up revert 記錄
  - DeepSeek stochasticity / prompt-complexity risk
- [ITER6_LANGUAGE_OVERINFERENCE_SPEC.md](ITER6_LANGUAGE_OVERINFERENCE_SPEC.md)
  - language over-inference 下放 downstream 的規格
  - explicit language evidence policy
  - DeepSeek prompt budget guardrail
- [ITER6_NOTES.md](ITER6_NOTES.md)
  - Iter6 shipped 結論
  - 第一輪 evidence dict 漏 javascript / c++ / javscript 的 fix 記錄
  - DeepSeek noise pattern 與 §9.3 escape 適用判讀

使用方式：

1. 先讀 `artifacts/eval/{eval_run_id}/per_item_results.json`
2. 對照本目錄內的 tuning plan 找出本輪主要失分來源
3. 依照優先級執行 prompt / parser / judge / normalization 調整
4. 重跑 eval，產生新一輪 artifacts
5. 把新結果追加成下一份 tuning plan 或 iteration record
