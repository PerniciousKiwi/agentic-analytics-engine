# Limitations

## Phase 8 — Selective Prediction

The confidence classifier is trained on 330 eligible examples from the
BIRD-200 and Olist evaluation suites. Twenty deliberately unanswerable
Olist examples are excluded from confidence-model training because using
their gold answerability labels as runtime confidence features would
introduce target leakage.

Confidence-model metrics are reported using five-fold out-of-fold
predictions. The fitted production model is subsequently trained on all
eligible examples.

The selected confidence threshold is tuned using the same out-of-fold
predictions used to report risk-coverage performance. This introduces
mild threshold-selection bias because there is no independent
threshold-selection holdout.

Several confidence signals are structurally unavailable for BIRD.
Warehouse-specific checks such as warehouse date bounds and Olist
retrieval scores are therefore marked as unavailable rather than
fabricated. This contributes to substantially weaker selective coverage
on BIRD than on Olist.

The grounding score is a regex-based heuristic that checks whether
numbers and named entities in the synthesized answer appear in the
result rows. It is a proxy for grounding, not a complete factual
verification system, and can produce false negatives or false positives.

The global selective threshold is 0.730965, selected for a target
selective accuracy of 85%. On out-of-fold predictions it achieves
86.36% selective accuracy at 13.33% combined coverage.

At the same global threshold, BIRD-200 achieves 100.00% selective
accuracy at only 0.50% coverage, while the eligible Olist subset
achieves 86.05% selective accuracy at 33.08% coverage. The extremely
low BIRD coverage shows that the confidence model transfers much more
poorly to BIRD than to Olist.

The current process feature `agent_steps` is effectively unavailable in
the confidence-training pipeline because the dataset is generated from
the retrieval-guarded-repaired evaluation system rather than the
multi-step Phase 7 agent loop. It is therefore currently constant and
should not be interpreted as a validated confidence signal.