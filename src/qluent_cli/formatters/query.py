"""Formatter for ad-hoc natural-language query results."""

from __future__ import annotations

from typing import Any

from qluent_cli.query_contracts import QueryContract


_MAX_TABLE_ROWS = 20
_MAX_CELL_WIDTH = 40


def _fmt_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    elif isinstance(value, int) and not isinstance(value, bool):
        text = f"{value:,}"
    else:
        text = str(value)
    if len(text) > _MAX_CELL_WIDTH:
        text = text[: _MAX_CELL_WIDTH - 1] + "…"
    return text


def _format_table(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    cells = [[_fmt_cell(row.get(col)) for col in columns] for row in rows]
    widths = [
        max(len(col), *(len(r[i]) for r in cells)) if cells else len(col)
        for i, col in enumerate(columns)
    ]
    lines = ["  " + "  ".join(col.ljust(widths[i]) for i, col in enumerate(columns))]
    for row in cells:
        lines.append("  " + "  ".join(v.ljust(widths[i]) for i, v in enumerate(row)))
    return lines


def format_query_result(
    contract: QueryContract, *, show_sql: bool = True, max_rows: int = _MAX_TABLE_ROWS
) -> str:
    """Human-readable rendering of a successful query contract."""
    lines: list[str] = []

    answer = contract.get("answer")
    if answer:
        lines.append(str(answer).strip())

    columns = contract.get("columns") or []
    data = contract.get("data") or []
    row_count = contract.get("row_count")
    total = row_count if isinstance(row_count, int) else len(data)

    if columns and data:
        if lines:
            lines.append("")
        lines.extend(_format_table(list(columns), data[:max_rows]))
        if total > min(len(data), max_rows):
            shown = min(len(data), max_rows)
            lines.append(
                f"  (showing {shown} of {total:,} rows — full data:"
                " --json-output or the download link)"
            )

    sql = contract.get("sql")
    if sql and show_sql:
        lines.append("")
        lines.append(f"SQL: {sql}")

    footer: list[str] = []
    if total:
        footer.append(f"Rows: {total:,}")
    if contract.get("download_url"):
        footer.append(f"Download: {contract['download_url']}")
    if contract.get("google_sheets_url"):
        footer.append(f"Sheets: {contract['google_sheets_url']}")
    if footer:
        lines.append("")
        lines.append("   ".join(footer))

    thread_id = contract.get("thread_id")
    if thread_id:
        lines.append(f"Thread: {thread_id} — follow up with:")
        lines.append(f'  qluent query "<follow-up question>" --thread {thread_id}')

    return "\n".join(lines) if lines else "No answer returned."


def format_query_clarification(contract: QueryContract) -> str:
    """Human-readable rendering of a clarification request."""
    clarification = contract.get("clarification") or {}
    lines = ["Clarification needed:"]
    message = clarification.get("message") or contract.get("answer")
    if message:
        lines.append(f"  {message}")
    for i, option in enumerate(clarification.get("options") or [], start=1):
        lines.append(f"    {i}. {option}")

    thread_id = contract.get("thread_id")
    if thread_id:
        lines.append("")
        lines.append("Answer with:")
        lines.append(f'  qluent query "<your answer>" --thread {thread_id}')
    return "\n".join(lines)
