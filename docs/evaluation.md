# Evaluation Semantics

## Execution accuracy

For answerable questions, `correct` means that the predicted SQL
executed successfully and its result rows matched the gold SQL result
under the execution comparator.

The comparator is order-insensitive, preserves duplicate rows, treats
NULL as equal to NULL, and applies the configured floating-point
tolerance.

## Unanswerable questions

The Olist gold suite contains 20 intentionally unanswerable questions.

For these records:

- `gold_sql` is absent.
- The Oracle system abstains.
- `abstained` is `true`.
- `correct` is `true`.

Here, `correct` means that the evaluation system produced the expected
behavior for the question. It does not mean that two SQL result sets
were compared.

This distinction is intentional because later phases introduce
model-generated abstention. The same result schema can therefore
represent both successful SQL execution and correct abstention.

## BIRD sampling

The BIRD evaluation suite contains 200 questions sampled by difficulty.

The sample intentionally oversamples challenging questions to
stress-test the guarded and repair pipeline. Therefore, the BIRD
subset is not intended to be directly comparable with published BIRD
leaderboard proportions.

Sampling seed: `20260821`.

BIRD source/version identifier: `3c11fb1`.
