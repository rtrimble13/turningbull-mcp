# FMP MCP Server — Tool → Endpoint Map

Authoritative mapping of every tool in this server to its underlying Financial
Modeling Prep (FMP) API endpoint. All paths assume base
`https://financialmodelingprep.com` and require `?apikey=YOUR_KEY` on every
request. All endpoints are GET. Stable endpoints are preferred; legacy v3/v4
fallbacks are flagged explicitly.

Global notes:
- `period` for statements/ratios/key-metrics is one of `annual` | `quarter` |
  `Q1` | `Q2` | `Q3` | `Q4`. **Never** `quarterly`.
- EOD price history and historical market cap are capped at ~5 years per
  request. Tools chunk longer ranges automatically.
- Many list endpoints support `limit` and `page` (0-based) pagination.

---

## 1. Prices & quotes — `tools/prices.py`

### `fmp_get_quote`
- Path: `/stable/quote`
- Symbol style: `?symbol=AAPL` (single). For batch use `/stable/batch-quote`.
- Optional batch path: `/stable/batch-quote?symbols=AAPL,MSFT,GOOG`
- Key response fields: `symbol`, `name`, `price`, `changesPercentage`, `change`,
  `dayLow`, `dayHigh`, `yearHigh`, `yearLow`, `marketCap`, `priceAvg50`,
  `priceAvg200`, `volume`, `avgVolume`, `exchange`, `open`, `previousClose`,
  `eps`, `pe`, `earningsAnnouncement`, `sharesOutstanding`, `timestamp`
- Notes: Same path works for indexes (`^GSPC`), forex, crypto, commodities.

### `fmp_get_historical_prices`
- Path: `/stable/historical-price-eod/full`
- Required: `symbol`. Optional: `from`, `to` (YYYY-MM-DD).
- Response: array of daily bars `{symbol, date, open, high, low, close,
  volume, change, changePercent, vwap}`.
- Gotcha: ~5-year cap per request → tool auto-chunks for longer ranges.
- Use `adjClose` from the response (when present) for return calculations.

### `fmp_get_intraday_prices`
- Path: `/stable/historical-chart/{interval}` where `{interval}` ∈
  `1min` | `5min` | `15min` | `30min` | `1hour` | `4hour`.
- Required: `symbol`. Optional: `from`, `to`, `nonadjusted` (bool).
- Response: array of `{date, open, high, low, close, volume}`.
- Gotcha: 1min depth ≈ last 30 days; longer for coarser intervals.

---

## 2. News — `tools/news.py`

### `fmp_get_stock_news`
- Filtered path: `/stable/news/stock` — required `symbols` (comma-separated).
  Optional: `from`, `to`, `page`, `limit`.
- Unfiltered feed path: `/stable/news/stock-latest` — optional `page`, `limit`.
- Response: array of `{symbol, publishedDate, publisher, title, image, site,
  text, url}`.

### `fmp_get_market_news`
- Path: `/stable/news/general-latest`
- Optional: `page` (default 0), `limit` (default 20).
- Response: array of `{publishedDate, publisher, title, image, site, text, url}`.

### `fmp_get_press_releases`
- Filtered path: `/stable/news/press-releases` — required `symbols`,
  optional `from`, `to`, `page`, `limit`.
- Unfiltered feed path: `/stable/news/press-releases-latest` — optional
  `page`, `limit`.
- Response: array of `{symbol, date, title, text, url}`.

---

## 3. Financial statements — `tools/financials.py`

All four statement endpoints share the same parameter contract:
required `symbol`; optional `period` (`annual`|`quarter`|`Q1..Q4`), `limit`.

### `fmp_get_income_statement`
- Path: `/stable/income-statement`
- Key fields: `date`, `period`, `revenue`, `costOfRevenue`, `grossProfit`,
  `grossProfitRatio`, `operatingIncome`, `interestExpense`, `incomeBeforeTax`,
  `incomeTaxExpense`, `netIncome`, `eps`, `epsdiluted`,
  `weightedAverageShsOut`, `weightedAverageShsOutDil`.

