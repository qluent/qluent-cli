"""Human-readable output formatting for metric tree results.

Public surface re-exported here so consumers (`trees.py`, `rca.py`,
`elasticity.py`, `mcp_server.py`, `main.py`) import from
`qluent_cli.formatters` regardless of which submodule the formatter lives in.
"""

from qluent_cli.formatters._common import format_period_label
from qluent_cli.formatters.comparison import format_comparison
from qluent_cli.formatters.elasticity import format_elasticity
from qluent_cli.formatters.evaluation import format_evaluation, format_levers
from qluent_cli.formatters.investigation import format_investigation
from qluent_cli.formatters.rca import format_root_cause
from qluent_cli.formatters.trees import format_tree_detail, format_tree_list
from qluent_cli.formatters.trend import format_trend
from qluent_cli.formatters.validation import format_tree_validation

__all__ = [
    "format_comparison",
    "format_elasticity",
    "format_evaluation",
    "format_investigation",
    "format_levers",
    "format_period_label",
    "format_root_cause",
    "format_tree_detail",
    "format_tree_list",
    "format_tree_validation",
    "format_trend",
]
