---
name: investigate
description: Investigate metric, KPI, or business performance changes (revenue, cost, conversion, sales, ROAS) using the qluent bundled investigation command. Triggers on questions about why a metric changed, what drove a KPI movement, or how business performance is trending.
argument-hint: "[question or tree-name] [--period 'last week' | --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD]"
allowed-tools: Bash(qluent *)
---

# Investigate KPI movement

## Step 1: Run the investigation

If the user asked a natural-language question:

```bash
qluent trees investigate --question "$ARGUMENTS" --json-output
```

If the user named a specific tree and/or date windows, construct the command explicitly:

```bash
qluent trees investigate <tree_id> --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD --json-output
```

For natural-language periods:

```bash
qluent trees investigate <tree_id> --period "last week" --json-output
```

## Step 2: Parse the JSON response

Read the investigation bundle in this order:

1. `agent.status` — determines what to do next
2. `agent.top_findings` — fastest summary
3. `agent.gaps` — what evidence is missing
4. `agent.recommended_next_steps` — follow these before inventing your own drill-down
5. `evaluation`, `trend`, `root_cause` — detailed evidence

## Step 3: Act on agent.status

- **`resolved`**: Summarize the evidence and stop. Report the exact windows used.
- **`needs_tree_selection`**: Inspect `match.top_candidates`, pick the strongest tree (or ask the user), and re-run with the explicit tree_id.
- **`needs_more_data`** or **`partially_resolved`**: Run the first relevant command from `agent.recommended_next_steps`. Do NOT invent your own drill-down until you've exhausted the recommended steps.

## Step 4: Parallel deep-dive (when warranted)

For complex investigations where `agent.status` is `resolved` but the user wants deeper analysis, or when `partially_resolved`, launch specialized agents in parallel:

- **`trend-interpreter`** agent (sonnet): Run trend analysis on the primary tree to identify patterns and anomalies across multiple periods
- **`rca-validator`** agent (opus): Validate the top RCA findings by cross-referencing against trend data and checking for data artifacts
- **`segment-explorer`** agent (sonnet): Drill into the top Shapley contributors to find which segments concentrate the movement

Launch these in parallel using the Agent tool. Each agent has access to `qluent` CLI commands and will return structured findings.

Only use this step when:
- The user explicitly asks for a deeper analysis
- The investigation covers a broad time range (quarter+)
- RCA confidence is low and validation would help
- Multiple competing drivers need independent verification

## Step 5: Summarize

- Lead with the top findings
- Verify against `root_cause.conclusion.takeaways` and supporting evidence
- If agents were used, synthesize their outputs into a cohesive narrative
- Always report the exact current and comparison windows used

## Rules

- Always use `--json-output` when driving the workflow
- For full-year date ranges, if RCA times out, suggest quarterly breakdowns
- If the user asks a follow-up, check if the existing data answers it before re-running
