from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from citeguard.http import HttpClient
from citeguard.models import Paper
from citeguard.sources.base import clean_title, split_display_name

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(\d{4}\.\d{4,5})$", re.IGNORECASE)


class ArxivSource:
    """只用于带 arXiv 编号的条目（限流严格：≥3 秒一次）。"""

    name = "arxiv"
    base_url = "https://export.arxiv.org/api/query"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def get_by_id(self, arxiv_id: str) -> Paper | None:
        text = self._http.get_text(self.base_url, params={"id_list": arxiv_id})
        if not text:
            return None
        entry = ET.fromstring(text).find(f"{_ATOM}entry")
        if entry is None or entry.find(f"{_ATOM}title") is None:
            return None
        published = entry.findtext(f"{_ATOM}published", "")
        return Paper(
            title=clean_title(entry.findtext(f"{_ATOM}title")),
            authors=[split_display_name(a.findtext(f"{_ATOM}name", "")) for a in entry.findall(f"{_ATOM}author")],
            year=int(published[:4]) if published[:4].isdigit() else None,
            venue="arXiv",
            doi=f"10.48550/arxiv.{arxiv_id}",
            source=self.name,
        )

    def get_by_doi(self, doi: str) -> Paper | None:
        m = _ARXIV_DOI_RE.match(doi)
        return self.get_by_id(m.group(1)) if m else None

    def search(self, query: str, limit: int = 5) -> list[Paper]:
        return []
