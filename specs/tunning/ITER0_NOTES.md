# Iteration 0 — Execution Notes

> Plan: [EVAL_GPT41MINI_20260424_PLAN.md §8, §10](EVAL_GPT41MINI_20260424_PLAN.md)
> Baseline run: `artifacts/eval/eval_gpt41mini_20260424/`
> Matrix artifact: `artifacts/eval/iterations/iter_0_baseline_20260424/`

## What shipped

| §8 checklist | status | artifact |
|---|---|---|
| pin decoding `temperature = 0` | ✅ already pinned | `src/gh_search/llm/openai_client.py:33` |
| scorer review | ✅ done | `specs/tunning/ITER0_SCORER_REVIEW.md` |
| golden tests `q012` / `q015` / `q025` | ✅ done | `tests/test_golden_iter0.py` + `tests/golden/iter0_cases.json` |
| `model_matrix.{json,md}` + `refs.json` canonical artifact | ✅ done | `artifacts/eval/iterations/iter_0_baseline_20260424/` |
| adopt `core-* / appendix-*` prompt_version naming | ✅ done (prospective) | `src/gh_search/cli.py:29`, `src/gh_search/eval/runner.py:48` |
| multi-model baseline (≥2 models, cross-provider) | ⚠ PARTIAL — 1 model only | see blocker below |
| cross-model failure-mode triage (task-level vs model-specific) | ⏸ blocked on cross-provider run | — |

## Matrix summary (single-provider)

From `artifacts/eval/iterations/iter_0_baseline_20260424/model_matrix.json`:

| model | provider | accuracy | correct | rejected | no_results | golden_passed |
|---|---|---|---|---|---|---|
| `gpt-4.1-mini` | openai | 10.00% | 3/30 | 7 | 4 | 3/3 |

Per-field recall (core 6 fields):

| field | recall | headline |
|---|---|---|
| `keywords` | **16.7%** | dominant drag on accuracy |
| `language` | 70.0% | decent; 2 cases over-inference |
| `created_after` | 70.0% | 3 date errors |
| `created_before` | 70.0% | 3 date errors |
| `min_stars` | 73.3% | mostly OK |
| `max_stars` | 76.7% | mostly OK |

Cross-provider flag: **no**. Plan §4.5 requires ≥2 providers before any
model-specific prompt change can be promoted into the `core` layer, so Iteration
0 is **not** considered "pass" until the second provider runs.

## Blocker: cross-provider runner

Current `src/gh_search/llm/openai_client.py` is the only provider adapter.
`claude-sonnet-4` falsification (§4.5 recommended pairing) needs either:

1. An Anthropic client adapter that returns the same `LLMJsonCall` contract,
   **or**
2. A one-shot aggregation script that ingests pre-computed Claude predictions
   in the existing `per_item_results.jsonl` format

Decision needed from owner before Iteration 0 can be declared done.

## Historical run relabeling

`artifacts/eval/eval_gpt41mini_20260424/run_config.json` still records
`prompt_version = "phase1-v1"` because the eval ran before the §4.3 rename. The
canonical matrix faithfully carries that value forward. New runs produced after
this commit will record `"core-v1 + appendix-gpt41mini-v1"`.

## What Iteration 1 should start from

Given the matrix (keywords recall 16.7%), the §5.3 scorer review, and the
§6 priorities, the concrete next-step shortlist — in the order §8 Iteration 1
implies — is:

1. **P0 gate relaxation** (`intention_judge`) — recoverable: q004, q009, q021,
   q022; intentionally leave q019, q020, q030 rejected (see §6 P0 notes).
2. **P1 parser output policy** — phrase preservation + no-plural-rewrite +
   no-language-over-inference. Affects 14 keyword-mismatch items, F1+F2 in
   scorer review.
3. **Scorer canonicalization (lemmatize + phrase-merge + language-redundancy)**
   — lands as model-agnostic hedge. ITER0_SCORER_REVIEW F1/F2 row-wise saves
   ≈11 items if parser still imperfect.

All three must be re-verified against **≥2 providers cross-matrix** before
promotion into `core-*`, per §4.5 pass gate.

## Reproducing the matrix

```bash
source .venv/bin/activate
python scripts/build_model_matrix.py \
  --iteration-id iter_0_baseline_20260424 \
  --dataset datasets/eval_dataset_reviewed.json \
  --runs eval_gpt41mini_20260424
```

Second model (once available):

```bash
python scripts/build_model_matrix.py \
  --iteration-id iter_0_baseline_20260424 \
  --dataset datasets/eval_dataset_reviewed.json \
  --runs eval_gpt41mini_20260424 eval_claude_sonnet4_20260424
```
