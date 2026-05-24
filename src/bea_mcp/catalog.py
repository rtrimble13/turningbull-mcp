"""Curated catalog of high-value BEA tables.

BEA's full table inventory is huge (hundreds of NIPA tables, hundreds of
Regional tables, dozens of industry tables) and volatile. We hardcode a
small set of the most-requested tables here so :func:`bea_search_tables`
can answer routine questions without round-tripping ``GetParameterValues``,
and the composite snapshots can reference well-known TableNames by symbol.
"""

from __future__ import annotations

from typing import Any

# Each entry: (dataset, table_name_or_id, title, freq_hint).
POPULAR_TABLES: list[dict[str, str]] = [
    # ---- NIPA: National Income and Product Accounts -----------------------
    {"dataset": "NIPA", "table": "T10101", "title": "Percent Change From Preceding Period in Real GDP", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T10102", "title": "Contributions to Percent Change in Real GDP", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T10103", "title": "Real GDP, Quantity Indexes", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T10105", "title": "Gross Domestic Product (current $)", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T10106", "title": "Real Gross Domestic Product, chained dollars", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T10109", "title": "Implicit Price Deflators for Gross Domestic Product", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T11200", "title": "National Income by Type of Income", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T11400", "title": "Corporate Profits by Industry", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T20100", "title": "Personal Income and Its Disposition", "freq": "M,Q,A"},
    {"dataset": "NIPA", "table": "T20600", "title": "Personal Income and Its Disposition, Monthly", "freq": "M"},
    {"dataset": "NIPA", "table": "T20305", "title": "Personal Consumption Expenditures by Major Type of Product", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T20804", "title": "Price Indexes for Personal Consumption Expenditures by Type of Product", "freq": "M,Q,A"},
    {"dataset": "NIPA", "table": "T30100", "title": "Government Current Receipts and Expenditures", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T40100", "title": "Foreign Transactions in the National Income and Product Accounts", "freq": "Q,A"},
    {"dataset": "NIPA", "table": "T50100", "title": "Gross and Net Domestic Investment by Major Type", "freq": "Q,A"},
    # ---- Fixed Assets ------------------------------------------------------
    {"dataset": "FixedAssets", "table": "FAAt101", "title": "Current-Cost Net Stock of Fixed Assets and Consumer Durable Goods", "freq": "A"},
    {"dataset": "FixedAssets", "table": "FAAt201", "title": "Current-Cost Depreciation of Fixed Assets and Consumer Durable Goods", "freq": "A"},
    # ---- Regional (state + county; SAGDP* state GDP, CAINC* personal income, SAEMP* employment) --
    {"dataset": "Regional", "table": "SAGDP1", "title": "State annual gross domestic product summary", "freq": "A"},
    {"dataset": "Regional", "table": "SAGDP2N", "title": "Gross domestic product by state, NAICS", "freq": "A"},
    {"dataset": "Regional", "table": "SAGDP9N", "title": "Real GDP by state (chained dollars)", "freq": "A"},
    {"dataset": "Regional", "table": "SAGDP10N", "title": "Per capita real GDP by state", "freq": "A"},
    {"dataset": "Regional", "table": "SQGDP2", "title": "Gross domestic product by state, quarterly", "freq": "Q"},
    {"dataset": "Regional", "table": "CAINC1", "title": "Personal income summary: by county/state", "freq": "A"},
    {"dataset": "Regional", "table": "CAINC4", "title": "Personal income and employment by major component", "freq": "A"},
    {"dataset": "Regional", "table": "CAINC30", "title": "Economic profile (per-capita personal income, etc.)", "freq": "A"},
    {"dataset": "Regional", "table": "SAEMP25N", "title": "Total full-time and part-time employment by state", "freq": "A"},
    {"dataset": "Regional", "table": "SAINC1", "title": "State personal income summary", "freq": "A,Q"},
    # ---- GDP by Industry ---------------------------------------------------
    {"dataset": "GDPbyIndustry", "table": "1", "title": "Value Added by Industry", "freq": "Q,A"},
    {"dataset": "GDPbyIndustry", "table": "5", "title": "Value Added by Industry as a Percentage of GDP", "freq": "Q,A"},
    {"dataset": "GDPbyIndustry", "table": "6", "title": "Components of Value Added by Industry", "freq": "A"},
    {"dataset": "GDPbyIndustry", "table": "8", "title": "Chain-Type Quantity Indexes for Value Added by Industry", "freq": "Q,A"},
    {"dataset": "GDPbyIndustry", "table": "11", "title": "Real Value Added by Industry, chained dollars", "freq": "A"},
    {"dataset": "GDPbyIndustry", "table": "15", "title": "Gross Output by Industry", "freq": "Q,A"},
    # ---- Input-Output ------------------------------------------------------
    {"dataset": "InputOutput", "table": "56", "title": "Total Requirements, Industry by Commodity", "freq": "A"},
    {"dataset": "InputOutput", "table": "57", "title": "Total Requirements, Commodity by Industry", "freq": "A"},
    {"dataset": "InputOutput", "table": "63", "title": "Use of Commodities by Industries, after Redefinitions (Producers' Prices)", "freq": "A"},
    # ---- ITA: International Transactions Accounts (BoP) -------------------
    {"dataset": "ITA", "table": "BalCurrAcct", "title": "Balance on current account", "freq": "A,Q"},
    {"dataset": "ITA", "table": "BalGds", "title": "Balance on goods (BoP basis)", "freq": "A,Q"},
    {"dataset": "ITA", "table": "BalServ", "title": "Balance on services", "freq": "A,Q"},
    {"dataset": "ITA", "table": "BalGdsServ", "title": "Balance on goods and services", "freq": "A,Q"},
    {"dataset": "ITA", "table": "BalSecondaryInc", "title": "Balance on secondary income (current transfers)", "freq": "A,Q"},
    # ---- IIP: International Investment Position --------------------------
    {"dataset": "IIP", "table": "IIPNetPos", "title": "Net international investment position", "freq": "A,Q"},
    {"dataset": "IIP", "table": "USAssets", "title": "U.S. assets abroad", "freq": "A,Q"},
    {"dataset": "IIP", "table": "USLiab", "title": "U.S. liabilities to foreigners", "freq": "A,Q"},
]


def search_tables(query: str, dataset: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    """Substring-rank ``POPULAR_TABLES`` against ``query``.

    Same scoring as ``bls_search_series`` (`src/bls_mcp/tools/discovery.py`)
    so the model feels consistent across connectors.
    """
    q = (query or "").strip().lower()
    tokens = [t for t in q.split() if t] if q else []
    out: list[tuple[int, dict[str, Any]]] = []
    for row in POPULAR_TABLES:
        if dataset and row["dataset"].lower() != dataset.lower():
            continue
        hay = f"{row['dataset']} {row['table']} {row['title']}".lower()
        score = sum(1 for t in tokens if t in hay) if tokens else 1
        if q and q in hay:
            score += 2
        if score > 0:
            out.append((score, row))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in out[:limit]]
