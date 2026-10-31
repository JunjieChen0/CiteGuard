import json
from pathlib import Path

import httpx
import pytest

from citeguard.http import FetchError, HttpClient
from citeguard.models import Author
from citeguard.sources import (
    ArxivSource,
    CrossrefSource,
    DoiOrgSource,
    OpenAlexSource,
    SemanticScholarSource,
    split_display_name,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


def make_http(handler) -> HttpClient:
    return HttpClient(httpx.Client(transport=httpx.MockTransport(handler)), min_interval={}, sleep=lambda s: None)


# ---------------------------------------------------------------- Crossref（真实录制的响应）

def test_crossref_get_by_doi_parses_metadata():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=fixture("cr_doi_resnet.json"))

    paper = CrossrefSource(make_http(handler), mailto="me@example.org").get_by_doi("10.1109/CVPR.2016.90")
    assert paper.title == "Deep Residual Learning for Image Recognition"
    assert paper.authors[0] == Author("He", "Kaiming")
    assert (paper.year, paper.pages, paper.doi, paper.source) == (2016, "770-778", "10.1109/cvpr.2016.90", "crossref")
    assert "CVPR" in paper.venue
    assert seen[0].url.path == "/works/10.1109/CVPR.2016.90"
    assert seen[0].url.params["mailto"] == "me@example.org"


def test_crossref_cleans_markup_in_titles():
    paper = CrossrefSource(make_http(lambda r: httpx.Response(200, json=fixture("cr_doi_frenkel_early.json")))
                           ).get_by_doi("10.1109/TBCAS.2018.2880425")
    assert paper.title.startswith("A 0.086-mm 2 12.7-pJ/SOP")
    assert "<" not in paper.title and "\n" not in paper.title


def test_crossref_get_by_doi_returns_none_when_missing():
    assert CrossrefSource(make_http(lambda r: httpx.Response(404))).get_by_doi("10.1/none") is None


def test_crossref_search_returns_papers_and_drops_components():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=fixture("cr_search_fabricated.json"))

    papers = CrossrefSource(make_http(handler)).search("Hierarchical Quantum Attention", limit=5)
    assert len(papers) == 4  # 第 5 条是 type=component（表格），丢弃
    assert seen[0].url.params["query.bibliographic"] == "Hierarchical Quantum Attention"
    assert seen[0].url.params["rows"] == "5"


# ---------------------------------------------------------------- doi.org（DataCite / arXiv DOI）

def test_doi_org_resolves_arxiv_doi_via_csl_json():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=fixture("csl_arxiv_attention.json"))

    paper = DoiOrgSource(make_http(handler)).get_by_doi("10.48550/arXiv.1706.03762")
    assert paper.title == "Attention Is All You Need"
    assert paper.authors[6] == Author("Kaiser", "Lukasz")
    assert (paper.year, paper.doi, paper.venue) == (2017, "10.48550/arxiv.1706.03762", "arXiv")
    assert seen[0].headers["Accept"] == "application/vnd.citationstyles.csl+json"
    assert DoiOrgSource(make_http(handler)).search("x") == []


# ---------------------------------------------------------------- OpenAlex（字段按官方文档手写）

OPENALEX_WORK = {
    "id": "https://openalex.org/W2194775991",
    "doi": "https://doi.org/10.1109/cvpr.2016.90",
    "title": "Deep Residual Learning for Image Recognition",
    "display_name": "Deep Residual Learning for Image Recognition",
    "publication_year": 2016,
    "authorships": [{"author": {"display_name": "Kaiming He"}}, {"author": {"display_name": "Xiangyu Zhang"}}],
    "primary_location": {"source": {"display_name": "2016 IEEE Conference on Computer Vision and Pattern Recognition"}},
    "biblio": {"first_page": "770", "last_page": "778"},
}


def test_openalex_get_by_doi_and_search_with_api_key():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.startswith("/works/doi:"):
            return httpx.Response(200, json=OPENALEX_WORK)
        return httpx.Response(200, json={"results": [OPENALEX_WORK, {**OPENALEX_WORK, "title": None, "display_name": None}]})

    source = OpenAlexSource(make_http(handler), api_key="k123")
    paper = source.get_by_doi("10.1109/CVPR.2016.90")
    assert paper.authors == [Author("He", "Kaiming"), Author("Zhang", "Xiangyu")]
    assert (paper.doi, paper.pages, paper.year, paper.source) == ("10.1109/cvpr.2016.90", "770-778", 2016, "openalex")
    assert len(source.search("Deep Residual Learning", limit=3)) == 1  # 无标题的记录被丢弃
    assert seen[1].url.params["search"] == "Deep Residual Learning"
    assert all(r.url.params["api_key"] == "k123" for r in seen)


# ---------------------------------------------------------------- Semantic Scholar（真实录制）

def test_semantic_scholar_match_found_and_not_found():
    def handler(request):
        rec = fixture("s2_match_tcmbench.json" if "TCMBench" in request.url.params["query"] else "s2_match_shennong.json")
        return httpx.Response(rec["status_code"], json=rec["body"])

    source = SemanticScholarSource(make_http(handler), api_key=None)
    found = source.search("TCMBench: A Comprehensive Benchmark for Evaluating Large Language Models in Traditional "
                          "Chinese Medicine")
    assert found[0].year == 2024 and found[0].doi == "10.48550/arxiv.2406.01126"
    assert found[0].authors[0] == Author("Yue", "Wenjing")
    assert source.search("ShenNong-TCM: A Traditional Chinese Medicine Large Language Model") == []


def test_semantic_scholar_sends_api_key_header_and_gets_by_doi():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"title": "T", "year": 2020, "authors": [{"name": "Ada Lovelace"}],
                                         "externalIds": {"DOI": "10.1/X"}, "venue": "V"})

    paper = SemanticScholarSource(make_http(handler), api_key="s2key").get_by_doi("10.1/X")
    assert paper.doi == "10.1/x" and paper.authors == [Author("Lovelace", "Ada")]
    assert seen[0].headers["x-api-key"] == "s2key"
    assert seen[0].url.path == "/graph/v1/paper/DOI:10.1/X"


# ---------------------------------------------------------------- arXiv（真实录制）

def test_arxiv_get_by_id_and_arxiv_doi():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text=fixture("arxiv_resnet.xml"))

    source = ArxivSource(make_http(handler))
    paper = source.get_by_id("1512.03385")
    assert paper.title == "Deep Residual Learning for Image Recognition"
    assert paper.authors[0] == Author("He", "Kaiming")
    assert (paper.year, paper.doi, paper.source) == (2015, "10.48550/arxiv.1512.03385", "arxiv")
    assert seen[0].url.params["id_list"] == "1512.03385"
    assert source.get_by_doi("10.48550/arxiv.1512.03385").title == paper.title
    assert source.get_by_doi("10.1109/cvpr.2016.90") is None


def test_arxiv_returns_none_for_empty_feed():
    empty = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    assert ArxivSource(make_http(lambda r: httpx.Response(200, text=empty))).get_by_id("9999.99999") is None


def test_source_propagates_fetch_errors():
    with pytest.raises(FetchError):
        CrossrefSource(make_http(lambda r: httpx.Response(403))).search("x")


@pytest.mark.parametrize(("name", "author"), [
    ("Kaiming He", Author("He", "Kaiming")),
    ("Jose M. Alvarez", Author("Alvarez", "Jose M.")),
    ("OpenAI", Author("OpenAI", "")),
    ("  ", Author("", "")),
])
def test_split_display_name(name, author):
    assert split_display_name(name) == author
