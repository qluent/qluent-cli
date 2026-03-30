---
name: qluent-interpretation
description: Qluent output interpretation reference
user-invocable: false
---

# Interpreting qluent results

## Shapley-value attribution (Top contributors)

Each child's contribution to the parent's delta is computed using Shapley values from cooperative game theory. This answers: "how much of the parent's change is attributable to each child?"

Key properties:
- **Contributions sum to the parent delta** — they fully explain the change
- **A share > 100%** means this child drove MORE change than the total, offset by others
- **A negative share** means this child moved against the overall trend
- This is NOT a simple percentage breakdown — it accounts for formula interactions (e.g., in ROAS = revenue / spend, both numerator and denominator are attributed correctly)

## Trend labels

- **accelerating**: positive and growing faster
- **decelerating**: positive but slowing down
- **recovering**: was negative, now positive
- **declining**: was positive, now negative
- **volatile**: direction changes frequently
- **stable**: changes within +/-2%

## RCA confidence

`conclusion.confidence` and `conclusion.confidence_score` are NOT probabilities. They are evidence-coverage heuristics.

- `confidence_type = evidence_coverage_heuristic` means the score reflects how much deterministic evidence is available
- Higher scores mean broader coverage across driver, time-slice, segment/mix-shift, and mechanism evidence
- Warnings and unresolved branches reduce the score
- Use `evidence_types_present`, `evidence_types_missing`, and `confidence_factors` to explain why the score is high, medium, or low
- Never describe `80%` as "80% likely to be true." Describe it as an evidence or coverage score

## Synthesis pattern

Combine evidence across steps: trend observation (direction + anomaly) + Shapley attribution (which sub-metric drove it) + mechanism validation (volume vs mix shift via `/compare-trees`) = conclusion with actionable takeaway.