### `fmp_get_balance_sheet`
- Path: `/stable/balance-sheet-statement`
- Key fields: `cashAndCashEquivalents`, `shortTermInvestments`, `inventory`,
  `totalCurrentAssets`, `propertyPlantEquipmentNet`, `goodwill`,
  `intangibleAssets`, `totalAssets`, `accountPayables`, `shortTermDebt`,
  `longTermDebt`, `totalLiabilities`, `commonStock`, `retainedEarnings`,
  `totalStockholdersEquity`, `totalEquity`, `totalDebt`, `netDebt`.

### `fmp_get_cash_flow`
- Path: `/stable/cashflow-statement` (single word: `cashflow`).
- Key fields: `netIncome`, `depreciationAndAmortization`,
  `stockBasedCompensation`, `changeInWorkingCapital`,
  `netCashProvidedByOperatingActivities`,
  `investmentsInPropertyPlantAndEquipment`, `acquisitionsNet`,
  `purchasesOfInvestments`, `salesMaturitiesOfInvestments`,
  `netCashUsedForInvestingActivites`, `debtRepayment`, `commonStockIssued`,
  `commonStockRepurchased`, `dividendsPaid`,
  `netCashUsedProvidedByFinancingActivities`, `freeCashFlow`,
  `capitalExpenditure`.

### `fmp_get_financial_ratios`
- Path: `/stable/ratios`
- Key fields: `currentRatio`, `quickRatio`, `cashRatio`,
  `cashConversionCycle`, `grossProfitMargin`, `operatingProfitMargin`,
  `pretaxProfitMargin`, `netProfitMargin`, `effectiveTaxRate`,
  `returnOnAssets`, `returnOnEquity`, `returnOnCapitalEmployed`, `debtRatio`,
  `debtEquityRatio`, `priceEarningsRatio`, `priceToBookRatio`,
  `priceToSalesRatio`, `dividendYield`.

### `fmp_get_key_metrics`
- Path: `/stable/key-metrics`
- Key fields: `revenuePerShare`, `freeCashFlowPerShare`, `bookValuePerShare`,
  `marketCap`, `enterpriseValue`, `peRatio`, `pbRatio`,
  `enterpriseValueOverEBITDA`, `evToFreeCashFlow`, `earningsYield`,
  `freeCashFlowYield`, `debtToEquity`, `netDebtToEBITDA`, `currentRatio`,
  `interestCoverage`, `dividendYield`, `payoutRatio`, `roic`, `grahamNumber`,
  `workingCapital`, `investedCapital`.

---

## 4. Corporate information — `tools/corporate.py`

### `fmp_get_company_profile`
- Path: `/stable/profile`
- Required: `symbol`.
- Key fields: `symbol`, `companyName`, `sector`, `industry`, `exchange`,
  `country`, `mktCap`, `description`, `ceo`, `fullTimeEmployees`, `website`,
  `ipoDate`, `beta`, `volAvg`, `lastDiv`, `range`, `price`, `isEtf`,
  `isActivelyTrading`, `isAdr`, `isFund`.

### `fmp_search_symbol`
- Path: `/stable/search-name` for name-based search, `/stable/search-symbol`
  for ticker-based search. Tool exposes both modes via a `mode` parameter.
- Required: `query`. Optional: `limit`, `exchange`.
- Response: array of `{symbol, name, currency, exchangeFullName, exchange}`.

### `fmp_get_company_executives`
- Path: `/stable/key-executives`
- Required: `symbol`.
- Response: array of `{title, name, pay, currencyPay, gender, yearBorn,
  titleSince}`.

### `fmp_get_shares_float`
- Path: `/stable/shares-float`
- Required: `symbol`.
- Response: array (single element) of `{symbol, date, freeFloat, floatShares,
  outstandingShares, source}`.

### `fmp_get_market_cap`
- Current path: `/stable/market-cap` (required `symbol`).
- Historical path: `/stable/historical-market-cap` (required `symbol`;
  optional `from`, `to`, `limit`). Same ~5-year cap as historical prices.

