"""Lazy-loaded :mod:`portopt` Python-library wrappers.

The `po` CLI covers MVO, frontier, BL, BL-frontier, min-variance,
max-Sharpe, target-vol, target-return, and report. Features only in the
Python library — risk parity (ERC), HRP, inverse-var/vol, equal-weight,
max-diversification, walk-forward backtesting, Brinson attribution,
arbitrary-weights portfolio summarization, and covariance/μ estimation
from raw returns — live here.

Importing :mod:`portopt` is deferred to first call so CLI-only installs
(no pybind11 build) still load the connector. The first failure raises
:class:`POError` with an actionable remediation message.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

from .errors import POError, portopt_not_importable_message

_portopt_mod = None
_numpy_mod = None


def _import_portopt():
    global _portopt_mod
    if _portopt_mod is None:
        try:
            import portopt  # type: ignore[import-not-found]
        except ImportError as exc:
            raise POError(portopt_not_importable_message()) from exc
        _portopt_mod = portopt
    return _portopt_mod


def _import_numpy():
    global _numpy_mod
    if _numpy_mod is None:
        try:
            import numpy as np
        except ImportError as exc:
            raise POError(
                "numpy is required for the portopt-supplement tools. "
                "Install with `pip install numpy`."
            ) from exc
        _numpy_mod = np
    return _numpy_mod


# ---------- closed-form portfolios ---------------------------------------


def equal_risk_contribution(
    tickers: list[str],
    covariance: list[list[float]],
    *,
    tolerance: float = 1e-8,
    max_iters: int = 5000,
) -> dict[str, Any]:
    """Equal Risk Contribution (risk parity). Returns weights and the
    per-asset realized risk contribution.
    """
    po = _import_portopt()
    np = _import_numpy()
    cov = np.asarray(covariance, dtype=float)
    w = np.asarray(
        po.portfolios.equal_risk_contribution(cov, tolerance, max_iters), dtype=float
    )
    return _portfolio_payload(tickers, w, cov)


def hierarchical_risk_parity(
    tickers: list[str], covariance: list[list[float]]
) -> dict[str, Any]:
    """Hierarchical Risk Parity (López de Prado)."""
    po = _import_portopt()
    np = _import_numpy()
    cov = np.asarray(covariance, dtype=float)
    w = np.asarray(po.portfolios.hierarchical_risk_parity(cov), dtype=float)
    return _portfolio_payload(tickers, w, cov)


def inverse_variance(
    tickers: list[str], covariance: list[list[float]]
) -> dict[str, Any]:
    """``w_i ∝ 1/σ_i²``."""
    po = _import_portopt()
    np = _import_numpy()
    cov = np.asarray(covariance, dtype=float)
    w = np.asarray(po.portfolios.inverse_variance(cov), dtype=float)
    return _portfolio_payload(tickers, w, cov)


def inverse_volatility(
    tickers: list[str], covariance: list[list[float]]
) -> dict[str, Any]:
    """``w_i ∝ 1/σ_i``."""
    po = _import_portopt()
    np = _import_numpy()
    cov = np.asarray(covariance, dtype=float)
    w = np.asarray(po.portfolios.inverse_volatility(cov), dtype=float)
    return _portfolio_payload(tickers, w, cov)


def equal_weight(tickers: list[str]) -> dict[str, Any]:
    """``1/N`` portfolio."""
    n = len(tickers)
    if n < 1:
        raise POError("equal_weight requires at least one ticker.")
    w = [1.0 / n] * n
    return {
        "weights": dict(zip(tickers, w)),
        "metrics": {"n_assets": n, "max_position": 1.0 / n},
    }


def max_diversification(
    tickers: list[str], covariance: list[list[float]]
) -> dict[str, Any]:
    """Maximum-diversification (Choueifaty & Coignard)."""
    po = _import_portopt()
    np = _import_numpy()
    cov = np.asarray(covariance, dtype=float)
    w = np.asarray(po.portfolios.maximum_diversification(cov), dtype=float)
    return _portfolio_payload(tickers, w, cov)


# ---------- estimation from returns --------------------------------------


def estimate_from_returns(
    returns_csv_path: Path,
    *,
    periods_per_year: int = 252,
    shrinkage: str = "ledoit-wolf",
    shrinkage_delta: float = 0.2,
) -> dict[str, Any]:
    """Estimate (μ, Σ) from a periodic returns CSV.

    Returns the assets.json-shaped dict the `po` CLI accepts directly:
    ``{"assets": [{"ticker": ...}], "covariance": [[...]],
       "expected_returns": [...]}``.
    """
    po = _import_portopt()
    np = _import_numpy()
    tickers, R = _read_returns_csv(returns_csv_path)
    data = po.estimation.from_returns(
        tickers,
        np.asarray(R, dtype=float),
        periods_per_year=periods_per_year,
        shrinkage=shrinkage,
        shrinkage_delta=shrinkage_delta,
    )
    return po.market_data_to_dict(data)


# ---------- arbitrary-weights portfolio summary --------------------------


def summarize_portfolio(
    weights: dict[str, float],
    covariance: list[list[float]],
    *,
    expected_returns: dict[str, float] | None = None,
    risk_free_rate: float = 0.0,
    benchmark_weights: dict[str, float] | None = None,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Compute portfolio-level metrics (expected return, volatility,
    Sharpe, diversification ratio, effective N, beta-vs-benchmark,
    tracking error, active share, per-asset risk contributions).

    All inputs are aligned by ticker order — ``tickers`` defaults to the
    sorted union of ``weights`` and ``benchmark_weights`` keys.
    """
    np = _import_numpy()
    cov = np.asarray(covariance, dtype=float)
    if tickers is None:
        tickers = sorted(set(weights) | set(benchmark_weights or {}))
    if cov.shape != (len(tickers), len(tickers)):
        raise POError(
            f"covariance shape {cov.shape} does not match {len(tickers)} tickers."
        )
    w = np.array([weights.get(t, 0.0) for t in tickers], dtype=float)
    bw = (
        np.array([benchmark_weights.get(t, 0.0) for t in tickers], dtype=float)
        if benchmark_weights is not None
        else None
    )
    mu = (
        np.array([expected_returns.get(t, 0.0) for t in tickers], dtype=float)
        if expected_returns is not None
        else None
    )

    port_var = float(w @ cov @ w)
    port_vol = math.sqrt(max(port_var, 0.0))
    asset_vols = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    metrics: dict[str, Any] = {
        "n_assets": int((w != 0).sum()),
        "gross_exposure": float(np.abs(w).sum()),
        "net_exposure": float(w.sum()),
        "max_position": float(np.max(np.abs(w))) if len(w) else 0.0,
        "volatility": port_vol,
        "variance": port_var,
    }
    if mu is not None:
        exp_ret = float(mu @ w)
        metrics["expected_return"] = exp_ret
        if port_vol > 0:
            metrics["sharpe_ratio"] = (exp_ret - risk_free_rate) / port_vol
    # Diversification ratio: (w · σ) / σ_port
    weighted_vol = float(np.abs(w) @ asset_vols)
    if port_vol > 0:
        metrics["diversification_ratio"] = weighted_vol / port_vol
    # Effective N = 1 / Σ w_i²
    sumsq = float((w * w).sum())
    if sumsq > 0:
        metrics["effective_n"] = 1.0 / sumsq
    # Risk contributions: w_i · (Σw)_i / σ_port²
    if port_var > 0:
        marginal = cov @ w
        rc = (w * marginal) / port_var
        risk_contributions = {t: float(rc[i]) for i, t in enumerate(tickers)}
    else:
        risk_contributions = {t: 0.0 for t in tickers}
    if bw is not None:
        # Active share = ½ Σ |w_i - b_i|
        metrics["active_share"] = float(np.abs(w - bw).sum() / 2.0)
        # Tracking error (in same units as inputs, i.e. annualized when
        # the covariance is annualized).
        diff = w - bw
        te_var = float(diff @ cov @ diff)
        metrics["tracking_error"] = math.sqrt(max(te_var, 0.0))
        # Beta = w'·Σ·b / (b'·Σ·b)
        bench_var = float(bw @ cov @ bw)
        if bench_var > 0:
            metrics["beta"] = float(w @ cov @ bw) / bench_var
    return {
        "weights": {t: float(w[i]) for i, t in enumerate(tickers)},
        "metrics": metrics,
        "risk_contributions": risk_contributions,
        "top_holdings": _top_n_dict(
            {t: float(w[i]) for i, t in enumerate(tickers)}, n=10
        ),
    }


