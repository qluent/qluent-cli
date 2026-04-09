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
qluent trees levers <tree_id> --period "last week"          # Quantify elasticity / lever impact scenarios
qluent trees trend <tree_id> --periods 4 --grain week       # Multi-period trend analysis
qluent trees trend <tree_id> --periods 3 --grain month      # Monthly trend
qluent trees compare <tree_id> <tree_id> --period "last week"  # Side-by-side tree comparison
qluent trees investigate revenue --period "last week"       # Validate + trend + evaluate + RCA bundle
qluent trees investigate --question "Why did revenue drop last week?"  # Match tree + infer windows + bundle RCA
qluent rca analyze revenue --period "last week"             # Deterministic tree + segment RCA
```

All commands support `--json-output` for raw JSON. The `trend` command supports `--as-of YYYY-MM-DD`
to set the reference date. The `investigate` command supports `--trend-as-of YYYY-MM-DD`
for reproducible bundled trend analysis.

Supported periods: "last week", "this week", "last month", "this month", "last quarter",
"yesterday", "last 30 days", "week over week", "month over month", or explicit ISO dates.

## Preferred Claude Code workflow

**IMPORTANT: Always start with `investigate`.** Do NOT manually chain `trend`, `evaluate`,
`list`, or `rca analyze` commands. The `investigate` command bundles all of these into a
single call and returns a structured response. Running individual commands is slower,
more error-prone, and misses the agent-level analysis.

Your first command for ANY question about metrics, KPIs, revenue, sales, costs, or
business performance should be:

```bash
qluent trees investigate --question "<user's question>" --json-output
```

If the user already named the tree, use:

```bash
qluent trees investigate <tree_id> --period "<period>" --json-output
```

For explicit date ranges:

```bash
qluent trees investigate <tree_id> --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD --json-output
```

Only use individual commands (`trend`, `evaluate`, `rca analyze`) as follow-up steps
when `investigate` returns `agent.recommended_next_steps` that call for them.

Read the investigation bundle in this order:

1. `agent.status`
2. `agent.top_findings`
3. `agent.gaps`
4. `agent.recommended_next_steps`
5. `levers` — embedded elasticity / lever summary when available
6. `root_cause`, `evaluation`, and `trend` details for evidence

Use these rules:

- Prefer `--json-output` when Claude Code is driving the workflow.
- If `agent.status = needs_tree_selection`, inspect `match.top_candidates` and either pick the strongest tree or ask the user.
- If `agent.status = needs_more_data` or `partially_resolved`, run the first relevant command from `agent.recommended_next_steps` before inventing your own drill-down.
- If `agent.status = resolved`, summarize the evidence and stop unless the user explicitly wants a deeper drill-down.
- Always report the exact current and comparison windows you used.
- Treat `agent.top_findings` as the fastest summary, then verify against `root_cause.conclusion.takeaways` and supporting evidence.
- For elasticity, sensitivity, leverage, impact, scenario, or "what if" follow-ups, read `investigate.levers` first. If you need a deeper scenario table, run `qluent trees levers` with the exact same `--current/--compare` windows.
- Reuse the exact windows from the last investigation for follow-ups unless the user explicitly changes the period.
- Never parse saved tool-result temp files or write ad-hoc Python to extract values from prior bash output. Use the structured JSON from `investigate`, `evaluate`, or `levers` directly.
- Do not rerun both JSON and non-JSON versions of the same qluent command unless the JSON is genuinely insufficient.

## Manual root cause analysis workflow

Only use this workflow when `investigate` is insufficient or when following up on
`agent.recommended_next_steps`. Do NOT start here.

### Step 1: Spot the anomaly with `trend`
```bash
qluent trees trend revenue --periods 4 --grain week
```
Look for: which period had an unusual change? Is the trend accelerating, declining, or volatile?

### Step 2: Drill into the anomaly with `evaluate`
```bash
qluent trees evaluate revenue --period "last week"
```
The Shapley attribution tells you WHICH sub-metric drove the change and by how much.
Focus on the top contributors — they explain where the delta came from.

### Step 3: Quantify future lever impact with `levers`
```bash
qluent trees levers revenue --period "last week" --json-output
```
Use this for explicit elasticity / impact questions. The output ranks the biggest
levers by absolute elasticity and shows scenario impacts such as +1%, +5%, and +10%.
Treat these as local linear estimates, not forecasts.

### Step 4: Validate segment contracts with `trees validate`
```bash
qluent trees validate revenue
```
Use this before relying on segment RCA. A tree should explicitly project its execution columns
and declared dimensions at every leaf node.

### Step 5: Run deterministic root cause analysis with `rca analyze`
```bash
qluent rca analyze revenue --period "last week"
```
This traverses the tree and, when dimensions are available, cuts suspect nodes by segment
to surface where the movement is concentrated.

### Step 6: Cross-reference with `compare`
```bash
qluent trees compare revenue order_volume --period "last week"
```
Comparing related trees validates the mechanism. For example:
- Revenue up +20% but Orders up +20% → pure volume growth
- Revenue up +20% but Orders up +5% → basket size / mix shift
- Revenue up but ROAS down → growth is coming at higher cost

## How to interpret results

### Shapley-value attribution (Top contributors)
Each child's contribution to the parent's delta is computed using Shapley values from
cooperative game theory. This answers: "how much of the parent's change is attributable
to each child?"

Key properties:
- **Contributions sum to the parent delta** — they fully explain the change.
- **A share > 100%** means this child drove MORE change than the total, offset by others.
- **A negative share** means this child moved against the overall trend.
- This is NOT a simple percentage breakdown — it accounts for formula interactions
  (e.g., in ROAS = revenue / spend, both numerator and denominator are attributed correctly).

### Trend labels
- **accelerating**: positive and growing faster
- **decelerating**: positive but slowing down
- **recovering**: was negative, now positive
- **declining**: was positive, now negative
- **volatile**: direction changes frequently
- **stable**: changes within ±2%

### RCA confidence
`conclusion.confidence` and `conclusion.confidence_score` are NOT probabilities.
They are evidence-coverage heuristics.

Interpret them like this:
- `confidence_type = evidence_coverage_heuristic` means the score reflects how much deterministic evidence is available.
- Higher scores mean broader coverage across driver, time-slice, segment/mix-shift, and mechanism evidence.
- Warnings and unresolved branches reduce the score.
- Use `evidence_types_present`, `evidence_types_missing`, and `confidence_factors` to explain why the score is high, medium, or low.
- Never describe `80%` as "80% likely to be true." Describe it as an evidence or coverage score.

### Lever / scenario interpretation
`levers.top_levers[]` and `trees levers` quantify forward-looking impact from elasticities.

- `recommended_direction = increase` means raising that node improves the root KPI.
- `recommended_direction = decrease` means reducing that node improves the root KPI.
- `estimated_root_delta_ratio` is the implied root percent change from the scenario.
- `estimated_root_delta_value` is the implied absolute root change using the current-period root value.
- These are local linear estimates from the current operating point, not forecasts or causal guarantees.

### Example analysis
"Why did revenue change last week?"

1. `trend` shows: Revenue was +11%, +11%, then +6% → **decelerating**
2. `evaluate` shows: Owned channels drove 143% of growth, but Organic declined 56%
3. `compare` Revenue vs Orders: Owned revenue +20% but Owned orders -5% → higher basket size,
   not more customers. Organic orders -5% matching Organic revenue -12% → volume loss.

Conclusion: "Revenue growth is decelerating. Last week's gain came from higher basket sizes
in owned channels (Direct, Email), not from customer acquisition. Organic traffic continues
to decline — investigate SEO or content changes."
