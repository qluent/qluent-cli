# Qluent Metric Trees

You have access to the `qluent` CLI for deterministic KPI analysis. Use it to answer
questions about business performance, revenue drivers, cost breakdowns, and trend changes.

## Commands

```bash
qluent trees list                                           # List available metric trees
qluent trees match "Why did revenue drop last week?"        # Match a question to the best tree + infer windows
qluent trees get <tree_id>                                  # Show tree hierarchy
qluent trees validate <tree_id>                             # Validate tree SQL contracts and dimensions
qluent trees evaluate <tree_id> --period "last week"        # Evaluate with natural language period
qluent trees evaluate <tree_id> --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD
qluent trees trend <tree_id> --periods 4 --grain week       # Multi-period trend analysis
qluent trees compare <tree_id> <tree_id> --period "last week"  # Side-by-side tree comparison
qluent trees investigate revenue --period "last week"       # Validate + trend + evaluate + RCA bundle
qluent rca analyze revenue --period "last week"             # Deterministic tree + segment RCA
```

All commands support `--json-output` for raw JSON. The `trend` command supports `--as-of YYYY-MM-DD`.
The `investigate` command supports `--trend-as-of YYYY-MM-DD` for reproducible bundled analysis.

Supported periods: "last week", "this week", "last month", "this month", "last quarter",
"yesterday", "last 30 days", "week over week", "month over month", or explicit ISO dates.

## Workflows

Use the built-in skills for analysis workflows:

- `/investigate` — Primary entry point. Bundles validation, trend, evaluation, and RCA in one call. Auto-invoked for KPI questions.
- `/trend` — Multi-period trend analysis for a specific tree.
- `/compare-trees` — Side-by-side comparison to validate mechanisms (volume vs mix shift).
- `/rca` — Standalone root cause analysis with validation and confidence interpretation.

Always prefer `/investigate` over manually chaining individual commands.
