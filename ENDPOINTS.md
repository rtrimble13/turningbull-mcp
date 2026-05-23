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

## Legacy / fallback endpoints used

None of the targeted capabilities require a v3 or v4 fallback at present.
Historical shares float was considered but is not exposed by this server;
if added later, fall back to `/api/v4/historical/shares_float?symbol=...`.
