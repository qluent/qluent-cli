"""Qluent CLI entry point."""

from __future__ import annotations

import click

from qluent_cli.rca import rca
from qluent_cli.trees import trees


@click.group()
def cli() -> None:
    """Qluent — metric tree analysis from the command line."""


@cli.command()
@click.option("--api-key", help="API key (qk_...)")
@click.option("--url", help="API base URL")
@click.option("--project", help="Project UUID")
@click.option("--email", help="User email")
@click.option(
    "--client-safe/--no-client-safe",
    default=None,
    help="Redact tree formulas and SQL contract details for client-facing use.",
)
def config(
    api_key: str | None,
    url: str | None,
    project: str | None,
    email: str | None,
    client_safe: bool | None,
) -> None:
    """Configure Qluent API credentials."""
    from qluent_cli.config import CONFIG_FILE, default_client_safe, mask_key, save_config

    if not any([api_key, url, project, email, client_safe is not None]):
        if CONFIG_FILE.exists():
            import json

            data = json.loads(CONFIG_FILE.read_text())
            if "client_safe" not in data:
                data["client_safe"] = default_client_safe(
                    str(data.get("api_url") or "https://api.qluent.io")
                )
            for k, v in data.items():
                click.echo(f"  {k}: {mask_key(v) if k == 'api_key' else v}")
        else:
            click.echo("No config file found. Run: qluent config --api-key qk_... --project UUID --email you@co.com")
        return

    result = save_config(
        api_key=api_key,
        api_url=url,
        project_uuid=project,
        user_email=email,
        client_safe=client_safe,
    )
    if "client_safe" not in result:
        result["client_safe"] = default_client_safe(
            str(result.get("api_url") or "https://api.qluent.io")
        )
    click.echo("Config saved to ~/.qluent/config.json")
    for k, v in result.items():
        click.echo(f"  {k}: {mask_key(v) if k == 'api_key' else v}")


cli.add_command(trees)
cli.add_command(rca)


_CLAUDE_INSTRUCTIONS = """\
# Qluent Metric Trees

You have access to the `qluent` CLI for deterministic KPI analysis. Use it to answer
questions about business performance, revenue drivers, cost breakdowns, and trend changes.

## Commands

```bash
qluent trees list                                           # List available metric trees
qluent trees get <tree_id>                                  # Show tree hierarchy
qluent trees validate <tree_id>                             # Validate tree SQL contracts and dimensions
qluent trees evaluate <tree_id> --period "last week"        # Evaluate with natural language period
qluent trees evaluate <tree_id> --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD
qluent trees trend <tree_id> --periods 4 --grain week       # Multi-period trend analysis
qluent trees trend <tree_id> --periods 3 --grain month      # Monthly trend
qluent trees compare <tree_id> <tree_id> --period "last week"  # Side-by-side tree comparison
qluent rca analyze revenue --period "last week"             # Deterministic tree + segment RCA
```

All commands support `--json-output` for raw JSON. The `trend` command supports `--as-of YYYY-MM-DD`
to set the reference date.

Supported periods: "last week", "this week", "last month", "this month", "last quarter",
"yesterday", "last 30 days", "week over week", "month over month", or explicit ISO dates.

## Root cause analysis workflow

When asked to analyze business performance, follow this 3-step drill-down:

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

### Step 3: Validate segment contracts with `trees validate`
```bash
qluent trees validate revenue
```
Use this before relying on segment RCA. A tree should explicitly project its execution columns
and declared dimensions at every leaf node.

### Step 4: Run deterministic root cause analysis with `rca analyze`
```bash
qluent rca analyze revenue --period "last week"
```
This traverses the tree and, when dimensions are available, cuts suspect nodes by segment
to surface where the movement is concentrated.

### Step 5: Cross-reference with `compare`
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

### Example analysis
"Why did revenue change last week?"

1. `trend` shows: Revenue was +11%, +11%, then +6% → **decelerating**
2. `evaluate` shows: Owned channels drove 143% of growth, but Organic declined 56%
3. `compare` Revenue vs Orders: Owned revenue +20% but Owned orders -5% → higher basket size,
   not more customers. Organic orders -5% matching Organic revenue -12% → volume loss.

Conclusion: "Revenue growth is decelerating. Last week's gain came from higher basket sizes
in owned channels (Direct, Email), not from customer acquisition. Organic traffic continues
to decline — investigate SEO or content changes."
"""


@cli.command()
def instructions() -> None:
    """Print a CLAUDE.md snippet for Claude Code integration."""
    click.echo(_CLAUDE_INSTRUCTIONS)
