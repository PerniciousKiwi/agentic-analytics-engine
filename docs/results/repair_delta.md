# Phase 5 Repair Accuracy Delta

## Scope

This document records the measured accuracy change from the Phase 4 guarded
system to the Phase 5 repaired system.

The BIRD result shown below uses the controlled 50-question evaluation subset
used for the Phase 5 ablation. The Olist result is the 150-question evaluation
reported by the Phase 5 validation script.

## Accuracy

| Suite | Guarded | Repaired | Delta |
|---|---:|---:|---:|
| `bird_dev_200` (50-question subset) | 17/50 (34.0%) | 19/50 (38.0%) | +4.0 pp |
| `olist_gold_150` | 28.5% | 28.5% | +0.0 pp |

## Controlled BIRD ablation

The BIRD subset was also used to separate prompt, guardrail, and repair
effects:

| Configuration | Prompt | Guardrails | Repair | Accuracy |
|---|---|---|---|---:|
| A | Old | No | No | 17/50 (34.0%) |
| B | New | No | No | 17/50 (34.0%) |
| C | New | Yes | No | 17/50 (34.0%) |
| D | New | Yes | Yes | 19/50 (38.0%) |

On this 50-question sample:

- Prompt effect (B - A): 0 questions.
- Guardrail effect (C - B): 0 questions.
- Repair-enabled system (D - C): +2 questions.

The controlled result therefore detects no prompt or guardrail accuracy effect
at this sample size. The repaired system is 2 questions higher than the guarded
system on this particular subset. This is a directional observation rather
than a statistically established effect.

## Interpretation

The earlier comparison between the original baseline and repaired system was
confounded by a prompt-template change. Re-evaluating the same 50-question
subset removed that subset confound.

The controlled comparison does not establish that the prompt change has no
effect in general; it establishes that no effect was detected on this
50-question sample.

Likewise, the observed repair improvement should not be interpreted as a
general accuracy guarantee. The sample is small, and the remaining evaluation
failures are dominated by SQL-generation and schema/context errors that are
not necessarily detectable by the verification layer.

## Reproducibility

The reported BIRD results are based on:

- Guarded: `bird_dev_200_baseline_guarded_20260823T110325Z.json`
- Repaired: `bird_dev_200_baseline_repaired_20260823T104237Z.json`

The validation script independently reports the Olist guarded-to-repaired
delta as 28.5% → 28.5% (+0.0 pp).
