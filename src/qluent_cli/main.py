"""Qluent CLI entry point."""

from __future__ import annotations

import click

from qluent_cli.trees import trees


@click.group()
def cli() -> None:
    """Qluent — metric tree analysis from the command line."""


@cli.command()
@click.option("--api-key", help="API key (qk_...)")
@click.option("--url", help="API base URL")
@click.option("--project", help="Project UUID")
@click.option("--email", help="User email")
def config(api_key: str | None, url: str | None, project: str | None, email: str | None) -> None:
    """Configure Qluent API credentials."""
    from qluent_cli.config import save_config

    if not any([api_key, url, project, email]):
        # Show current config
        from qluent_cli.config import CONFIG_FILE

        if CONFIG_FILE.exists():
            click.echo(CONFIG_FILE.read_text())
        else:
            click.echo("No config file found. Run: qluent config --api-key qk_... --project UUID --email you@co.com")
        return

    result = save_config(api_key=api_key, api_url=url, project_uuid=project, user_email=email)
    click.echo(f"Config saved to ~/.qluent/config.json")
    for k, v in result.items():
        display = v[:10] + "..." if k == "api_key" and len(v) > 10 else v
        click.echo(f"  {k}: {display}")


cli.add_command(trees)


_CLAUDE_INSTRUCTIONS = """\
# Qluent Metric Trees

You have access to the `qluent` CLI for deterministic KPI analysis. Use it to answer
questions about business performance, revenue drivers, cost breakdowns, and trend changes.

## Commands

```bash
qluent trees list                                    # List available metric trees
qluent trees get <tree_id>                           # Show tree hierarchy
qluent trees evaluate <tree_id> --period "last week" # Evaluate with natural language period
qluent trees evaluate <tree_id> --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD
qluent trees evaluate <tree_id> --json-output        # Raw JSON for further processing
```

Supported periods: "last week", "this week", "last month", "this month", "last quarter",
"yesterday", "last 30 days", "week over week", "month over month", or explicit ISO dates.

## How to interpret results

### Tree structure
Each metric tree decomposes a top-level KPI into sub-metrics. Leaf nodes execute SQL queries
against the data warehouse. Formula nodes compute from their children (e.g., `paid + owned + organic`).

### Evaluation output
- **Current vs Comparison**: Two time windows compared side-by-side.
- **Delta**: The absolute change (current - comparison).
- **Delta ratio**: The percentage change (delta / comparison).

### Shapley-value attribution (Top contributors)
Each child's contribution to the parent's delta is computed using Shapley values from
cooperative game theory. This answers: "how much of the parent's change is attributable
to each child?"

Key properties:
- **Contributions sum to the parent delta** — they fully explain the change.
- **A share > 100%** means this child drove MORE change than the total, offset by others moving opposite.
- **A negative share** means this child moved against the overall trend (e.g., grew while total declined).
- This is NOT a simple percentage breakdown — it accounts for formula interactions (e.g., in ROAS = revenue / spend, both numerator and denominator changes are attributed correctly).

### Example interpretation
```
Top contributors:
  Owned Channel Revenue    +$25,251  (143% of change)
  Organic Revenue           -$9,899  (-56% of change)
  Paid Channel Revenue      +$2,275  (13% of change)
```
Read as: "Owned channels drove $25K of growth (more than the total $17.6K increase),
but Organic declined by $9.9K, partially offsetting the gains. Paid contributed modestly."

## Best practices
- Start with `qluent trees list` to discover available lenses before evaluating.
- Use the tree hierarchy (`qluent trees get`) to understand what rolls up into what.
- When a contributor has a large share, drill into that subtree to find the root cause.
- Compare multiple trees for a complete picture (e.g., Revenue + Order Volume to separate
  volume effects from basket size effects).
- Use `--json-output` when you need to do further calculations on the raw numbers.
"""


@cli.command()
def instructions() -> None:
    """Print a CLAUDE.md snippet for Claude Code integration."""
    click.echo(_CLAUDE_INSTRUCTIONS)