---

## 5. Sector & industry classification — `tools/classification.py`

### `fmp_list_sectors`
- Path: `/stable/available-sectors`

### `fmp_list_industries`
- Path: `/stable/available-industries`

### `fmp_get_sector_performance`
- Snapshot path: `/stable/sector-performance-snapshot` —
  optional `date`, `exchange`, `sector`.
- Historical path: `/stable/historical-sector-performance` —
  required `sector`; optional `from`, `to`, `exchange`.

### `fmp_get_sector_pe`
- Snapshot path: `/stable/sector-pe-snapshot` — required `date`;
  optional `exchange`, `sector`.
- Historical path: `/stable/historical-sector-pe` — required `sector`;
  optional `from`, `to`, `exchange`.

---

## 6. Stock indexes — `tools/indexes.py`

### `fmp_list_indexes`
- Path: `/stable/indexes-list`
- Response: array of `{symbol, name, exchange, currency}`.

### `fmp_get_index_quote`
- Path: `/stable/quote?symbol=^GSPC` (same as equity quote).
- For all indexes at once: `/stable/all-index-quotes` (optional `short=true`).

### `fmp_get_index_constituents`
- S&P 500: `/stable/sp500-constituent`
- Nasdaq 100: `/stable/nasdaq-constituent`
- Dow Jones: `/stable/dowjones-constituent`
- Tool takes an `index` enum and routes accordingly.

Index price history reuses `fmp_get_historical_prices` with the index
symbol (e.g. `^GSPC`).

---

## 7. Economic & treasury — `tools/macro.py`

### `fmp_list_economic_indicators`
- No list endpoint. Tool returns a hardcoded inventory of FMP's documented
  indicator `name` values: `GDP`, `realGDP`, `nominalPotentialGDP`,
  `realGDPPerCapita`, `federalFunds`, `CPI`, `inflationRate`, `inflation`,
  `retailSales`, `consumerSentiment`, `durableGoods`, `unemploymentRate`,
  `totalNonfarmPayroll`, `initialClaims`,
  `industrialProductionTotalIndex`,
  `newPrivatelyOwnedHousingUnitsStartedTotalUnits`, `totalVehicleSales`,
  `retailMoneyFunds`, `smoothedUSRecessionProbabilities`,
  `30YearFixedRateMortgageAverage`, `15YearFixedRateMortgageAverage`.

### `fmp_get_economic_indicator`
- Path: `/stable/economic-indicators`
- Required: `name`. Optional: `from`, `to`.
- Response: array of `{date, value}`.

### `fmp_get_treasury_rates`
- Path: `/stable/treasury-rates`
- Optional: `from`, `to`.
- Response: array of `{date, month1, month2, month3, month6, year1, year2,
  year3, year5, year7, year10, year20, year30}` — one row per day across
  all maturities.

---

## 8. Screener — `tools/screener.py`

### `fmp_screen_stocks`
- Path: `/stable/company-screener`
- All filters optional. Only parameters explicitly set by the caller are
  forwarded. Exact spellings as FMP requires:
  - `marketCapMoreThan`, `marketCapLowerThan` (note `LowerThan`, not
    `LessThan` or `HigherThan`)
  - `priceMoreThan`, `priceLowerThan`
  - `betaMoreThan`, `betaLowerThan`
  - `volumeMoreThan`, `volumeLowerThan`
  - `dividendMoreThan`, `dividendLowerThan`
  - `sector`, `industry`, `country` (ISO-2), `exchange`
  - `isEtf`, `isFund`, `isActivelyTrading`
  - `limit`, `includeAllShareClasses`
- Response: array of `{symbol, companyName, marketCap, sector, industry,
  beta, price, lastAnnualDividend, volume, exchange, exchangeShortName,
  country, isEtf, isFund, isActivelyTrading}`.

---

---

## 9. Technical indicators — `tools/technicals.py`

