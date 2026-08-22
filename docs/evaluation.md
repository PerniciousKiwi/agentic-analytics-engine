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

## Phase 4 guardrails

Phase 4 adds SQL guardrails around the baseline generation system.

The guarded pipeline applies the following checks before SQL execution:

1. **Read-only AST validation**
   - Rejects DML such as `DELETE`, `UPDATE`, and `INSERT`.
   - Rejects SQL parse failures.

2. **Catalog validation**
   - Rejects unknown tables.
   - Rejects unknown columns.
   - Rejects ambiguous unqualified columns.
   - Resolves schema-qualified and aliased table references against the Cardinal manifest.

3. **Cartesian-join validation**
   - Rejects explicit `CROSS JOIN`.
   - Rejects joins without an `ON` or `USING` condition.

4. **PII validation**
   - Analyst queries cannot select catalogued PII columns.
   - Privileged-role access is supported by the guardrail API.

5. **Result-size protection**
   - An outer `LIMIT` is injected when no limit exists.
   - Existing limits above the configured maximum are reduced.
   - Smaller existing limits are preserved.

6. **Cost validation**
   - Provides a cost guardrail interface for rejecting queries whose estimated execution cost exceeds a configured threshold.

### Failure classification

PostgreSQL execution failures now preserve SQLSTATE values in
`failure_class`. In particular:

- `42703` — undefined column
- `42P01` — undefined table

This allows evaluation runs to distinguish execution-time identifier
failures from guardrail rejections.

### Phase 4 baseline

The recorded Olist baseline run contained:

- 150 questions
- 100 executed successfully
- 58 correct
- 38.67% execution accuracy
- 21 `42703` failures
- 3 `42P01` failures

The 24 historical PostgreSQL identifier failures were replayed through
the corrected catalog guardrail. All 24 were rejected before execution,
giving a 100% replay-blocking rate for this failure set.

The BIRD suite contains 200 SQLite questions. PostgreSQL SQLSTATE
classification is therefore not applicable to BIRD execution failures.

### Guarded evaluation

The guarded system is registered as `baseline_guarded` alongside the
existing `baseline` and `oracle` systems.

Full BIRD and Olist evaluations are intentionally run only when required
because they are computationally expensive.
