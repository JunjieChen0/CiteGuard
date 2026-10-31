from __future__ import annotations

from citeguard.http import HttpClient
from citeguard.models import Paper
from citeguard.sources.base import clean_title, normalize_doi, split_display_name


class OpenAlexSource:
    """第二数据源。无 Key 时同一 IP 共享每日额度（实测会被耗尽），建议配置 OPENALEX_API_KEY。"""

    name = "openalex"
    base_url = "https://api.openalex.org"

    def __init__(self, http: HttpClient, api_key: str | None = None) -> None:
        self._http = http
        self._params = {"api_key": api_key} if api_key else {}

    def _to_paper(self, work: dict) -> Paper:
        biblio = work.get("biblio") or {}
        first_page, last_page = biblio.get("first_page"), biblio.get("last_page")
        source = ((work.get("primary_location") or {}).get("source") or {})
        return Paper(
            title=clean_title(work.get("title") or work.get("display_name")),
            authors=[split_display_name((a.get("author") or {}).get("display_name", ""))
                     for a in work.get("authorships", [])],
            year=work.get("publication_year"),
            venue=source.get("display_name") or "",
            doi=normalize_doi(work.get("doi")),
            pages=f"{first_page}-{last_page}" if first_page and last_page else first_page,
            source=self.name,
            volume=biblio.get("volume"),
            issue=biblio.get("issue"),
        )

    def get_by_doi(self, doi: str) -> Paper | None:
        work = self._http.get_json(f"{self.base_url}/works/doi:{doi}", params=self._params)
        return self._to_paper(work) if work else None

    def search(self, query: str, limit: int = 5) -> list[Paper]:
        data = self._http.get_json(f"{self.base_url}/works", params={**self._params, "search": query,
                                                                     "per-page": str(limit)}) or {}
        return [self._to_paper(w) for w in data.get("results", []) if w.get("title") or w.get("display_name")]