### `fmp_get_technical_indicator`
- Path: `/stable/technical-indicators/{indicator}`
- `indicator` ∈ `sma | ema | wma | dema | tema | williams | rsi | adx | standardDeviation`
- Required: `symbol`, `periodLength`, `timeframe` (`1min`|`5min`|`15min`|`30min`|`1hour`|`4hour`|`1day`).
- Optional: `from`, `to` (YYYY-MM-DD).
- Response: OHLCV rows with one additional column matching the indicator name (e.g. `rsi`, `sma`).
- Gotchas: 1min depth ≈ last 30 days; longer for coarser intervals. Use `1day` for multi-year technical work.

---

## 10. Event calendars — `tools/calendars.py`

### `fmp_get_earnings_calendar`
- Path: `/stable/earnings-calendar`
- Optional: `from`, `to`.
- Response: `{symbol, date, epsEstimated, eps, revenueEstimated, revenue, time, fiscalDateEnding, updatedFromDate}`.

### `fmp_get_earnings_surprises`
- Path: `/stable/earnings-surprises`
- Required: `symbol`. Optional: `limit`.
- Response: `{date, symbol, actualEarningResult, estimatedEarning}`.

### `fmp_get_per_symbol_earnings`
- Path: `/stable/earnings`
- Required: `symbol`. Optional: `limit`.
- Same fields as earnings calendar, filtered to one symbol.

### `fmp_get_dividend_calendar`
- Path: `/stable/dividends-calendar`
- Optional: `from`, `to`.
- Response: `{symbol, date, recordDate, paymentDate, declarationDate, adjDividend, dividend, frequency}`.

### `fmp_get_split_calendar`
- Path: `/stable/splits-calendar`
- Optional: `from`, `to`.
- Response: `{symbol, date, numerator, denominator}`.

### `fmp_get_ipo_calendar`
- Path: `/stable/ipos-calendar`
- Optional: `from`, `to`.
- Response: `{symbol, company, date, exchange, actions, priceRange, shares, marketCap}`.

### `fmp_get_economic_calendar`
- Path: `/stable/economic-calendar`
- Optional: `from`, `to`.
- Response: `{date, country, event, actual, previous, change, estimate, impact, unit}`.

---

## 11. Analyst estimates & ratings — `tools/estimates.py`

### `fmp_get_analyst_estimates`
- Path: `/stable/analyst-estimates`
- Required: `symbol`. Optional: `period` (`annual`|`quarter`), `limit`.
- Response: `{symbol, date, revenueAvg, revenueLow, revenueHigh, ebitdaAvg, epsAvg, epsLow, epsHigh, numAnalystsRevenue, numAnalystsEps}`.

### `fmp_get_price_target_consensus`
- Path: `/stable/price-target-consensus`
- Required: `symbol`. Response: `{symbol, targetHigh, targetLow, targetConsensus, targetMedian}`.

### `fmp_get_price_target_summary`
- Path: `/stable/price-target-summary`
- Required: `symbol`. Returns rolling target stats and analyst counts.

### `fmp_get_price_target_news`
- Path: `/stable/price-target-news`
- Required: `symbol`. Optional: `page`, `limit`.

### `fmp_get_upgrades_downgrades`
- Path: `/stable/grades`
- Required: `symbol`. Optional: `page`, `limit`.

### `fmp_get_stock_grade_consensus`
- Path: `/stable/grades-consensus`
- Required: `symbol`. Returns rating distribution.

### `fmp_get_latest_upgrades_downgrades`
- Path: `/stable/grades-latest-news`
- Optional: `from`, `to`, `page`, `limit`.

---

## 12. Earnings transcripts — `tools/transcripts.py`

### `fmp_list_earnings_transcripts`
- Path: `/stable/earning-call-transcript-dates`
- Required: `symbol`. Returns `{symbol, quarter, year, date}`.

### `fmp_get_earnings_transcript`
- Path: `/stable/earning-call-transcript`
- Required: `symbol`, `year`, `quarter`.
- Response: `{symbol, quarter, year, date, content}` — long-form. Use `mode=summary` default.

