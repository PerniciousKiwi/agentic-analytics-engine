# Phase 9 — Ambiguity Detection

## Objective

Phase 9 adds an ambiguity gate before SQL generation.

The goal is to detect analytics questions that cannot be answered safely without first clarifying the user's intended metric, entity, filter, time interpretation, or tie-handling rule.

If a question is classified as ambiguous, the system abstains immediately and returns a clarifying question instead of continuing into SQL generation, guardrails, execution, or repair.

## Ambiguity Categories

The evaluation suite contains 100 ambiguous questions distributed evenly across five categories:

| Ambiguity type | Questions |
| -------------- | --------: |
| metric         |        20 |
| time_grain     |        20 |
| entity         |        20 |
| filter         |        20 |
| tiebreak       |        20 |
| **Total**      |   **100** |

Each question includes an authored ambiguity type and a specific clarifying question.

## Detector Context

The initial hypothesis was to always provide the ambiguity detector with:

* the semantic metric definitions from `metrics.yml`
* the glossary definitions from `glossary.yml`

Retrieved schema context was evaluated separately as an ablation.

### Context Ablation

A balanced 25-question subset was evaluated using both context configurations.

| Context mode                |  N | Detection rate | Correct-type rate | Parser fallbacks | Mean LLM latency |
| --------------------------- | -: | -------------: | ----------------: | ---------------: | ---------------: |
| Semantic only               | 25 |          88.0% |             40.0% |                0 |         362.6 ms |
| Semantic + retrieved schema | 25 |         100.0% |             20.0% |               24 |        1288.9 ms |

The apparent 100% detection rate with retrieved schema is misleading because 24 of 25 responses failed structured parsing and triggered the fail-closed fallback.

Adding retrieved schema also increased mean LLM latency from approximately 363 ms to 1289 ms.

Therefore the production detector uses:

`metrics.yml + glossary.yml`

without retrieved schema context.

## Parsing Policy

The detector uses a fail-closed parsing policy.

If the classifier response cannot be parsed reliably, the system treats the question as ambiguous rather than silently continuing into SQL generation.

Parser fallbacks intentionally do not receive a fabricated ambiguity type. This prevents malformed responses from contaminating per-type accuracy measurements.

In the final frozen evaluation, parser fallback count was zero.

## Verification Ablation

A second-stage LLM verifier was also evaluated.

The verifier independently reviewed questions that Stage 1 classified as ambiguous and decided whether the proposed ambiguity should actually block execution.

On a 50-question development set:

* Stage 1 classified 48/50 questions as ambiguous.
* The verifier was invoked 48 times.
* The verifier overturned 9 ambiguity decisions.
* False-positive rate fell from 96.0% to 78.0%.

Although the verifier reduced false positives, the remaining false-positive rate was still too high and the approach required an additional LLM call for nearly every Stage-1 positive.

The verifier was therefore retained as experimental code but disabled in the final production configuration.

## Final Frozen Configuration

The final evaluation used:

* semantic context only
* no retrieved schema context
* no second-stage verifier
* temperature 0
* fail-closed structured parsing
* 100 ambiguous positive questions
* 30 previously unseen, answerable Olist gold questions as negative examples

The prompt and architecture were frozen before this final evaluation.

## Final Results

| Ambiguity type |  N | Detection rate | Correct-type rate |
| -------------- | -: | -------------: | ----------------: |
| metric         | 20 |          85.0% |             55.0% |
| time_grain     | 20 |         100.0% |             95.0% |
| entity         | 20 |          95.0% |             60.0% |
| filter         | 20 |          65.0% |              0.0% |
| tiebreak       | 20 |          75.0% |              0.0% |

**Overall ambiguity detection rate:** 84.0%

**False-positive rate on unseen answerable questions:** 33.3% (10/30)

**Parser fail-closed fallbacks:** 0

Correct-type rate is intentionally strict: the question must be detected as ambiguous and assigned the authored ambiguity category.

## Interpretation

The detector successfully identifies most genuinely ambiguous questions, with an overall detection rate of 84.0%.

Time-grain ambiguity is the strongest category. All 20 time-grain questions were detected and 95% received the authored ambiguity type.

Metric and entity ambiguity are also detected reliably, although distinguishing between those categories remains imperfect.

Filter and tiebreak classification are substantially weaker. In particular, the detector frequently recognizes that a question is ambiguous while assigning a different ambiguity type than the authored label.

The more significant limitation is false-positive behavior. The final unseen false-positive rate of 33.3% means the current classifier still abstains too aggressively on some answerable analytics questions.

Error analysis showed a recurring tendency for the model to invent alternative analytical interpretations even when the user had already specified a metric, grouping dimension, filter, or time grain.

Further prompt specialization against individual evaluation questions was deliberately avoided to reduce benchmark overfitting.

## Pipeline Behavior

The ambiguity gate runs before the existing Phase 8 pipeline.

For a clear question:

`question -> ambiguity gate -> Phase 8 generation / guardrails / execution / repair`

For an ambiguous question:

`question -> ambiguity gate -> abstain + clarifying question`

When ambiguity is detected:

* SQL generation is skipped.
* SQL guardrails are skipped.
* SQL execution is skipped.
* repair is skipped.
* `abstained=true`
* `abstain_reason=AMBIGUOUS`
* `generation_skipped=true`

This preserves the Phase 8 implementation rather than duplicating or modifying its internal generation and repair behavior.

## Conclusion

Phase 9 demonstrates a functioning ambiguity-aware abstention layer and exposes an important practical limitation of small-model ambiguity classification.

The final detector achieves strong ambiguity recall but still over-abstains on a meaningful fraction of answerable questions.

The experiments also showed that adding retrieved schema context and adding a second LLM verification stage did not provide sufficient benefit relative to their parsing, latency, and complexity costs.

The final production choice is therefore the simpler semantic-only, single-stage ambiguity gate, with the measured limitations documented rather than hidden through further benchmark-specific prompt tuning.
