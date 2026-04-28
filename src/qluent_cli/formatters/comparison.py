"""Formatter for side-by-side multi-tree comparisons."""

from __future__ import annotations

import re
from typing import Any

from qluent_cli.formatters._common import fmt_pct


def format_comparison(tree_results: list[tuple[str, dict]], period_label: str) -> str:
    """Format side-by-side comparison of multiple trees for the same period.

    Matches nodes by structural path and only shows a value when the labels line
    up at that path. This avoids silently comparing unrelated nodes.
    """
    if not tree_results:
        return "No data."

    tree_labels = [label for label, _ in tree_results]
    header = " vs ".join(tree_labels) + f" — {period_label}"

    def normalize_label(label: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", label.lower())

    def enumerate_paths(data: dict[str, Any]) -> list[tuple[tuple[int, ...], str, dict[str, Any]]]:
        nodes = data.get("nodes", [])
        if not nodes:
            return []
        nodes_by_id = {node["id"]: node for node in nodes}
        root_id = data.get("root_node_id") or nodes[0]["id"]
        rows: list[tuple[tuple[int, ...], str, dict[str, Any]]] = []

        def walk(node_id: str, path: tuple[int, ...]) -> None:
            node = nodes_by_id.get(node_id)
            if not node:
                return
            rows.append((path, node["label"], node))
            for index, child_id in enumerate(node.get("children", [])):
                walk(child_id, (*path, index))

        walk(root_id, ())
        return rows

    base_paths = enumerate_paths(tree_results[0][1])
    tree_path_maps = []
    for _, data in tree_results:
        tree_path_maps.append({
            path: node
            for path, _label, node in enumerate_paths(data)
        })

    row_labels = [label for _path, label, _node in base_paths]

    max_label_len = max(len(la) for la in row_labels) if row_labels else 0
    col_width = max(len(la) for la in tree_labels) + 2
    col_width = max(col_width, 9)

    lines = [header, ""]
    col_header = " " * (max_label_len + 4) + "".join(la.rjust(col_width) for la in tree_labels)
    lines.append(col_header)

    for path, label, _base_node in base_paths:
        padded = label.ljust(max_label_len)
        cells = ""
        base_label_key = normalize_label(label)
        for path_map in tree_path_maps:
            candidate = path_map.get(path)
            if candidate is None:
                cells += "—".rjust(col_width)
                continue

            candidate_label_key = normalize_label(candidate["label"])
            if path and candidate_label_key != base_label_key:
                cells += "—".rjust(col_width)
                continue

            ratio = candidate.get("delta_ratio")
            cells += fmt_pct(ratio).rjust(col_width) if ratio is not None else "—".rjust(col_width)
        lines.append(f"    {padded}{cells}")

    return "\n".join(lines)
