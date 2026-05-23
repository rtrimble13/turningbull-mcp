"""Response formatting helpers (markdown / json) shared across connectors."""

from __future__ import annotations

import json
from typing import Any

from .models import ResponseFormat


def render(data: Any, fmt: ResponseFormat, *, title: str | None = None) -> str:
    """Render a response payload in the requested format.

    JSON mode pretty-prints. Markdown mode renders lists of dicts as tables
    and falls back to JSON-in-a-fenced-block for other shapes.
    """
    if fmt == ResponseFormat.json:
        return json.dumps(data, indent=2, default=str)

    if isinstance(data, list) and data and all(isinstance(r, dict) for r in data):
        return _md_table(data, title=title)
    if isinstance(data, dict):
        return _md_keyvals(data, title=title)
    return _wrap_md(json.dumps(data, indent=2, default=str), title=title)


def _wrap_md(body: str, *, title: str | None) -> str:
    if title:
        return f"### {title}\n\n```\n{body}\n```"
    return body


def _md_keyvals(d: dict, *, title: str | None) -> str:
    lines = []
    if title:
        lines.append(f"### {title}\n")
    for k, v in d.items():
        lines.append(f"- **{k}**: {v}")
    return "\n".join(lines)


def _md_table(rows: list[dict], *, title: str | None, max_rows: int = 50) -> str:
    columns: list[str] = []
    seen: set[str] = set()
    for r in rows[:max_rows]:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)

    head = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body_lines = []
    for r in rows[:max_rows]:
        cells = [_cell(r.get(c)) for c in columns]
        body_lines.append("| " + " | ".join(cells) + " |")

    lines = []
    if title:
        lines.append(f"### {title}\n")
    lines.append(head)
    lines.append(sep)
    lines.extend(body_lines)
    if len(rows) > max_rows:
        lines.append(
            f"\n_…{len(rows) - max_rows} more rows omitted; use response_format=json or mode=summary for full data._"
        )
    return "\n".join(lines)


def _cell(v: Any) -> str:
    if v is None:
        return ""
    s = str(v)
    s = s.replace("|", "\\|").replace("\n", " ")
    return s
