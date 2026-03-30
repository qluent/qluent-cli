---
name: trend
description: Run multi-period trend analysis for a metric tree
argument-hint: "[tree-name] [periods] [grain: week|month]"
allowed-tools: Bash(qluent *)
disable-model-invocation: true
---

# Trend analysis

Run a multi-period trend for the specified tree.

```bash
qluent trees trend $0 --periods $1 --grain $2 --json-output
```

Defaults if not provided: periods=4, grain=week. Use grain=month for longer-range analysis.

To pin the reference date, add `--as-of YYYY-MM-DD`.

## Interpret the results

For each period, report: value, absolute change, percentage change, and trend label (see interpretation guide for label definitions).

Highlight the anomalous period and suggest drilling into it with `/investigate` or `evaluate`.