# ---------- walk-forward backtest ---------------------------------------


def walk_forward_backtest(
    returns_csv_path: Path,
    *,
    strategy: Literal[
        "mvo",
        "min_variance",
        "max_sharpe",
        "risk_parity",
        "hrp",
        "equal_weight",
        "inverse_variance",
        "inverse_volatility",
    ],
    window: int,
    step: int,
    transaction_cost: float = 0.0,
    periods_per_year: int = 252,
    shrinkage: str = "ledoit-wolf",
    risk_aversion: float = 2.5,
    benchmark_returns_csv_path: Path | None = None,
) -> dict[str, Any]:
    """Walk-forward backtest with rolling estimation + periodic rebalance.

    Returns: equity curve, per-rebalance turnover, summary metrics
    (CAGR, Sharpe, Sortino, max drawdown, tracking error vs benchmark
    if supplied, information ratio).
    """
    po = _import_portopt()
    np = _import_numpy()
    tickers, R = _read_returns_csv(returns_csv_path)
    R = np.asarray(R, dtype=float)
    n_periods, n_assets = R.shape
    if window >= n_periods:
        raise POError(
            f"walk_forward window ({window}) must be < n_periods ({n_periods})."
        )

    def build_weights(window_returns):
        # Estimate Σ (and μ when needed) for this window
        data = po.estimation.from_returns(
            tickers,
            np.asarray(window_returns, dtype=float),
            periods_per_year=periods_per_year,
            shrinkage=shrinkage,
        )
        cov = np.array(data.covariance, dtype=float)
        if strategy == "min_variance":
            params = po.MVOParameters()
            params.risk_aversion = 1e6  # heavy risk aversion ⇒ min var
            params.constraints = po.PortfolioConstraints.long_only(n_assets)
            res = po.MVOptimizer(params).optimize(data)
            return np.array(res.weights, dtype=float)
        if strategy == "max_sharpe":
            params = po.MVOParameters()
            params.risk_aversion = risk_aversion
            params.constraints = po.PortfolioConstraints.long_only(n_assets)
            res = po.MVOptimizer(params).max_sharpe_portfolio(data)
            return np.array(res.weights, dtype=float)
        if strategy == "mvo":
            params = po.MVOParameters()
            params.risk_aversion = risk_aversion
            params.constraints = po.PortfolioConstraints.long_only(n_assets)
            res = po.MVOptimizer(params).optimize(data)
            return np.array(res.weights, dtype=float)
        if strategy == "risk_parity":
            return np.array(po.portfolios.equal_risk_contribution(cov), dtype=float)
        if strategy == "hrp":
            return np.array(po.portfolios.hierarchical_risk_parity(cov), dtype=float)
        if strategy == "equal_weight":
            return np.full(n_assets, 1.0 / n_assets)
        if strategy == "inverse_variance":
            return np.array(po.portfolios.inverse_variance(cov), dtype=float)
        if strategy == "inverse_volatility":
            return np.array(po.portfolios.inverse_volatility(cov), dtype=float)
        raise POError(f"unsupported walk-forward strategy: {strategy!r}")

    result = po.backtest.walk_forward(
        returns=R,
        window=window,
        step=step,
        build_weights=build_weights,
        transaction_cost=transaction_cost,
    )
    return _summarize_backtest(
        result,
        np,
        tickers=tickers,
        periods_per_year=periods_per_year,
        risk_free_rate=0.0,
        benchmark_path=benchmark_returns_csv_path,
    )


