# Phase 5 Failure-Class Distribution

## Scope

This document records the failure classes observed during the Phase 5
evaluation runs.

The automated BIRD distribution below is based on the 50-question
controlled BIRD subset used for the Phase 5 guardrail/repaired ablation.
It is not a full 200-question BIRD distribution.

The Olist distribution below is based on the latest full 150-question
`baseline_repaired` evaluation. The failure distribution is computed from
the first-attempt failure class recorded for each question.

## BIRD `bird_dev_200`

### Automated controlled subset

Result file:

`bird_dev_200_baseline_repaired_20260823T104237Z.json`

The automated repaired evaluation contained 50 questions.

- Correct: 19/50
- Accuracy: 38.0%
- Records with a failure class: 1/50
- Records with repair attempts: 1/50
- Maximum repair attempts observed: 2
- Degraded records: 0

The single recorded failure class was:

| Failure class | Count |
|---|---:|
| `MODE_MISMATCH` | 1 |

### Guarded baseline

The controlled guarded BIRD result used for the Phase 5 ablation was:

`bird_dev_200_baseline_guarded_20260823T110325Z.json`

- Correct: 17/50
- Accuracy: 34.0%
- Repair attempts: 0
- Degraded records: 0

The guarded result contains detailed identifier-level failure labels.
These are preserved at their recorded granularity and are not treated as
the final unified `FailureClass` distribution.

## Olist `olist_gold_150`

### Repaired evaluation

Latest result file:

`olist_gold_150_baseline_repaired_20260823T143416Z.json`

The evaluation contained 150 questions.

- Correct: 60/150
- Accuracy: 40.0%
- Records with a first-attempt failure class: 45/150
- Records with repair attempts: 28/150
- Maximum repair attempts observed: 2
- Degraded records: 7/150

### First-attempt failure distribution

| Failure class | Count | Share of first-attempt failures |
|---|---:|---:|
| `UNKNOWN_COLUMN` | 24 | 53.3% |
| `OTHER` | 16 | 35.6% |
| `AMBIGUOUS_COLUMN` | 3 | 6.7% |
| `AGGREGATION_ERROR` | 1 | 2.2% |
| `TIMEOUT` | 1 | 2.2% |
| **Total** | **45** | **100.0%** |

All recorded values are valid members of the unified `FailureClass`
taxonomy. No raw SQLSTATE codes, Python exception names, or semantic
guardrail labels are present in the final failure-class distribution.

### Policy failures classified as `OTHER`

A spot-check of the `OTHER` bucket found `PII_COLUMN_FORBIDDEN` guardrail
rejections, including attempts to use the protected `customer_id` column.

These policy failures are intentionally classified as `OTHER` rather than
being represented as a separate `FailureClass`. They represent guardrail
policy violations rather than SQL/schema failure categories.

The `OTHER` bucket should therefore not be interpreted as entirely
semantic or domain-reasoning failures.

## Controlled accuracy delta

The Phase 5 controlled ablation compares the guarded and repaired systems.

### Olist

- Guarded: 28.5%
- Repaired: 30.8%
- Delta: +2.3 percentage points

### BIRD

- Guarded: 34.0%
- Repaired: 38.0%
- Delta: +4.0 percentage points

The repaired system therefore improved execution accuracy on both
evaluation subsets, although the improvement is modest.

## Interpretation

The clearest finding from the Olist distribution is that
`UNKNOWN_COLUMN` is the dominant first-attempt failure class:

**24 of 45 first-attempt failures (53.3%) are `UNKNOWN_COLUMN`.**

This indicates that schema and column identification is the primary
failure surface observed in the Phase 5 evaluation. This finding provides
the main evidence for prioritizing schema/context retrieval in Phase 6.

The remaining failures are more heterogeneous. `OTHER` accounts for
16/45 failures (35.6%) and includes deliberate PII policy rejections,
while `AMBIGUOUS_COLUMN`, `AGGREGATION_ERROR`, and `TIMEOUT` account for
the remaining classified failures.

The BIRD automated distribution is limited to the 50-question controlled
subset and should not be interpreted as a full 200-question BIRD failure
distribution.

Overall, Phase 5 suggests that additional guardrail or repair tuning alone
is unlikely to address the dominant failure surface. The concentration of
`UNKNOWN_COLUMN` failures provides the primary motivation for Phase 6
retrieval and improved schema context.