### `fmp_get_latest_transcripts`
- Path: `/stable/earning-call-transcript-latest`
- Optional: `limit`, `page`. PREMIUM.

---

## 13. Valuation & quality scores — `tools/valuation.py`

### `fmp_get_dcf`
- Path: `/stable/discounted-cash-flow`
- Required: `symbol`. Response: `{symbol, date, dcf, "Stock Price"}`.

### `fmp_get_advanced_dcf`
- Path: `/stable/custom-discounted-cash-flow` (PREMIUM)

### `fmp_get_levered_dcf`
- Path: `/stable/custom-levered-discounted-cash-flow` (PREMIUM)

### `fmp_get_historical_dcf`
- Path: `/stable/historical-discounted-cash-flow-statement`
- Required: `symbol`. Optional: `period`, `limit`.

### `fmp_get_financial_score`
- Path: `/stable/financial-scores`
- Required: `symbol`. Returns Piotroski + Altman Z in one call.

### `fmp_get_company_rating`
- Path: `/stable/ratings-snapshot`
- Required: `symbol`. Composite letter grade with sub-scores.

### `fmp_get_historical_rating`
- Path: `/stable/ratings-historical`
- Required: `symbol`. Optional: `limit`.

---

## 14. Ownership signals — `tools/ownership.py`

### `fmp_get_insider_trades`
- Path: `/stable/insider-trading`
- Required: `symbol`. Optional: `transactionType` (`P-Purchase`, `S-Sale`, `A-Award`, `M-Exempt`, `G-Gift`), `page`, `limit`.

### `fmp_get_insider_statistics`
- Path: `/stable/insider-trading-statistics`
- Required: `symbol`. Optional: `limit`.

### `fmp_get_institutional_holders`
- Path: `/stable/institutional-ownership/symbol-positions-summary`
- Required: `symbol`.

### `fmp_get_form_13f`
- Path: `/stable/institutional-ownership/extract`
- Required: `cik` (10-digit, leading zeros auto-padded), `year`, `quarter`.

### `fmp_search_institution`
- Path: `/stable/institutional-ownership/list`
- Required: `name`.

### `fmp_get_senate_trades`
- Path: `/stable/senate-latest` or `/stable/senate-trades`
- Optional: `symbol`.

### `fmp_get_house_trades`
- Path: `/stable/house-latest` or `/stable/house-trades`
- Optional: `symbol`.

---

## 15. SEC filings & M&A — `tools/filings.py`

### `fmp_list_sec_filings`
- Path: `/stable/sec-filings-search/symbol`
- Required: `symbol`. Optional: `type`, `from`, `to`, `page`, `limit`.

### `fmp_search_filings_by_form_type`
- Path: `/stable/sec-filings-search/form-type`
- Required: `formType`. Optional: `from`, `to`, `page`, `limit`.

### `fmp_get_8k_feed`
- Path: `/stable/sec-filings-8k`
- Optional: `from`, `to`, `page`, `limit`.

### `fmp_search_mergers_acquisitions`
- Path: `/stable/mergers-acquisitions-search`
- Required: `name`.

### `fmp_get_latest_mergers_acquisitions`
- Path: `/stable/mergers-acquisitions-latest`
- Optional: `page`, `limit`.

---

## 16. Market movers — `tools/movers.py`

### `fmp_get_gainers`
- Path: `/stable/biggest-gainers`. Optional `limit` (client-side trim).

### `fmp_get_losers`
- Path: `/stable/biggest-losers`. Optional `limit`.

### `fmp_get_most_active`
- Path: `/stable/most-actives`. Optional `limit`.

### `fmp_get_aftermarket_quote`
- Path: `/stable/aftermarket-quote`. Required: `symbol`.

### `fmp_get_aftermarket_trades`
- Path: `/stable/aftermarket-trade`. Required: `symbol`.

### `fmp_get_premarket_quote`
- Path: `/stable/premarket-quote`. Required: `symbol`.

---

## 17. ETFs & mutual funds — `tools/etf.py`

