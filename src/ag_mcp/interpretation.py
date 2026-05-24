"""Structured parsing of `ag` CLI stdout reports and model JSON files.

The CLI's stdout is the analyst-readable report; tools surface it as
``raw_stdout`` for transparency, but the LLM shouldn't have to scrape it.
This module owns the regexes that extract structured fields (log-
likelihood, information criteria, ARIMA/GARCH params, test p-values,
Student-t recommendation) into a flat dict.

Design rules:

* Every extractor returns ``None`` when the field is absent; never raise.
  Stdout formatting can drift across `ag` versions and we don't want a
  cosmetic change to break the connector.
* For fields that also exist in the model JSON (parameters, log-
  likelihood, AIC/BIC), the JSON is authoritative — call
  :func:`parse_model_json` first and merge stdout-only fields on top.
* When an extractor can't find a value, log a stderr warning so the
  regex can be tightened later.
"""

from __future__ import annotations

import re
from typing import Any

from turningbull_mcp.logging import log_stderr

# ---------- low-level regex helpers ---------------------------------------

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
_NUM_RE = re.compile(_NUM)


def _grab_float(pattern: str, text: str) -> float | None:
    """Run ``pattern`` against ``text`` and return the first float capture.

    The regex must have one capture group matching the number.
    """
    m = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def _grab_bool(pattern: str, text: str) -> bool | None:
    m = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip().lower()
    if val in {"true", "yes", "converged", "1"}:
        return True
    if val in {"false", "no", "not_converged", "did_not_converge", "0"}:
        return False
    return None


def _grab_floats(pattern: str, text: str) -> list[float] | None:
    m = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    body = m.group(1)
    nums = _NUM_RE.findall(body)
    if not nums:
        return None
    try:
        return [float(n) for n in nums]
    except ValueError:
        return None


# ---------- stdout extractors --------------------------------------------


def parse_fit_stdout(stdout: str) -> dict[str, Any]:
    """Extract the numeric & flag fields from a fit/select stdout report.

    Returns a dict containing whichever fields parsed cleanly. Unmatched
    fields are simply absent; callers should use ``.get(key)`` and treat
    ``None`` as "unknown" rather than "zero".
    """
    out: dict[str, Any] = {}

    # Information criteria / fit quality. Try a few label variants.
    out["log_likelihood"] = _grab_float(
        rf"log[- ]?likelihood\s*[:=]\s*({_NUM})", stdout
    )
    out["aic"] = _grab_float(rf"\bAIC\s*[:=]\s*({_NUM})", stdout)
    out["bic"] = _grab_float(rf"\bBIC\s*[:=]\s*({_NUM})", stdout)
    out["aicc"] = _grab_float(rf"\bAICc\s*[:=]\s*({_NUM})", stdout)

    # ARIMA params
    out["intercept"] = _grab_float(
        rf"(?:intercept|mean|c0|constant)\s*[:=]\s*({_NUM})", stdout
    )
    out["ar_coef"] = _grab_floats(
        r"(?:^|\n)\s*(?:AR\s*coef(?:ficients)?|ar\s*=|AR)\s*[:=]?\s*[\[(]?([^\]\n)]+)[\])]?",
        stdout,
    )
    out["ma_coef"] = _grab_floats(
        r"(?:^|\n)\s*(?:MA\s*coef(?:ficients)?|ma\s*=|MA)\s*[:=]?\s*[\[(]?([^\]\n)]+)[\])]?",
        stdout,
    )

    # GARCH params
    out["omega"] = _grab_float(rf"omega\s*[:=]\s*({_NUM})", stdout)
    out["alpha_coef"] = _grab_floats(
        r"(?:^|\n)\s*(?:alpha\s*coef(?:ficients)?|alpha)\s*[:=]?\s*[\[(]?([^\]\n)]+)[\])]?",
        stdout,
    )
    out["beta_coef"] = _grab_floats(
        r"(?:^|\n)\s*(?:beta\s*coef(?:ficients)?|beta)\s*[:=]?\s*[\[(]?([^\]\n)]+)[\])]?",
        stdout,
    )

    # Diagnostic test p-values typically printed by fit's quick post-fit summary.
    out["ljung_box_residuals_pvalue"] = _grab_float(
        rf"Ljung[- ]?Box(?!\s*\(?(?:on\s*)?squared)[^\n]*p[- ]?value\s*[:=]\s*({_NUM})",
        stdout,
    )
    out["ljung_box_squared_residuals_pvalue"] = _grab_float(
        rf"Ljung[- ]?Box[^\n]*squared[^\n]*p[- ]?value\s*[:=]\s*({_NUM})", stdout
    )
    out["jarque_bera_pvalue"] = _grab_float(
        rf"Jarque[- ]?Bera[^\n]*p[- ]?value\s*[:=]\s*({_NUM})", stdout
    )

    # Convergence
    converged = _grab_bool(
        r"\bconverged\b\s*[:=]?\s*(true|false|yes|no)", stdout
    )
    if converged is None and re.search(r"\bconverged\b", stdout, re.IGNORECASE):
        # Bare "Converged" line, common pattern.
        if re.search(r"did\s*not\s*converge|not[- ]converged|failed", stdout, re.IGNORECASE):
            converged = False
        else:
            converged = True
    out["converged"] = converged

    # Distribution recommendation block:
    #   "Innovation distribution used: gaussian"
    #   "Student-t would be a better fit (suggested df=4.7)"
    dist = re.search(
        r"innovation\s*(?:distribution)?\s*(?:used)?\s*[:=]\s*(\w+)",
        stdout,
        flags=re.IGNORECASE,
    )
    if dist:
        out["distribution_used"] = dist.group(1).strip().lower()
    recommended = re.search(
        r"student[- ]?t\s+(?:would|appears|might)\s+(?:be|provide)",
        stdout,
        flags=re.IGNORECASE,
    )
    out["student_t_recommended"] = bool(recommended)
    df_hint = _grab_float(
        rf"(?:suggested|recommended|approx(?:imate)?)\s*df\s*[:=≈~]+\s*({_NUM})",
        stdout,
    )
    if df_hint is None:
        df_hint = _grab_float(rf"df\s*[:=≈~]+\s*({_NUM})", stdout)
    out["student_t_df_suggested"] = df_hint

    # Strip None to keep the dict tight; callers expect explicit absence
    # via .get() rather than None-laden payloads.
    cleaned: dict[str, Any] = {k: v for k, v in out.items() if v is not None}

    # Derived fields where we have enough info.
    cleaned.update(_derive_fields(cleaned))
    return cleaned


