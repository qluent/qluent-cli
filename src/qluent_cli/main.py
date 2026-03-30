"""Qluent CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click

from qluent_cli.rca import rca
from qluent_cli.trees import trees


@click.group()
def cli() -> None:
    """Qluent — metric tree analysis from the command line."""


def _print_saved_config(data: dict[str, object]) -> None:
    from qluent_cli.config import mask_key

    hidden = {"client_safe", "bearer_token"}
    for key, value in data.items():
        if key in hidden:
            continue
        click.echo(f"  {key}: {mask_key(value) if key == 'api_key' else value}")


def _prompt_required(
    label: str,
    *,
    default: str | None = None,
    show_default: bool = True,
) -> str:
    while True:
        value = click.prompt(
            label,
            default=default or "",
            show_default=show_default and bool(default),
        ).strip()
        if value:
            return value
        click.echo(f"{label} is required")


@cli.command()
@click.option("--api-key", help="API key (qk_...)")
@click.option("--url", help="API base URL")
@click.option(
    "--local",
    is_flag=True,
    help="Use the local API at http://localhost:8001.",
)
@click.option("--project", help="Project UUID")
@click.option("--email", help="User email")
@click.option(
    "--client-safe/--no-client-safe",
    default=None,
    help="Redact tree formulas and SQL contract details for client-facing use.",
)
@click.option(
    "--bearer-token",
    hidden=True,
    help="Deprecated legacy option. The metric-tree API uses X-API-Key auth.",
)
def config(
    api_key: str | None,
    url: str | None,
    local: bool,
    project: str | None,
    email: str | None,
    client_safe: bool | None,
    bearer_token: str | None,
) -> None:
    """Configure Qluent API credentials."""
    from qluent_cli.config import (
        CONFIG_FILE,
        CONFIG_SAVED_MSG,
        DEFAULT_API_URL,
        LOCAL_API_URL,
        default_client_safe,
        load_raw_config,
        save_config,
    )

    if url and local:
        raise click.ClickException("Use either --url or --local, not both.")
    if bearer_token:
        raise click.ClickException(
            "Bearer-token auth is not supported by the metric-tree API. Configure an API key instead."
        )

    effective_url = LOCAL_API_URL if local else url

    if not any([api_key, effective_url, project, email, client_safe is not None]):
        if CONFIG_FILE.exists():
            data = load_raw_config()
            if "client_safe" not in data:
                data["client_safe"] = default_client_safe(
                    str(data.get("api_url") or DEFAULT_API_URL)
                )
            _print_saved_config(data)
        else:
            click.echo("No config file found. Run: qluent setup")
        return

    result = save_config(
        api_key=api_key,
        api_url=effective_url,
        project_uuid=project,
        user_email=email,
        client_safe=client_safe,
    )
    if "client_safe" not in result:
        result["client_safe"] = default_client_safe(
            str(result.get("api_url") or DEFAULT_API_URL)
        )
    click.echo(CONFIG_SAVED_MSG)
    _print_saved_config(result)


def _write_claude_file(path: Path, *, force: bool) -> str:
    content = _CLAUDE_INSTRUCTIONS.strip() + "\n"
    if path.exists():
        existing = path.read_text()
        if existing == content:
            return f"{path} is already up to date"
        if not force:
            raise click.ClickException(f"{path} already exists. Re-run with --force to overwrite it.")
    path.write_text(content)
    return f"Wrote {path}"


@cli.command()
@click.option(
    "--local",
    is_flag=True,
    help="Use the local API at http://localhost:8001 and local UI at http://localhost:5173.",
)
def login(local: bool) -> None:
    """Log in via browser (opens qluent-ui for SSO authentication)."""
    from qluent_cli.auth import browser_login
    from qluent_cli.config import (
        CONFIG_SAVED_MSG,
        DEFAULT_API_URL,
        LOCAL_API_URL,
        default_client_safe,
        mask_key,
        save_config,
    )

    api_url = LOCAL_API_URL if local else DEFAULT_API_URL

    result = browser_login(api_url)

    if not result.success:
        raise click.ClickException(f"Login failed: {result.error}")

    client_safe = default_client_safe(api_url)
    save_config(
        api_key=result.api_key,
        api_url=api_url,
        project_uuid=result.project_uuid,
        user_email=result.user_email,
        client_safe=client_safe,
    )

    click.echo("Logged in successfully!")
    click.echo(f"  Project: {result.project_uuid}")
    click.echo(f"  Email:   {result.user_email}")
    click.echo(CONFIG_SAVED_MSG)


@cli.command()
@click.option(
    "--claude-path",
    default="CLAUDE.md",
    show_default=True,
    help="Where to write the Claude Code instructions file.",
)
@click.option(
    "--local",
    is_flag=True,
    help="Use the local API at http://localhost:8001.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing CLAUDE.md without prompting.")
def setup(claude_path: str, local: bool, force: bool) -> None:
    """Interactive first-run setup for client installations."""
    click.echo("Tip: Use 'qluent login' for browser-based login (recommended).\n")

    from qluent_cli.config import (
        CONFIG_SAVED_MSG,
        DEFAULT_API_URL,
        LOCAL_API_URL,
        default_client_safe,
        load_raw_config,
        save_config,
    )

    existing = load_raw_config()

    api_key = _prompt_required(
        "API key",
        default=str(existing.get("api_key") or ""),
        show_default=False,
    )
    project_uuid = _prompt_required(
        "Project UUID",
        default=str(existing.get("project_uuid") or ""),
        show_default=False,
    )
    user_email = _prompt_required(
        "User email",
        default=str(existing.get("user_email") or ""),
        show_default=False,
    )
    api_url = LOCAL_API_URL if local else str(existing.get("api_url") or DEFAULT_API_URL)
    client_safe = default_client_safe(api_url)

    result = save_config(
        api_key=api_key,
        api_url=api_url,
        project_uuid=project_uuid,
        user_email=user_email,
        client_safe=client_safe,
    )
    click.echo(CONFIG_SAVED_MSG)
    _print_saved_config(result)

    target = Path(claude_path)
    write_claude = click.confirm(
        f"Write Claude Code instructions to {target}?",
        default=True,
    )
    if not write_claude:
        click.echo("Skipped CLAUDE.md generation")
        return

    should_force = force
    if target.exists() and not force:
        should_force = click.confirm(
            f"{target} already exists. Overwrite it?",
            default=False,
        )
        if not should_force:
            click.echo("Skipped CLAUDE.md generation")
            return

    click.echo(_write_claude_file(target, force=should_force))


cli.add_command(trees)
cli.add_command(rca)


_CLAUDE_INSTRUCTIONS = """\
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