### `fmp_get_etf_holdings`
- Path: `/stable/etf/holdings`. Required: `symbol`.

### `fmp_get_etf_holders` (reverse lookup)
- Path: `/stable/etf/holder`. Required: `symbol` (the stock).

### `fmp_get_etf_info`
- Path: `/stable/etf/info`. Required: `symbol`.

### `fmp_get_etf_country_weightings`
- Path: `/stable/etf/country-weightings`. Required: `symbol`.

### `fmp_get_etf_sector_weightings`
- Path: `/stable/etf/sector-weightings`. Required: `symbol`.

### `fmp_get_mutual_fund_holdings`
- Path: `/stable/funds/holdings`. Required: `symbol`. PREMIUM on some plans.

---

## 18. Multi-asset discovery — `tools/multiasset.py`

### `fmp_list_forex_pairs`
- Path: `/stable/forex-list`.

### `fmp_list_crypto`
- Path: `/stable/cryptocurrency-list`.

### `fmp_list_commodities`
- Path: `/stable/commodities-list`.

### `fmp_get_all_forex_quotes` / `fmp_get_all_crypto_quotes` / `fmp_get_all_commodity_quotes`
- Paths: `/stable/batch-forex-quotes`, `/stable/batch-crypto-quotes`, `/stable/batch-commodity-quotes`.

Per-asset quote and historical bars work through the standard
`fmp_get_quote` and `fmp_get_historical_prices` tools by passing the
appropriate symbol (e.g. `EURUSD`, `BTCUSD`, `CLUSD`).

---

## 19. Extensions to existing modules

Added to `tools/financials.py`:

- `fmp_get_financial_growth` → `/stable/financial-growth`
- `fmp_get_enterprise_values` → `/stable/enterprise-values`
- `fmp_get_owner_earnings` → `/stable/owner-earnings`
- `fmp_get_revenue_product_segmentation` → `/stable/revenue-product-segmentation`
- `fmp_get_revenue_geographic_segmentation` → `/stable/revenue-geographic-segmentation`

Added to `tools/corporate.py`:

- `fmp_get_dividend_history` → `/stable/dividends`
- `fmp_get_split_history` → `/stable/splits`
- `fmp_get_stock_peers` → `/stable/stock-peers`
- `fmp_get_historical_employee_count` → `/stable/historical-employee-count`
- `fmp_get_historical_shares_float` → `/api/v4/historical/shares_float`

Macro indicator catalog (`ECONOMIC_INDICATORS` in `models.py`) was
expanded to include M2, ISM, capacity utilization, PPI / core PPI,
core CPI, PCE / core PCE, personal income, trade balance, industrial
production, private payrolls, AHE, AWH, LFPR, employment-population
ratio, JOLTS openings / quits / hires, home sales.

---

## 20. Composite snapshots — `tools/composites.py`

Bundle multiple endpoints into one analyst-friendly call. Failed
sub-calls (e.g. premium-gated transcript fetch on free key) surface as
`{error: ...}` inside the composite so the rest of the payload is
still usable.

- `fmp_company_snapshot` — profile + quote + key metrics + price target + 3 latest headlines
- `fmp_valuation_snapshot` — DCF + key metrics + price target + peers + financial scores + rating
- `fmp_earnings_prep` — next earnings + last 4 surprises + transcript dates + forward estimates + grade consensus
- `fmp_technical_snapshot` — quote + RSI(14) + SMA(50/200) + EMA(12/26) + ADX(14) at chosen interval
- `fmp_ownership_snapshot` — shares float + institutional summary + insider statistics

---

## Legacy / fallback endpoints used

- `fmp_get_historical_shares_float` falls back to `/api/v4/historical/shares_float?symbol=...` — FMP has no stable equivalent yet.

All other tools target stable `/stable/*` paths. PREMIUM-tier endpoints
(`custom-discounted-cash-flow`, `custom-levered-discounted-cash-flow`,
`earning-call-transcript-latest`, `funds/holdings`) raise a clean
`FMPError` with the upstream message on free-tier keys.