def parse_diagnostics_stdout(stdout: str) -> dict[str, Any]:
    """Extract diagnostic test p-values from `ag diagnostics` stdout.

    Reuses the fit parser's regexes — the diagnostics report shares the
    same label conventions for Ljung-Box / Jarque-Bera lines.
    """
    out: dict[str, Any] = {}
    out["ljung_box_residuals_pvalue"] = _grab_float(
        rf"Ljung[- ]?Box(?!\s*\(?(?:on\s*)?squared)[^\n]*p[- ]?value\s*[:=]\s*({_NUM})",
        stdout,
    )
    out["ljung_box_squared_residuals_pvalue"] = _grab_float(
        rf"Ljung[- ]?Box[^\n]*squared[^\n]*p[- ]?value\s*[:=]\s*({_NUM})", stdout
    )
    out["jarque_bera_pvalue"] = _grab_float(
        rf"Jarque[- ]?Bera[^\n]*p[- ]?value\s*[:=]\s*({_NUM})", stdout
    )
    return {k: v for k, v in out.items() if v is not None}


# ---------- model JSON extractor -----------------------------------------


def parse_model_json(model_json: dict[str, Any]) -> dict[str, Any]:
    """Flatten a saved model JSON into the same dict shape as the stdout parse.

    The model JSON schema is documented in arima-garch's
    ``docs/file_formats.md``; we look for the common keys defensively so a
    schema bump doesn't take the connector down. Missing keys are simply
    absent in the output.
    """
    out: dict[str, Any] = {}
    if not isinstance(model_json, dict):
        return out

    # Spec
    spec = model_json.get("spec") or model_json.get("model") or {}
    if isinstance(spec, dict):
        arima = spec.get("arima") or {}
        garch = spec.get("garch") or {}
        if isinstance(arima, dict):
            p, d, q = arima.get("p"), arima.get("d"), arima.get("q")
            if all(isinstance(x, int) for x in (p, d, q)):
                out["arima"] = (p, d, q)
        elif isinstance(arima, (list, tuple)) and len(arima) == 3:
            out["arima"] = tuple(int(x) for x in arima)
        if isinstance(garch, dict):
            gp, gq = garch.get("p"), garch.get("q")
            if all(isinstance(x, int) for x in (gp, gq)):
                out["garch"] = (gp, gq)
        elif isinstance(garch, (list, tuple)) and len(garch) == 2:
            out["garch"] = tuple(int(x) for x in garch)

    # Parameter coefficients (model JSON form, if present at top level)
    for key, alias in (
        ("intercept", ("intercept", "mean", "c0", "constant")),
        ("omega", ("omega",)),
    ):
        for a in alias:
            v = _nested_get(model_json, "params", a)
            if v is None:
                v = model_json.get(a)
            if isinstance(v, (int, float)):
                out[key] = float(v)
                break

    for key, alias in (
        ("ar_coef", ("ar", "ar_coef", "ar_coefficients")),
        ("ma_coef", ("ma", "ma_coef", "ma_coefficients")),
        ("alpha_coef", ("alpha", "alpha_coef", "alpha_coefficients")),
        ("beta_coef", ("beta", "beta_coef", "beta_coefficients")),
    ):
        for a in alias:
            v = _nested_get(model_json, "params", a)
            if v is None:
                v = model_json.get(a)
            if isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
                out[key] = [float(x) for x in v]
                break

    # Information criteria & fit quality at top level of the JSON
    for key, aliases in (
        ("log_likelihood", ("log_likelihood", "loglikelihood", "loglik")),
        ("aic", ("aic", "AIC")),
        ("bic", ("bic", "BIC")),
        ("aicc", ("aicc", "AICc")),
    ):
        for a in aliases:
            v = model_json.get(a)
            if v is None:
                v = _nested_get(model_json, "fit", a)
            if isinstance(v, (int, float)):
                out[key] = float(v)
                break

    # Innovation distribution
    inn = model_json.get("innovation") or _nested_get(model_json, "spec", "innovation")
    if isinstance(inn, dict):
        dist = inn.get("distribution") or inn.get("type")
        if isinstance(dist, str):
            out["distribution_used"] = dist.lower()
        df = inn.get("t_df") or inn.get("df")
        if isinstance(df, (int, float)):
            out["t_df"] = float(df)
    elif isinstance(inn, str):
        out["distribution_used"] = inn.lower()

    out["converged"] = _coerce_converged(
        model_json.get("converged"),
        _nested_get(model_json, "fit", "converged"),
    )
    if out["converged"] is None:
        out.pop("converged")

    # Derived
    out.update(_derive_fields(out))
    return out


