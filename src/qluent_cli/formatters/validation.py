"""Formatter for tree-contract validation results."""

from __future__ import annotations

from typing import Any


def format_tree_validation(data: dict[str, Any]) -> str:
    """Format metric tree contract validation results."""
    status = "valid" if data.get("valid") else "invalid"
    lines = [
        f"{data['tree_label']} Validation",
        "",
        f"  Status: {status}",
    ]
    if data.get("redacted"):
        lines.append(
            f"  {data.get('redaction_reason') or 'Client-safe mode redacted SQL contract details.'}"
        )

    declared_dimensions = data.get("dimensions_declared", [])
    supported_dimensions = data.get("supported_dimensions", [])
    if declared_dimensions:
        lines.append(f"  Declared dimensions: {', '.join(declared_dimensions)}")
        lines.append(
            "  Supported dimensions: "
            + (", ".join(supported_dimensions) if supported_dimensions else "none")
        )

    leaf_nodes = data.get("leaf_nodes", [])
    if leaf_nodes:
        lines.append("")
        lines.append("  Leaf nodes:")
        for leaf in leaf_nodes:
            summary = f"    {leaf['label']} ({leaf['node_id']})"
            if leaf.get("metric_id") is not None:
                summary += f" [metric {leaf.get('metric_id')}]"
            summary += f" [{leaf.get('projection_status', 'explicit')}]"
            lines.append(summary)
            projected_columns = leaf.get("projected_columns", [])
            if projected_columns:
                lines.append(f"      columns: {', '.join(projected_columns)}")
            if leaf.get("missing_columns"):
                lines.append(f"      missing columns: {', '.join(leaf['missing_columns'])}")
            if leaf.get("missing_dimensions"):
                lines.append(f"      missing dimensions: {', '.join(leaf['missing_dimensions'])}")

    errors = data.get("errors", [])
    if errors:
        lines.append("")
        lines.append("  Errors:")
        for error in errors:
            lines.append(f"    ! {error}")

    warnings = data.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("  Warnings:")
        for warning in warnings:
            lines.append(f"    ! {warning}")

    return "\n".join(lines)