# ---------- Brinson attribution ----------------------------------------


def brinson_attribution(
    *,
    group_weights_p: dict[str, float],
    group_weights_b: dict[str, float],
    group_returns_p: dict[str, float],
    group_returns_b: dict[str, float],
    mode: Literal["brinson_fachler", "brinson_hood_beebower"] = "brinson_fachler",
) -> dict[str, Any]:
    """Brinson decomposition of active return into allocation, selection,
    and (for BHB) interaction effects.

    All four inputs are ``{group_name: value}`` dicts and must share the
    same set of keys.
    """
    po = _import_portopt()
    np = _import_numpy()
    groups = sorted(
        set(group_weights_p)
        | set(group_weights_b)
        | set(group_returns_p)
        | set(group_returns_b)
    )
    wp = np.array([group_weights_p.get(g, 0.0) for g in groups], dtype=float)
    wb = np.array([group_weights_b.get(g, 0.0) for g in groups], dtype=float)
    rp = np.array([group_returns_p.get(g, 0.0) for g in groups], dtype=float)
    rb = np.array([group_returns_b.get(g, 0.0) for g in groups], dtype=float)
    func = (
        po.attribution.brinson_fachler
        if mode == "brinson_fachler"
        else po.attribution.brinson_hood_beebower
    )
    res = func(wp, wb, rp, rb)
    return {
        "mode": mode,
        "groups": groups,
        "allocation": {g: float(res.allocation[i]) for i, g in enumerate(groups)},
        "selection": {g: float(res.selection[i]) for i, g in enumerate(groups)},
        "interaction": (
            {g: float(res.interaction[i]) for i, g in enumerate(groups)}
            if hasattr(res, "interaction")
            else None
        ),
        "totals": {
            "allocation_total": float(res.allocation.sum()),
            "selection_total": float(res.selection.sum()),
            "interaction_total": float(res.interaction.sum())
            if hasattr(res, "interaction")
            else None,
            "active_return": float((rp * wp).sum() - (rb * wb).sum()),
        },
    }


# ---------- internal helpers --------------------------------------------


