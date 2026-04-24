# Main Specs Index

本目錄是從 [MVP_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/target/MVP_SPEC.md:1) 拆出的 implementation-facing 規格，目的在於降低單一文件過大造成的閱讀與開發負擔。

建議使用方式如下：

- 開始實作前先讀 [MAIN_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/MAIN_SPEC.md:1)
- 寫資料 model / validation 時讀 [SCHEMAS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/SCHEMAS.md:1)
- 寫 agent loop / tools 時讀 [TOOLS.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/TOOLS.md:1)
- 寫 logging / artifact output 時讀 [LOGGING.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/LOGGING.md:1)
- 寫 dataset / runner / scoring / model eval 時讀 [EVAL.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL.md:1)
- 寫正式測分流程、runner、scorer、model adapters 時讀 [EVAL_EXECUTION_SPEC.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/EVAL_EXECUTION_SPEC.md:1)
- 開始實作第一階段時讀 [PHASE1_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/PHASE1_PLAN.md:1)
- 開始進行第二階段 hardening / tuning / cross-model eval 時讀 [PHASE2_PLAN.md](/Users/chenweiqi/Documents/interview/gofreight/specs/main/PHASE2_PLAN.md:1)

文件分工如下：

- `MAIN_SPEC.md`
  產品目標、範圍、agent flow、成功標準、交付物
- `SCHEMAS.md`
  `structured_query`、shared state、log/eval/failure dataset contracts
- `TOOLS.md`
  tool responsibilities、I/O contracts、state transition、termination
- `LOGGING.md`
  canonical file structure、session logs、traceability
- `EVAL.md`
  datasets、failure cases、scoring、runner、model plan、iteration
- `EVAL_EXECUTION_SPEC.md`
  eval execution plan、runner modes、scorer contract、model adapters、gates、artifacts
- `PHASE1_PLAN.md`
  Phase 1 任務拆解、每步驗證方式、失敗時調整策略、應參考文件
- `PHASE2_PLAN.md`
  Phase 2 infra 任務拆解、provider adapters、cross-model baseline、已完成工項的維護責任、每步驗證方式與調整策略

規則：

- `specs/target/MVP_SPEC.md` 仍是完整母本
- `specs/main/` 是給開發與 LLM implementation 的工作規格
- 若兩者有不一致，應先修正 `MVP_SPEC.md`，再同步更新本目錄
