"""Natural-language matching helpers for CLI metric tree workflows."""

from __future__ import annotations

import re
from typing import Any

from qluent_cli.dates import infer_windows

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "change",
    "changed",
    "compare",
    "did",
    "do",
    "does",
    "driver",
    "drivers",
    "during",
    "explain",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "kpi",
    "last",
    "me",
    "metric",
    "metrics",
    "month",
    "of",
    "on",
    "over",
    "performance",
    "period",
    "please",
    "quarter",
    "rca",
    "root",
    "show",
    "that",
    "the",
    "their",
    "this",
    "to",
    "today",
    "tree",
    "vs",
    "week",
    "what",
    "when",
    "why",
    "with",
    "without",
    "yesterday",
}


def _normalize_text(value: str) -> str:
    cleaned = _NON_ALNUM_RE.sub(" ", value.lower()).strip()
    return " ".join(cleaned.split())


def _normalize_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(value: str) -> list[str]:
    return [_normalize_token(token) for token in _TOKEN_RE.findall(value.lower())]


def _significant_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for token in _tokens(value):
        if len(token) <= 1 or token.isdigit() or token in _STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _phrase_in_question(question_text: str, phrase: str) -> bool:
    if not phrase:
        return False
    return re.search(rf"\b{re.escape(phrase)}\b", question_text) is not None


def _collect_tree_tokens(tree: dict[str, Any]) -> dict[str, set[str]]:
    dimensions = tree.get("dimensions") or []
    nodes = tree.get("nodes") or []
    description = tree.get("description") or ""

    node_labels = " ".join(
        str(node.get("label") or "")
        for node in nodes
        if isinstance(node, dict)
    )
    dimension_text = " ".join(str(value) for value in dimensions)

    return {
        "id": set(_significant_tokens(str(tree.get("id") or ""))),
        "label": set(_significant_tokens(str(tree.get("label") or ""))),
        "description": set(_significant_tokens(description)),
        "dimensions": set(_significant_tokens(dimension_text)),
        "nodes": set(_significant_tokens(node_labels)),
    }


def _score_tree(
    question_text: str,
    question_tokens: set[str],
    tree: dict[str, Any],
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    tree_id = str(tree.get("id") or "")
    tree_label = str(tree.get("label") or tree_id)
    id_phrase = _normalize_text(tree_id.replace("_", " ").replace("-", " "))
    label_phrase = _normalize_text(tree_label)

    if _phrase_in_question(question_text, id_phrase):
        score += 8
        reasons.append(f"exact id phrase '{tree_id}'")

    if label_phrase != id_phrase and _phrase_in_question(question_text, label_phrase):
        score += 8
        reasons.append(f"exact label phrase '{tree_label}'")

    tree_tokens = _collect_tree_tokens(tree)

    id_overlap = sorted(question_tokens & tree_tokens["id"])
    if id_overlap:
        score += 4 * len(id_overlap)
        reasons.append("id tokens: " + ", ".join(id_overlap))

    label_overlap = sorted(question_tokens & tree_tokens["label"])
    if label_overlap:
        score += 3 * len(label_overlap)
        reasons.append("label tokens: " + ", ".join(label_overlap))

    description_overlap = sorted(question_tokens & tree_tokens["description"])
    if description_overlap:
        score += min(2, len(description_overlap))
        reasons.append("description tokens: " + ", ".join(description_overlap))

    dimension_overlap = sorted(question_tokens & tree_tokens["dimensions"])
    if dimension_overlap:
        score += min(2, len(dimension_overlap))
        reasons.append("dimension tokens: " + ", ".join(dimension_overlap))

    node_overlap = sorted(question_tokens & tree_tokens["nodes"])
    if node_overlap:
        score += min(3, len(node_overlap))
        reasons.append("node tokens: " + ", ".join(node_overlap))

    return score, reasons


def match_tree_question(question: str, tree_collection: dict[str, Any]) -> dict[str, Any]:
    """Match a natural-language question to the best available metric tree."""
    trees = tree_collection.get("trees") or []
    question_text = _normalize_text(question)
    question_tokens = set(_significant_tokens(question))
    windows = infer_windows(question)

    candidates: list[dict[str, Any]] = []
    for tree in trees:
        if not isinstance(tree, dict):
            continue
        score, reasons = _score_tree(question_text, question_tokens, tree)
        candidates.append(
            {
                "tree_id": tree.get("id"),
                "tree_label": tree.get("label") or tree.get("id"),
                "score": score,
                "reasons": reasons,
            }
        )

    candidates.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            str(item.get("tree_label") or ""),
            str(item.get("tree_id") or ""),
        )
    )

    result = {
        "question": question,
        "decision": "no_trees",
        "matched": False,
        "tree_id": None,
        "tree_label": None,
        "score": 0,
        "reasons": [],
        "current_window": {
            "date_from": str(windows.current.date_from),
            "date_to": str(windows.current.date_to),
        },
        "comparison_window": {
            "date_from": str(windows.comparison.date_from),
            "date_to": str(windows.comparison.date_to),
        },
        "top_candidates": candidates[:3],
    }

    if not candidates:
        return result

    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    best_score = int(best.get("score") or 0)
    second_score = int(second.get("score") or 0) if second else 0

    if best_score <= 0:
        result["decision"] = "no_match"
        return result

    ambiguous = second is not None and (
        best_score == second_score
        or (best_score < 6 and best_score - second_score <= 1 and second_score > 0)
    )
    if ambiguous:
        result["decision"] = "ambiguous"
        return result

    result.update(
        {
            "decision": "matched",
            "matched": True,
            "tree_id": best.get("tree_id"),
            "tree_label": best.get("tree_label"),
            "score": best_score,
            "reasons": best.get("reasons", []),
        }
    )
    return result
