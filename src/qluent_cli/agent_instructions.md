# Qluent

You have access to the `qluent` CLI for business querying and deterministic
KPI analysis. Querying is the default workflow; metric trees are the advanced
workflow for governed movement analysis, RCA, trends, and levers.

## Commands

```bash
qluent suggestions --json-output                           # Start here: query-first project examples plus advanced tree analyses
qluent catalog --json-output                               # Catalog vocabulary + plan schema for deterministic queries
qluent plan '<QueryPlan JSON>' [--file <path>]              # Deterministic, catalog-checked query
qluent query "<question>" [--thread <id>]                   # NL-to-SQL fallback when the catalog cannot cover the question
qluent trees list                                           # List advanced metric trees
qluent trees get <tree_id>                                  # Show tree hierarchy
qluent trees validate <tree_id>                             # Validate tree SQL contracts and dimensions
qluent trees evaluate <tree_id> --period "last week"        # Evaluate with natural language period
qluent trees evaluate <tree_id> --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD
qluent trees evaluate <tree_id> --period "last week" --contract-output  # Stable deterministic query contract
qluent trees levers <tree_id> --period "last week"          # Quantify elasticity / lever impact scenarios
qluent elasticity <tree_id> --outcome <metric> --lever <metric> --period "last week"  # Evidence-labeled elasticity
qluent trees trend <tree_id> --periods 4 --grain week       # Multi-period trend analysis
qluent trees trend <tree_id> --periods 3 --grain month      # Monthly trend
qluent trees compare <tree_id> <tree_id> --period "last week"  # Side-by-side tree comparison
qluent trees investigate <tree_id> --period "last week"     # Validate + trend + evaluate + RCA bundle
qluent rca analyze revenue --period "last week"             # Deterministic tree + segment RCA
```

All commands support `--json-output` for raw JSON. The `trend` command supports `--as-of YYYY-MM-DD`
to set the reference date. The `investigate` command supports `--trend-as-of YYYY-MM-DD`
for reproducible bundled trend analysis.

Supported periods: "last week", "this week", "last month", "this month", "last quarter",
"yesterday", "last 30 days", "week over week", "month over month", or explicit ISO dates.

## Preferred agent workflow

**Start with query discovery.** Run `qluent suggestions --json-output` and
prefer its catalog-backed query examples. Author a composed plan when the
catalog covers the question; use `qluent query` as the NL-to-SQL fallback.

Metric trees are advanced and optional. Use them when the user explicitly asks
for deterministic KPI movement, RCA, trend classification, mix-shift, or
lever analysis and a matching tree is configured.

If the user already named the tree (e.g. "investigate revenue last week"), run:

```bash
qluent trees investigate <tree_id> --period "<period>" --json-output
```

If the user asks what they can do with the connected project, run:

```bash
qluent suggestions --json-output
```

For a general natural-language question, use the query workflow described
below. Do not require or probe metric trees first.

For an explicit advanced investigation without a named tree, list the
available trees and pick the best fit by matching the question against each
tree's `id`, `label`, `description`, child node labels, and declared
`dimensions`:

```bash
qluent trees list --json-output
qluent trees investigate <tree_id> --period "<period>" --json-output
```

For explicit date ranges:

```bash
qluent trees investigate <tree_id> --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD --json-output
```

Once you have the bundled response, use it to drive follow-ups: do NOT manually
chain `trend`, `evaluate`, or `rca analyze` unless `agent.recommended_next_steps`
calls for it. Running individual commands first is slower, more error-prone,
and misses the agent-level analysis.

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

- Prefer `--json-output` when an agent is driving the workflow.
- If `agent.status = needs_more_data` or `partially_resolved`, run the first relevant command from `agent.recommended_next_steps` before inventing your own drill-down.
- If `agent.status = resolved`, summarize the evidence and stop unless the user explicitly wants a deeper drill-down.
- Always report the exact current and comparison windows you used.
- Treat `agent.top_findings` as the fastest summary, then verify against `root_cause.conclusion.takeaways` and supporting evidence.
- For elasticity, sensitivity, leverage, impact, scenario, or "what if" follow-ups, read `investigate.levers` first. If the user asks for a selected outcome/lever relationship, run `qluent elasticity` and preserve its evidence type and confidence caveats. If you need a deeper scenario table, run `qluent trees levers` with the exact same `--current/--compare` windows.
- Reuse the exact windows from the last investigation for follow-ups unless the user explicitly changes the period.
- Never parse saved tool-result temp files or write ad-hoc Python to extract values from prior bash output. Use the structured JSON from `investigate`, `evaluate`, or `levers` directly.
- Do not rerun both JSON and non-JSON versions of the same qluent command unless the JSON is genuinely insufficient.

