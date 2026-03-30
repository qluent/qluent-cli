---
name: compare-trees
description: Compare two metric trees side-by-side to validate the mechanism behind a change
argument-hint: "[tree1] [tree2] [period]"
allowed-tools: Bash(qluent *)
disable-model-invocation: true
---

# Compare metric trees

Run a side-by-side comparison of two trees for the same period.

```bash
qluent trees compare $0 $1 --period "$2" --json-output
```

For explicit date windows:

```bash
qluent trees compare $0 $1 --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD --json-output
```

## Interpret the mechanism

Compare the percentage changes between the two trees:

- **Both up by same %**: Pure volume growth
- **Tree1 up more than Tree2**: Mix shift or basket size increase
- **Tree1 up, Tree2 down**: Offset movements — investigate why
- **Revenue up but ROAS down**: Growth is coming at higher cost
- **Revenue up but Orders flat**: Higher basket size, not more customers

Always state the hypothesized mechanism and whether it needs further drill-down.
