"""Portfolio-optimization MCP server package.

Wraps the `po` C++ CLI from the `rtrimble13/po` project (mean-variance,
Black-Litterman, efficient frontier, target-vol/return, min-variance,
max-Sharpe, Jupyter report) and supplements it with a thin lazy-loaded
binding to the `portopt` Python library for HRP, equal-risk-contribution
(risk parity), inverse-var/vol, equal-weight, max-diversification,
walk-forward backtesting, Brinson attribution, and arbitrary-weights
portfolio summarisation.

Designed for CFA-style portfolio construction and risk-analysis workflows:
constraint-aware optimisation, view-based BL, frontier exploration,
backtests with transaction costs, and benchmark-relative attribution.
"""

__version__ = "0.1.0"