def _coerce_converged(*values: Any) -> bool | None:
    for v in values:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            sv = v.strip().lower()
            if sv in {"true", "yes", "converged", "1"}:
                return True
            if sv in {"false", "no", "did_not_converge", "0"}:
                return False
    return None


def _nested_get(obj: Any, *keys: str) -> Any:
    cur: Any = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


# ---------- derived diagnostic fields ------------------------------------


def _derive_fields(d: dict[str, Any]) -> dict[str, Any]:
    """Compute derived diagnostics from raw fields we already extracted.

    - ``garch_persistence`` = sum(alpha) + sum(beta)
    - ``near_unit_root``     = persistence > 0.99
    - ``mean_reverting``     = persistence < 1 and |ar_coef|_max < 1
    - ``unconditional_variance`` = omega / (1 - persistence) when persistence < 1
    """
    derived: dict[str, Any] = {}
    alpha = d.get("alpha_coef") or []
    beta = d.get("beta_coef") or []
    if alpha or beta:
        persistence = float(sum(alpha) + sum(beta))
        derived["garch_persistence"] = persistence
        derived["near_unit_root"] = persistence > 0.99
        ar = d.get("ar_coef") or []
        ar_ok = (max((abs(float(x)) for x in ar), default=0.0) < 1.0) if ar else True
        derived["mean_reverting"] = persistence < 1.0 and ar_ok
        omega = d.get("omega")
        if isinstance(omega, (int, float)) and persistence < 1.0:
            derived["unconditional_variance"] = float(omega) / (1.0 - persistence)
        else:
            derived["unconditional_variance"] = None
    return derived


# ---------- light-weight warning hook ------------------------------------


def warn_missing(field: str, stdout_snippet: str) -> None:
    """Log a one-line warning when a field couldn't be parsed.

    Kept tiny so callers can sprinkle it through their own helpers without
    pulling in a full logger. Stdout snippet is truncated to keep stderr
    readable.
    """
    snippet = stdout_snippet[:200].replace("\n", " ")
    log_stderr(f"ag_mcp: could not parse field {field!r}. stdout starts: {snippet!r}")
