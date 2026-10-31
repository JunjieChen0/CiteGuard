"""文献数据源：Crossref、doi.org、OpenAlex、Semantic Scholar、arXiv。"""

from citeguard.sources.arxiv import ArxivSource
from citeguard.sources.base import Source, clean_title, normalize_doi, split_display_name
from citeguard.sources.crossref import CrossrefSource
from citeguard.sources.doi_org import DoiOrgSource
from citeguard.sources.openalex import OpenAlexSource
from citeguard.sources.semantic_scholar import SemanticScholarSource

__all__ = [
    "ArxivSource",
    "CrossrefSource",
    "DoiOrgSource",
    "OpenAlexSource",
    "SemanticScholarSource",
    "Source",
    "clean_title",
    "normalize_doi",
    "split_display_name",
]
