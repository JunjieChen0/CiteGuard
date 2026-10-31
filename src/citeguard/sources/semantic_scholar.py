from __future__ import annotations

from citeguard.http import HttpClient
from citeguard.models import Paper
from citeguard.sources.base import clean_title, normalize_doi, split_display_name

FIELDS = "title,authors,year,venue,externalIds"


class SemanticScholarSource:
    """标题最佳匹配接口：找不到时返回 404，可作为"不存在"的佐证。无 Key 时共享限流池，容易 429。"""

    name = "semantic_scholar"
    base_url = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, http: HttpClient, api_key: str | None = None) -> None:
        self._http = http
        self._headers = {"x-api-key": api_key} if api_key else None

    def _to_paper(self, item: dict) -> Paper:
        return Paper(
            title=clean_title(item.get("title")),
            authors=[split_display_name(a.get("name", "")) for a in item.get("authors") or []],
            year=item.get("year"),
            venue=item.get("venue") or "",
            doi=normalize_doi((item.get("externalIds") or {}).get("DOI")),
            source=self.name,
        )

    def get_by_doi(self, doi: str) -> Paper | None:
        item = self._http.get_json(f"{self.base_url}/paper/DOI:{doi}", params={"fields": FIELDS},
                                   headers=self._headers)
        return self._to_paper(item) if item else None

    def search(self, query: str, limit: int = 5) -> list[Paper]:
        data = self._http.get_json(f"{self.base_url}/paper/search/match", params={"query": query, "fields": FIELDS},
                                   headers=self._headers) or {}
        return [self._to_paper(item) for item in data.get("data", [])[:limit]]