## When to use `qluent plan` / `qluent query` vs metric-tree commands

The query workflow is the default for values, aggregations, breakdowns,
rankings, comparisons, and general business questions. The tree commands
(`investigate`, `evaluate`, `trend`, `rca analyze`, ...) are deterministic,
fast, and reproducible, but advanced: use them for explicit governed movement
analysis, RCA, trend, mix, or elasticity requests that map to a configured
tree.

`qluent plan` compiles a typed QueryPlan you author against the project's
closed-world query catalog — deterministic (the same plan always produces the
same SQL) and correct-by-construction (anything outside the catalog is rejected
with a repairable message). Prefer it over `qluent query` for ad-hoc
aggregations, breakdowns, filters and rankings whenever the catalog's
bases/metrics/dimensions cover the question:

- Run `qluent catalog --json-output` once per session; it returns the full
  vocabulary and the QueryPlan JSON schema (`plan_schema`).
- Author the plan (source -> filter_by -> group_by -> top_k / window) and
  submit it with `qluent plan --file <path> --json-output`.
- `status = plan_invalid` is a repair instruction, not a failure: fix the plan
  from the error message and re-run. Only fall back to `qluent query` when the
  catalog genuinely lacks the vocabulary (a column/metric that does not exist).
- `QUERY_CATALOG_INVALID` is *not* repairable: the project's catalog itself
  fails to load, so no plan will ever compile. Stop re-authoring plans — report
  the error (the catalog is fixed under the Model tab) and use `qluent query`.
- Before combining numbers across several plan results, check `grain` and
  `metrics[*].summable`: only summable metrics (plain sums, row counts) may be
  added across result sets — recompute averages, ratios and distinct counts.

`qluent query` runs the backend's LLM query workflow (natural language -> generated
SQL -> execution) and is for everything neither trees nor the catalog can answer:

- Row-level or entity-level questions ("top 10 customers by refunds", "list last
  week's failed orders").
- Arbitrary aggregations, filters, or joins over metrics and dimensions no tree declares.
- Explicit raw-data requests (a table, an export, the SQL itself).

It is non-deterministic, slower (can take minutes), and returns the generated `sql`,
up to 1000 inline rows in `data`, plus a `download_url` for the full result set.

Rules:

- Use `--json-output` and check `status`: `ok`, `clarification_needed`, or `error`.
- If `status = clarification_needed`, answer by re-running
  `qluent query "<your answer>" --thread <thread_id>` with the `thread_id` from the response.
- Reuse `thread_id` for follow-up questions that build on the same result.
- Verify the returned `sql` matches the user's intent before presenting numbers, and
  present the numbers as coming from an ad-hoc query, never as deterministic tree evidence.
- When the response carries a `plan`, that is the QueryPlan the backend compiled for the
  question. Review it instead of re-authoring one: it is a QueryPlan document, so a
  corrected version goes straight back through `qluent plan --file <path> --json-output`
  and re-runs deterministically. A `plan` of `null` just means this project does not
  compile queries through a plan — fall back to reviewing the `sql`.
- Never use `qluent query` to re-derive numbers a tree command already returned.

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

## Agent-specific notes

For Claude Code: the qluent plugin exposes `/investigate`, `/trend`, `/compare-trees`, and
`/rca` slash commands that wrap the workflow above. Prefer those over manually chaining the
underlying CLI commands.

For Codex CLI / Cursor / Continue / Zed (and any other MCP client): run `qluent mcp serve`
and connect via the [Model Context Protocol](https://modelcontextprotocol.io). The MCP tools
return the same JSON contracts as the CLI's `--json-output` mode, so the workflow rules
above apply unchanged.
