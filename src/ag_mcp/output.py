"""AG-flavored output-directory resolution.

Persisted artifacts (model JSONs, returns CSVs, forecast CSVs, simulation
CSVs, diagnostics JSONs) live under ``$AG_OUTPUT_DIR`` in a fixed
substructure so a quant can find every file produced by any tool.

Layout (created lazily on first use):

```
$AG_OUTPUT_DIR/
├── prices/      raw price CSVs from FMP
├── series/      raw series CSVs from BLS/BEA
├── returns/     derived log/simple returns CSVs (input to `ag fit`)
├── models/      fitted model JSONs
├── forecasts/   forecast CSVs from `ag forecast`
├── simulations/ simulation CSVs from `ag simulate` / `ag sim`
└── diagnostics/ diagnostics JSONs from `ag diagnostics`
```
"""

from __future__ import annotations

from pathlib import Path

from turningbull_mcp.output import resolve_output_dir

SUBDIRS: tuple[str, ...] = (
    "prices",
    "series",
    "returns",
    "models",
    "forecasts",
    "simulations",
    "diagnostics",
)


def output_dir() -> Path:
    """Resolve ``$AG_OUTPUT_DIR`` (defaulting to ``./ag_output``).

    Always ensures the subdirectory tree exists so downstream writers don't
    need to mkdir defensively.
    """
    root = resolve_output_dir("AG_OUTPUT_DIR", "./ag_output")
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def prices_dir() -> Path:
    return output_dir() / "prices"


def series_dir() -> Path:
    return output_dir() / "series"


def returns_dir() -> Path:
    return output_dir() / "returns"


def models_dir() -> Path:
    return output_dir() / "models"


def forecasts_dir() -> Path:
    return output_dir() / "forecasts"


def simulations_dir() -> Path:
    return output_dir() / "simulations"


def diagnostics_dir() -> Path:
    return output_dir() / "diagnostics"


def safe_filename(name: str) -> str:
    """Make ``name`` safe for use as a filename component."""
    keep = "-_.,()^"
    return "".join(c if c.isalnum() or c in keep else "_" for c in name)


def spec_string(arima: tuple[int, int, int], garch: tuple[int, int]) -> str:
    """Render an ARIMA(p,d,q)-GARCH(p,q) spec into a filename-safe stem."""
    p, d, q = arima
    gp, gq = garch
    return f"arima{p}{d}{q}_garch{gp}{gq}"