def _portfolio_payload(
    tickers: list[str], weights, covariance
) -> dict[str, Any]:
    """Standardize the output of every closed-form portfolio."""
    np = _import_numpy()
    w = np.asarray(weights, dtype=float)
    cov = np.asarray(covariance, dtype=float)
    port_var = float(w @ cov @ w)
    port_vol = math.sqrt(max(port_var, 0.0))
    asset_vols = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    weighted_vol = float(np.abs(w) @ asset_vols)
    sumsq = float((w * w).sum())
    rc = {}
    if port_var > 0:
        marginal = cov @ w
        contributions = (w * marginal) / port_var
        rc = {t: float(contributions[i]) for i, t in enumerate(tickers)}
    metrics = {
        "n_assets": int((w != 0).sum()),
        "volatility": port_vol,
        "variance": port_var,
        "max_position": float(np.max(np.abs(w))) if len(w) else 0.0,
        "gross_exposure": float(np.abs(w).sum()),
    }
    if port_vol > 0:
        metrics["diversification_ratio"] = weighted_vol / port_vol
    if sumsq > 0:
        metrics["effective_n"] = 1.0 / sumsq
    return {
        "weights": {t: float(w[i]) for i, t in enumerate(tickers)},
        "metrics": metrics,
        "risk_contributions": rc,
    }


def _summarize_backtest(
    bt_result,
    np,
    *,
    tickers: list[str],
    periods_per_year: int,
    risk_free_rate: float,
    benchmark_path: Path | None,
) -> dict[str, Any]:
    """Compute summary metrics from a portopt backtest result object."""
    po = _import_portopt()
    pnl = np.asarray(getattr(bt_result, "portfolio_returns", []), dtype=float)
    if pnl.size == 0:
        return {"summary": {}, "equity_curve": [], "trades": []}
    eq = po.analytics.equity_curve(pnl, initial=1.0)
    mdd, *_ = po.analytics.max_drawdown(pnl)
    sharpe = po.analytics.sharpe_ratio(pnl, rf=risk_free_rate, periods=periods_per_year)
    sortino = po.analytics.sortino_ratio(
        pnl, rf=risk_free_rate, periods=periods_per_year
    )
    n_years = max(len(pnl) / periods_per_year, 1e-9)
    cagr = float((1.0 + pnl).prod() ** (1.0 / n_years) - 1.0)
    summary = {
        "n_periods": int(len(pnl)),
        "cagr": cagr,
        "sharpe_ratio": float(sharpe),
        "sortino_ratio": float(sortino),
        "max_drawdown": float(mdd),
        "annualized_volatility": float(pnl.std(ddof=0) * (periods_per_year ** 0.5)),
        "total_turnover": float(getattr(bt_result, "total_turnover", 0.0)),
        "total_transaction_cost": float(getattr(bt_result, "total_transaction_cost", 0.0)),
    }
    if benchmark_path is not None:
        _, B = _read_returns_csv(Path(benchmark_path))
        b = np.asarray(B, dtype=float).flatten()
        b = b[: len(pnl)]
        if len(b) == len(pnl):
            active = pnl - b
            te = float(active.std(ddof=0) * (periods_per_year ** 0.5))
            summary["tracking_error"] = te
            if te > 0:
                summary["information_ratio"] = float(active.mean() * periods_per_year / te)
    return {
        "summary": summary,
        "equity_curve": [
            {"period": i, "value": float(v)} for i, v in enumerate(eq.tolist())
        ],
        "tickers": tickers,
        "n_rebalances": int(getattr(bt_result, "n_rebalances", 0)),
    }


def _read_returns_csv(path: Path) -> tuple[list[str], list[list[float]]]:
    """Read a returns CSV (rows = periods, columns = tickers).

    First column may be a date — auto-detected and dropped if non-numeric.
    """
    import csv

    with Path(path).open("r", encoding="utf-8", newline="") as fp:
        reader = csv.reader(fp)
        header = next(reader, None)
        if header is None:
            raise POError(f"returns CSV {path} is empty.")
        data: list[list[float]] = []
        for row in reader:
            data.append(row)

    if not data:
        raise POError(f"returns CSV {path} has no data rows.")

    # Detect a date/label column in position 0
    first_cell = data[0][0]
    try:
        float(first_cell)
        has_date_col = False
    except (TypeError, ValueError):
        has_date_col = True

    start = 1 if has_date_col else 0
    tickers = [h.strip() for h in header[start:]]
    matrix: list[list[float]] = []
    for row in data:
        try:
            matrix.append([float(x) for x in row[start:]])
        except (TypeError, ValueError) as exc:
            raise POError(
                f"non-numeric value in returns CSV {path} at row {row}: {exc}"
            ) from exc
    return tickers, matrix


def _top_n_dict(weights: dict[str, float], *, n: int) -> list[dict[str, Any]]:
    items = sorted(weights.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return [{"ticker": t, "weight": w} for t, w in items[:n]]
