from __future__ import annotations

from click.testing import CliRunner

from qluent_cli.config import QluentConfig
from qluent_cli.formatters import format_comparison, format_evaluation
from qluent_cli.main import cli


def test_rca_analyze_formats_root_cause_output(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.rca.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    def mock_root_cause_tree(
        self,
        tree_id,
        current_from,
        current_to,
        comparison_from,
        comparison_to,
        *,
        segment_by,
        filters,
        max_depth,
        max_branching,
        max_segments,
        min_contribution_share,
    ):
        assert tree_id == "revenue"
        assert current_from == "2026-03-09"
        assert comparison_from == "2026-03-02"
        assert segment_by == ["channel"]
        assert filters == {"country": ["SE"]}
        assert max_depth == 2
        assert max_branching == 1
        assert max_segments == 3
        assert min_contribution_share == 0.2
        return {
            "tree_label": "Revenue",
            "tree_id": "revenue",
            "root_node_id": "revenue",
            "current_window": {"date_from": "2026-03-09", "date_to": "2026-03-15"},
            "comparison_window": {"date_from": "2026-03-02", "date_to": "2026-03-08"},
            "current_value": 900,
            "comparison_value": 1000,
            "delta_value": -100,
            "delta_ratio": -0.1,
            "dimensions_considered": ["channel"],
            "time_slice_grain": "day",
            "time_slices": [
                {
                    "current_window": {"date_from": "2026-03-15", "date_to": "2026-03-15"},
                    "comparison_window": {"date_from": "2026-03-08", "date_to": "2026-03-08"},
                    "current_value": 200,
                    "comparison_value": 260,
                    "delta_value": -60,
                    "delta_ratio": -0.2307692308,
                    "share_of_change": 0.6,
                    "top_contributors": [
                        {"node_id": "orders", "label": "Orders", "delta_value": -60, "delta_share": 1.0}
                    ],
                }
            ],
            "mix_shift": {
                "dimension": "channel",
                "segments": [
                    {
                        "segment": "Organic",
                        "current_value": 600,
                        "comparison_value": 800,
                        "delta_value": -200,
                        "current_share": 0.6666666667,
                        "comparison_share": 0.8,
                        "share_delta": -0.1333333333,
                        "baseline_effect": -80,
                        "mix_effect": -120,
                    },
                    {
                        "segment": "Paid",
                        "current_value": 300,
                        "comparison_value": 200,
                        "delta_value": 100,
                        "current_share": 0.3333333333,
                        "comparison_share": 0.2,
                        "share_delta": 0.1333333333,
                        "baseline_effect": -20,
                        "mix_effect": 120,
                    },
                ],
            },
            "conclusion": {
                "confidence": "high",
                "confidence_score": 0.9,
                "confidence_type": "evidence_coverage_heuristic",
                "confidence_description": (
                    "Not probabilistic. Higher scores mean broader deterministic evidence "
                    "coverage, adjusted down for warnings and unresolved branches."
                ),
                "evidence_types_present": [
                    "driver",
                    "time_slice",
                    "segment",
                    "mix_shift",
                    "mechanism",
                ],
                "evidence_types_missing": [],
                "confidence_factors": [
                    "Direct driver evidence is available.",
                    "Time-slice evidence is available.",
                    "Segment-level evidence is available.",
                    "Formula mechanism evidence is available.",
                    "Multiple ranked takeaways support the result.",
                    "No execution warnings were raised.",
                ],
                "takeaways": [
                    {
                        "kind": "segment",
                        "title": "Revenue: channel=Organic",
                        "summary": "Revenue is concentrated in channel=Organic: Δ -200 (+200.0% of root change)",
                        "score": 2.0,
                        "node_id": "revenue",
                        "path": ["revenue"],
                        "delta_value": -200,
                        "effect_value": None,
                        "share_of_change": 2.0,
                        "dimension": "channel",
                        "segment": "Organic",
                        "current_window": None,
                        "comparison_window": None,
                    },
                    {
                        "kind": "mechanism",
                        "title": "Revenue: AOV effect",
                        "summary": "Revenue mechanism is led by AOV effect -250",
                        "score": 2.5,
                        "node_id": "revenue",
                        "path": ["revenue"],
                        "delta_value": None,
                        "effect_value": -250,
                        "share_of_change": 2.5,
                        "dimension": None,
                        "segment": None,
                        "current_window": None,
                        "comparison_window": None,
                    },
                ],
                "unresolved_nodes": [],
            },
            "findings": [
                {
                    "node_id": "revenue",
                    "label": "Revenue",
                    "depth": 0,
                    "path": ["revenue"],
                    "current_value": 900,
                    "comparison_value": 1000,
                    "delta_value": -100,
                    "delta_ratio": -0.1,
                    "contribution_value": None,
                    "contribution_share": None,
                    "direct_contributors": [
                        {"node_id": "orders", "label": "Orders", "delta_value": -100, "delta_share": 1.0}
                    ],
                    "formula_analysis": {
                        "formula": "orders * aov",
                        "method": "two_factor_product",
                        "effects": [
                            {
                                "kind": "child",
                                "label": "Orders effect",
                                "node_id": "orders",
                                "current_value": 120,
                                "comparison_value": 100,
                                "delta_value": 20,
                                "effect_value": 200,
                                "effect_share": -2.0,
                            },
                            {
                                "kind": "child",
                                "label": "AOV effect",
                                "node_id": "aov",
                                "current_value": 7.5,
                                "comparison_value": 10,
                                "delta_value": -2.5,
                                "effect_value": -250,
                                "effect_share": 2.5,
                            },
                            {
                                "kind": "interaction",
                                "label": "Interaction effect",
                                "node_id": None,
                                "current_value": None,
                                "comparison_value": None,
                                "delta_value": None,
                                "effect_value": -50,
                                "effect_share": 0.5,
                            },
                        ],
                    },
                    "segment_dimension": "channel",
                    "segment_findings": [
                        {
                            "dimension": "channel",
                            "segment": "Organic",
                            "current_value": 600,
                            "comparison_value": 800,
                            "delta_value": -200,
                            "delta_ratio": -0.25,
                            "share_of_change": 2.0,
                        }
                    ],
                    "filters": {"country": ["SE"]},
                    "status": "branch",
                }
            ],
            "warnings": [],
        }

    monkeypatch.setattr("qluent_cli.rca.QluentClient.root_cause_tree", mock_root_cause_tree)

    result = CliRunner().invoke(
        cli,
        [
            "rca",
            "analyze",
            "revenue",
            "--current",
            "2026-03-09:2026-03-15",
            "--compare",
            "2026-03-02:2026-03-08",
            "--segment-by",
            "channel",
            "--filter",
            "country=SE",
            "--max-depth",
            "2",
            "--max-branches",
            "1",
            "--max-segments",
            "3",
            "--min-contribution-share",
            "0.2",
        ],
    )

    assert result.exit_code == 0
    assert "Revenue RCA" in result.output
    assert "Evidence confidence: high (coverage score 90%)" in result.output
    assert "Not probabilistic." in result.output
    assert "Evidence present: driver, time_slice, segment, mix_shift, mechanism" in result.output
    assert "Top takeaways:" in result.output
    assert "1. Revenue is concentrated in channel=Organic: Δ -200 (+200.0% of root change)" in result.output
    assert "Largest time slices (day):" in result.output
    assert "Mar 15 vs Mar 8: Δ -60 (-23.1%) | 60% of change" in result.output
    assert "Mix shift (channel):" in result.output
    assert "Organic: Δ -200 | share 80% → 67% (-13pp) | baseline -80 | mix -120" in result.output
    assert "mechanism: Orders effect +200, AOV effect -250, Interaction effect -50" in result.output
    assert "best segment cut: channel -> Organic -200 (200%)" in result.output
    assert "Evidence factors:" in result.output


def test_rca_analyze_rejects_invalid_filter(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.rca.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    result = CliRunner().invoke(cli, ["rca", "analyze", "revenue", "--filter", "country"])

    assert result.exit_code != 0
    assert "Invalid filter" in result.output


def test_format_evaluation_preserves_negative_values():
    output = format_evaluation(
        {
            "tree_label": "Margin",
            "current_window": {"date_from": "2026-03-10", "date_to": "2026-03-16"},
            "comparison_window": {"date_from": "2026-03-03", "date_to": "2026-03-09"},
            "current_value": -5.2,
            "comparison_value": -1.1,
            "delta_value": -4.1,
            "delta_ratio": 3.7272727,
            "nodes": [
                {
                    "label": "Margin",
                    "comparison_value": -1.1,
                    "current_value": -5.2,
                    "delta_value": -4.1,
                    "delta_ratio": 3.7272727,
                    "sensitivity": 1.0,
                    "elasticity": 1.0,
                }
            ],
            "top_contributors": [],
            "warnings": [],
        }
    )

    assert "-1" in output
    assert "→           -5" in output


def test_format_comparison_hides_unrelated_nodes():
    output = format_comparison(
        [
            (
                "Revenue",
                {
                    "root_node_id": "revenue",
                    "nodes": [
                        {"id": "revenue", "label": "Revenue", "children": ["orders", "aov"], "delta_ratio": 0.1},
                        {"id": "orders", "label": "Orders", "children": [], "delta_ratio": 0.2},
                        {"id": "aov", "label": "AOV", "children": [], "delta_ratio": -0.1},
                    ],
                },
            ),
            (
                "Spend",
                {
                    "root_node_id": "spend",
                    "nodes": [
                        {"id": "spend", "label": "Spend", "children": ["brand", "non_brand"], "delta_ratio": -0.05},
                        {"id": "brand", "label": "Brand", "children": [], "delta_ratio": 0.3},
                        {"id": "non_brand", "label": "Non-brand", "children": [], "delta_ratio": -0.2},
                    ],
                },
            ),
        ],
        "test",
    )

    assert "Revenue   +10.0%    -5.0%" in output
    assert "Orders    +20.0%        —" in output
    assert "AOV       -10.0%        —" in output
