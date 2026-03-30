---
name: rca
description: Run standalone deterministic root cause analysis on a metric tree with optional validation
argument-hint: "[tree-name] [period]"
allowed-tools: Bash(qluent *)
disable-model-invocation: true
---

# Root cause analysis

## Step 1: Validate the tree

```bash
qluent trees validate $0 --json-output
```

Check that leaf nodes project all declared dimensions. If dimensions are missing, note this as a gap — segment-level RCA will be limited.

## Step 2: Run deterministic RCA

```bash
qluent rca analyze $0 --period "$1" --json-output
```

For explicit date windows:

```bash
qluent rca analyze $0 --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD --json-output
```

## Step 3: Report the results

Focus on `conclusion.takeaways` and the top driver nodes. See the interpretation guide for Shapley attribution and confidence score rules.

- Lead with the root cause and supporting evidence
- List the top contributing nodes with their Shapley attribution shares
- Note any gaps (missing dimensions, unresolved branches)
- Suggest `/compare-trees` if mechanism validation would help
