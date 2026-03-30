"""Tests for natural-language tree matching helpers."""

from qluent_cli.matching import find_related_trees


def test_find_related_trees_ranks_by_similarity():
    tree_collection = {
        "trees": [
            {
                "id": "revenue",
                "label": "Revenue",
                "description": "Total revenue from completed orders",
                "dimensions": ["channel", "country"],
                "nodes": [
                    {"id": "revenue", "label": "Revenue", "kind": "formula"},
                    {"id": "orders_rev", "label": "Orders Revenue", "kind": "sql_metric"},
                ],
            },
            {
                "id": "net_revenue",
                "label": "Net Revenue",
                "description": "Revenue after refunds and discounts",
                "dimensions": ["channel", "country"],
                "nodes": [
                    {"id": "net_revenue", "label": "Net Revenue", "kind": "formula"},
                ],
            },
            {
                "id": "order_volume",
                "label": "Order Volume",
                "description": "Total completed orders",
                "dimensions": ["channel", "country"],
                "nodes": [
                    {"id": "order_volume", "label": "Order Volume", "kind": "formula"},
                ],
            },
            {
                "id": "churn_rate",
                "label": "Churn Rate",
                "description": "Monthly customer churn percentage",
                "dimensions": ["segment"],
                "nodes": [
                    {"id": "churn_rate", "label": "Churn Rate", "kind": "sql_metric"},
                ],
            },
        ]
    }

    source = tree_collection["trees"][0]
    related = find_related_trees(source, tree_collection)

    ids = [r["tree_id"] for r in related]
    assert "revenue" not in ids
    assert "net_revenue" in ids
    assert "order_volume" in ids
    # Both share strong token overlap; churn_rate shares little
    assert ids.index("order_volume") < ids.index("churn_rate") if "churn_rate" in ids else True
    for r in related:
        assert r["score"] > 0
        assert r["why"].startswith("Related")


def test_find_related_trees_excludes_specified_ids():
    tree_collection = {
        "trees": [
            {
                "id": "revenue",
                "label": "Revenue",
                "description": "Total revenue",
                "dimensions": ["channel"],
                "nodes": [],
            },
            {
                "id": "net_revenue",
                "label": "Net Revenue",
                "description": "Revenue after refunds",
                "dimensions": ["channel"],
                "nodes": [],
            },
            {
                "id": "order_volume",
                "label": "Order Volume",
                "description": "Completed orders",
                "dimensions": ["channel"],
                "nodes": [],
            },
        ]
    }

    source = tree_collection["trees"][0]
    related = find_related_trees(
        source,
        tree_collection,
        exclude_ids={"revenue", "net_revenue"},
    )

    ids = [r["tree_id"] for r in related]
    assert "net_revenue" not in ids
    assert "revenue" not in ids


def test_find_related_trees_returns_empty_for_no_matches():
    tree_collection = {"trees": [{"id": "revenue", "label": "Revenue", "dimensions": [], "nodes": []}]}
    source = tree_collection["trees"][0]
    assert find_related_trees(source, tree_collection) == []


def test_find_related_trees_respects_max_results():
    tree_collection = {
        "trees": [
            {"id": "a", "label": "Revenue A", "description": "Revenue metric", "dimensions": ["channel"], "nodes": []},
            {"id": "b", "label": "Revenue B", "description": "Revenue metric", "dimensions": ["channel"], "nodes": []},
            {"id": "c", "label": "Revenue C", "description": "Revenue metric", "dimensions": ["channel"], "nodes": []},
            {"id": "d", "label": "Revenue D", "description": "Revenue metric", "dimensions": ["channel"], "nodes": []},
        ]
    }

    source = tree_collection["trees"][0]
    related = find_related_trees(source, tree_collection, max_results=2)
    assert len(related) <= 2
