from __future__ import annotations

from urllib.parse import quote

from citeguard.http import HttpClient
from citeguard.models import Paper
from citeguard.sources.base import csl_to_paper

_SKIP_TYPES = {"component", "peer-review", "grant"}


class CrossrefSource:
    """主数据源。传入 mailto 可进入 Crossref 的"礼貌池"。"""

    name = "crossref"
    base_url = "https://api.crossref.org"

    def __init__(self, http: HttpClient, mailto: str | None = None) -> None:
        self._http = http
        self._params = {"mailto": mailto} if mailto else {}

    def get_by_doi(self, doi: str) -> Paper | None:
        data = self._http.get_json(f"{self.base_url}/works/{quote(doi, safe='/()')}", params=self._params)
        return csl_to_paper(data["message"], self.name) if data else None

    def search(self, query: str, limit: int = 5, from_year: int | None = None) -> list[Paper]:
        params = {**self._params, "query.bibliographic": query, "rows": str(limit)}
        if from_year:
            params["filter"] = f"from-pub-date:{from_year}"
        data = self._http.get_json(f"{self.base_url}/works", params=params, rate_key="api.crossref.org/search") or {}
        items = (data.get("message") or {}).get("items", [])
        return [csl_to_paper(item, self.name) for item in items if item.get("type") not in _SKIP_TYPES]
