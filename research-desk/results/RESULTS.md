# Research Desk: measured development evaluation

**Baseline 34/50 (68%) -> reference-rule comparison 38/50 (76%). Change: +8 percentage points.**

This is a new run on the supplied current codebase. Earlier generated code and results were not imported. The comparison rule is newly constructed from this checkout's learning evidence; it is not an approved or learned-from-validation application procedure.

| Slice | Cases | Baseline correct | Reference-rule correct | Gains | Regressions |
|---|---:|---:|---:|---:|---:|
| Overall | 50 | 34 | 38 | 4 | 0 |
| Distinct calculations | 30 | 24 | 26 | 2 | 0 |
| Applicable | 8 | 4 | 8 | 4 | 0 |
| Out of scope | 42 | 30 | 30 | 0 | 0 |
| additional_calculation | 18 | 15 | 15 | 0 | 0 |
| opaque_ids | 10 | 3 | 4 | 1 | 0 |
| original | 12 | 9 | 11 | 2 | 0 |
| row_order | 10 | 7 | 8 | 1 | 0 |
| costco_2018 | 12 | 10 | 10 | 0 | 0 |
| document_95fd80bd6614164c19 | 19 | 7 | 11 | 4 | 0 |
| target_2018_2020 | 19 | 17 | 17 | 0 | 0 |

## Protocol and limits

- 50 authored development cases = 30 distinct calculations + 20 correlated row-order/opaque-ID variants, over only three source groups. This is not 50 independent documents or a held-out final benchmark.
- Original 12 cases and their references are unchanged. Learning and reserved-final sets remain unchanged; no final model inference is performed. Prepared source figures retain their original review status; no new human source review is claimed.
- Correctness requires exact ordered source operand IDs AND a numeric result within 0.01. Requested reviews and runtime failures count as incorrect. Fiscal-week qualification is scored separately using the existing evaluator's text heuristic.
- Eight scoped cases run both real inference conditions with alternating order. Outside-scope branches reuse the real baseline result because model inputs and execution are identical. Each shared row is labeled; zero boundary regressions are guaranteed by unchanged execution, not independent reruns.
- The intervention combines reference-procedure text with deterministic label binding and model auditing. It does not establish model-weight learning, a text-only memory benefit or a new human approval. The normal application's approval gate remains intact; this runner never stores its rule in the accepted-procedure ledger.
- Single fixed-seed run; correlated cases and only three source groups. No generalization, statistical significance, production-readiness or financial-advice reliability claim is supported.
- Model: `qwen3:8b`; digest `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.
- Model options: `{"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 1500}`.
- Fingerprint: `5691e1dabb4919978dd307b1d182e57b06598147a0278539df0758243ec915c8`.
- MLflow: `{"run_id": "3b78eabbc86544b194c5cbc1791d20d1", "enabled": true}`.
- Start/end UTC: 2026-10-28T21:54:17.213603+00:00 / 2026-10-28T22:21:04.076627+00:00.

## Resume wording supported by this run

> Expanded Research Desk's development evaluation to 50 cases; measured 68% baseline correctness versus 76% with a scoped source-binding reference rule, using MLflow traces and paired failure analysis.

Describe the application as approval-gated; do not describe this unapproved comparison rule as human-approved memory.

## Remaining failures

- `costco16_imported_sales_margin`: status `answer`; chosen `['document_95fd80bd6614164c19_cell_8', 'document_95fd80bd6614164c19_cell_0']`; expected `['document_95fd80bd6614164c19_cell_0', 'document_95fd80bd6614164c19_cell_8']`; runtime error `None`.
- `dev_4caaef22d81e`: status `answer`; chosen `['document_95fd80bd6614164c19_cell_9', 'document_95fd80bd6614164c19_cell_5']`; expected `['document_95fd80bd6614164c19_cell_4', 'document_95fd80bd6614164c19_cell_9']`; runtime error `None`.
- `dev_0f1a12849ee2`: status `answer`; chosen `['document_95fd80bd6614164c19_cell_6', 'document_95fd80bd6614164c19_cell_7']`; expected `['document_95fd80bd6614164c19_cell_6', 'document_95fd80bd6614164c19_cell_11']`; runtime error `None`.
- `dev_ef2f9200e05f`: status `answer`; chosen `['document_95fd80bd6614164c19_cell_10', 'document_95fd80bd6614164c19_cell_2']`; expected `['document_95fd80bd6614164c19_cell_2', 'document_95fd80bd6614164c19_cell_10']`; runtime error `None`.
- `costco18_growth__opaque_ids`: status `review`; chosen `['row_259b8989e56a', 'row_2281f5435162']`; expected `['row_2281f5435162', 'row_259b8989e56a']`; runtime error `None`.
- `target20_sales_margin__opaque_ids`: status `answer`; chosen `['row_f8997e12f531', 'row_790b04e65b60']`; expected `['row_790b04e65b60', 'row_f8997e12f531']`; runtime error `None`.
- `costco16_imported_growth__opaque_ids`: status `answer`; chosen `['row_939211db718f', 'row_fc01b8bbb281']`; expected `['row_4bab90aaafcd', 'row_fc01b8bbb281']`; runtime error `None`.
- `dev_edfdd2350a46__opaque_ids`: status `review`; chosen `['row_c51c461f711f', 'row_ae3b52d44830']`; expected `['row_ae3b52d44830', 'row_c51c461f711f']`; runtime error `None`.
- `costco16_imported_sales_margin__row_order`: status `answer`; chosen `['document_95fd80bd6614164c19_cell_8', 'document_95fd80bd6614164c19_cell_0']`; expected `['document_95fd80bd6614164c19_cell_0', 'document_95fd80bd6614164c19_cell_8']`; runtime error `None`.
- `target20_growth__opaque_ids`: status `review`; chosen `['row_f9b844a62d43', 'row_0fe6f0e9d736']`; expected `['row_0fe6f0e9d736', 'row_f9b844a62d43']`; runtime error `None`.
- `costco16_imported_quarter_margin__opaque_ids`: status `answer`; chosen `['row_ed64d35de30c', 'row_9221a70a16cb']`; expected `['row_9221a70a16cb', 'row_ed64d35de30c']`; runtime error `None`.
- `dev_4caaef22d81e__row_order`: status `answer`; chosen `['document_95fd80bd6614164c19_cell_11', 'document_95fd80bd6614164c19_cell_6']`; expected `['document_95fd80bd6614164c19_cell_4', 'document_95fd80bd6614164c19_cell_9']`; runtime error `None`.
