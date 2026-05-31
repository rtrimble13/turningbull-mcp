# FRED MCP Server — Tool → Endpoint Map

Authoritative mapping of every tool in this server to its underlying FRED
endpoint. The connector wraps the full **core FRED API**
(`https://api.stlouisfed.org/fred`) plus the **GeoFRED / FRED Maps API**
(`https://api.stlouisfed.org/geofred`).

Global notes:
- Every request needs an `api_key` and `file_type=json`; both are injected
  automatically by `FredClient`. FRED rejects keyless requests, so a missing
  `FRED_API_KEY` raises a clear `FredError` **before** any network call.
- All endpoints are HTTP `GET`. The client retries `429`/`5xx` with
  exponential backoff (shared `turningbull_mcp.http.backoff_seconds`).
- List tools accept `mode` (`inline` default, or `summary` → CSV+Parquet
  under `$FRED_OUTPUT_DIR`) and `response_format` (`markdown` default, or
  `json`). Single-object tools accept only `response_format`.
- Common optional query params (passed through only when set):
  `realtime_start`, `realtime_end`, `limit`, `offset`, `order_by`,
  `sort_order` (`asc`/`desc`), plus tag/filter params where the endpoint
  supports them.

---

## Categories — `tools/categories.py`

| Tool | Endpoint | Key params | Result collection |
| --- | --- | --- | --- |
| `fred_get_category` | `/category` | `category_id` | `categories` (single) |
| `fred_get_category_children` | `/category/children` | `category_id` | `categories` |
| `fred_get_category_related` | `/category/related` | `category_id` | `categories` |
| `fred_get_category_series` | `/category/series` | `category_id`, `filter_variable`, `filter_value`, `tag_names`, `exclude_tag_names` | `seriess` |
| `fred_get_category_tags` | `/category/tags` | `category_id`, `tag_names`, `tag_group_id`, `search_text` | `tags` |
| `fred_get_category_related_tags` | `/category/related_tags` | `category_id`, `tag_names` (required), `exclude_tag_names` | `tags` |

## Releases — `tools/releases.py`

| Tool | Endpoint | Key params | Result collection |
| --- | --- | --- | --- |
| `fred_get_releases` | `/releases` | pagination | `releases` |
| `fred_get_releases_dates` | `/releases/dates` | `include_release_dates_with_no_data` | `release_dates` |
| `fred_get_release` | `/release` | `release_id` | `releases` (single) |
| `fred_get_release_dates` | `/release/dates` | `release_id` | `release_dates` |
| `fred_get_release_series` | `/release/series` | `release_id`, filter/tag params | `seriess` |
| `fred_get_release_sources` | `/release/sources` | `release_id` | `sources` |
| `fred_get_release_tags` | `/release/tags` | `release_id`, `tag_names`, `tag_group_id`, `search_text` | `tags` |
| `fred_get_release_related_tags` | `/release/related_tags` | `release_id`, `tag_names` (required) | `tags` |
| `fred_get_release_tables` | `/release/tables` | `release_id`, `element_id`, `include_observation_values`, `observation_date` | table tree |

## Series — `tools/series.py`

| Tool | Endpoint | Key params | Result collection |
| --- | --- | --- | --- |
| `fred_get_series` | `/series` | `series_id` | `seriess` (single) |
| `fred_get_series_categories` | `/series/categories` | `series_id` | `categories` |
| `fred_get_series_observations` | `/series/observations` | `series_id`, `observation_start`, `observation_end`, `units`, `frequency`, `aggregation_method`, `output_type`, `vintage_dates` | `observations` |
| `fred_get_series_release` | `/series/release` | `series_id` | `releases` (single) |
| `fred_search_series` | `/series/search` | `search_text` (required), `search_type`, filter/tag params | `seriess` |
| `fred_get_series_search_tags` | `/series/search/tags` | `series_search_text` (required) | `tags` |
| `fred_get_series_search_related_tags` | `/series/search/related_tags` | `series_search_text`, `tag_names` (both required) | `tags` |
| `fred_get_series_tags` | `/series/tags` | `series_id` | `tags` |
| `fred_get_series_updates` | `/series/updates` | `filter_value`, `start_time`, `end_time` | `seriess` |
| `fred_get_series_vintagedates` | `/series/vintagedates` | `series_id` | `vintage_dates` |

## Sources — `tools/sources.py`

| Tool | Endpoint | Key params | Result collection |
| --- | --- | --- | --- |
| `fred_get_sources` | `/sources` | pagination | `sources` |
| `fred_get_source` | `/source` | `source_id` | `sources` (single) |
| `fred_get_source_releases` | `/source/releases` | `source_id` | `releases` |

## Tags — `tools/tags.py`

| Tool | Endpoint | Key params | Result collection |
| --- | --- | --- | --- |
| `fred_get_tags` | `/tags` | `tag_names`, `tag_group_id`, `search_text` | `tags` |
| `fred_get_related_tags` | `/related_tags` | `tag_names` (required), `exclude_tag_names` | `tags` |
| `fred_get_tags_series` | `/tags/series` | `tag_names` (required), `exclude_tag_names` | `seriess` |

## GeoFRED / FRED Maps — `tools/maps.py`

These call the `https://api.stlouisfed.org/geofred` host via
`FredClient.geo_get`.

| Tool | Endpoint | Key params | Result |
| --- | --- | --- | --- |
| `fred_get_geofred_shapes` | `/shapes/file` | `shape` (e.g. `state`, `county`, `country`) | GeoJSON shapes |
| `fred_get_geofred_series_group` | `/series/group` | `series_id` | series-group metadata |
| `fred_get_geofred_series_data` | `/series/data` | `series_id`, `date`, `start_date` | regional values for a series |
| `fred_get_geofred_regional_data` | `/regional/data` | `series_group`, `region_type`, `date`, `season`, `units`, `transformation`, `frequency`, `aggregation_method` | regional values for a series group |

---

## Observation transforms (`units`)

`/series/observations` and `/regional/data` accept a value transform:

| Code | Meaning |
| --- | --- |
| `lin` | Levels (no transform, default) |
| `chg` | Change |
| `ch1` | Change from a year ago |
| `pch` | Percent change |
| `pc1` | Percent change from a year ago |
| `pca` | Compounded annual rate of change |
| `cch` | Continuously compounded rate of change |
| `cca` | Continuously compounded annual rate of change |
| `log` | Natural log |

## Response shape & rendering

Most FRED list endpoints return a paginated envelope:

```jsonc
{
  "realtime_start": "2026-05-31", "realtime_end": "2026-05-31",
  "order_by": "series_id", "sort_order": "asc",
  "count": 1234, "offset": 0, "limit": 1000,
  "seriess": [ /* or categories / releases / sources / tags / observations */ ]
}
```

Each tool extracts the relevant collection and renders it with the shared
`render_large_result` (lists) or `render_small_result` (single objects).
`fred_get_series_vintagedates` returns a bare `vintage_dates` string array,
which the tool wraps as `[{"vintage_date": ...}]` rows for tabular output.
