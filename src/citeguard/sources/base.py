"""数据源的公共接口与解析工具。"""

from __future__ import annotations

import html
import re
from typing import Protocol

from citeguard.models import Author, Paper


class Source(Protocol):
    name: str

    def get_by_doi(self, doi: str) -> Paper | None: ...

    def search(self, query: str, limit: int = 5) -> list[Paper]: ...


def clean_title(raw: str | None) -> str:
    text = html.unescape(html.unescape(raw or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\$\^?\{?([^$}]*)\}?\$", r"\1", text)
    return " ".join(text.split())


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE).lower()


def split_display_name(name: str) -> Author:
    parts = name.split()
    if not parts:
        return Author("", "")
    return Author(parts[-1], " ".join(parts[:-1]))


def csl_year(record: dict) -> int | None:
    for key in ("issued", "published-print", "published-online", "published"):
        parts = (record.get(key) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def first(value) -> str:
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def csl_to_paper(record: dict, source: str) -> Paper:
    """Crossref 的 message 与 doi.org 返回的 CSL-JSON 字段基本一致。"""
    authors = [
        Author(a.get("family") or a.get("literal") or a.get("name", ""), a.get("given", ""))
        for a in record.get("author", [])
    ]
    return Paper(
        title=clean_title(first(record.get("title"))),
        authors=authors,
        year=csl_year(record),
        venue=clean_title(first(record.get("container-title")) or record.get("publisher", "")),
        doi=normalize_doi(record.get("DOI")),
        pages=record.get("page"),
        source=source,
        volume=record.get("volume"),
        issue=record.get("issue"),
    )