When Claude Code is asked to investigate KPI movement, prefer the bundled investigation command
with `--json-output` as the first step:

```bash
qluent trees investigate --question "Why did revenue drop last week?" --json-output
```

If the user already named the tree, use:

```bash
qluent trees investigate revenue --current YYYY-MM-DD:YYYY-MM-DD --compare YYYY-MM-DD:YYYY-MM-DD --json-output
```

Read the investigation bundle in this order:

1. `agent.status`
2. `agent.top_findings`
3. `agent.gaps`
4. `agent.recommended_next_steps`
5. `root_cause`, `evaluation`, and `trend` details for evidence

Use these rules:

- Prefer `investigate --question` over manually chaining `match`, `trend`, `evaluate`, and `rca analyze`.
- Prefer `--json-output` when Claude Code is driving the workflow.
- If `agent.status = needs_tree_selection`, inspect `match.top_candidates` and either pick the strongest tree or ask the user.
- If `agent.status = needs_more_data` or `partially_resolved`, run the first relevant command from `agent.recommended_next_steps` before inventing your own drill-down.
- If `agent.status = resolved`, summarize the evidence and stop unless the user explicitly wants a deeper drill-down.
- Always report the exact current and comparison windows you used.
- Treat `agent.top_findings` as the fastest summary, then verify against `root_cause.conclusion.takeaways` and supporting evidence.

## Manual root cause analysis workflow

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


@cli.group()
def claude() -> None:
    """Claude Code integration helpers."""


@claude.command("init")
@click.option("--path", "target_path", default="CLAUDE.md", show_default=True, help="Path to write CLAUDE.md")
@click.option("--force", is_flag=True, help="Overwrite an existing CLAUDE.md")
def claude_init(target_path: str, force: bool) -> None:
    """Write a CLAUDE.md file for Claude Code."""
    click.echo(_write_claude_file(Path(target_path), force=force))


cli.add_command(claude)
