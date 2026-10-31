from __future__ import annotations

from urllib.parse import quote

from citeguard.http import HttpClient
from citeguard.models import Paper
from citeguard.sources.base import csl_to_paper

CSL_ACCEPT = "application/vnd.citationstyles.csl+json"


class DoiOrgSource:
    """通过 doi.org 内容协商解析任意注册机构的 DOI（Crossref 查不到的 DataCite/arXiv DOI 走这里）。"""

    name = "doi.org"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def get_by_doi(self, doi: str) -> Paper | None:
        data = self._http.get_json(f"https://doi.org/{quote(doi, safe='/()')}", headers={"Accept": CSL_ACCEPT})
        return csl_to_paper(data, self.name) if data else None

    def search(self, query: str, limit: int = 5) -> list[Paper]:
        return []
