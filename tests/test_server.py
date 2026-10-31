import asyncio

from citeguard.checker import Checker
from citeguard.models import Author, Paper
from citeguard.server import create_server, search_papers
from tests.test_checker import FakeSource

RESNET = Paper("Deep Residual Learning for Image Recognition", [Author("He", "Kaiming"), Author("Zhang", "Xiangyu")],
               2016, "CVPR", "10.1109/cvpr.2016.90", "770-778", "crossref")
NO_AUTHORS = Paper("Table 1", [], 2020, "", "10.1/table", None, "crossref")


class SearchSpy(FakeSource):
    def __init__(self):
        super().__init__("crossref", by_doi={"10.1109/cvpr.2016.90": RESNET})
        self.calls = []

    def search(self, query, limit=5, from_year=None):
        self.calls.append((query, limit, from_year))
        return [RESNET, NO_AUTHORS, RESNET]


def make_server():
    crossref = SearchSpy()
    server = create_server(Checker(crossref=crossref, doi_org=FakeSource("doi.org"), max_workers=1), crossref)
    return server, crossref


def call(server, name, args):
    result = asyncio.run(server.call_tool(name, args))
    assert not result.is_error, result
    return result.content[0].text


def test_server_exposes_two_tools_with_chinese_descriptions():
    server, _ = make_server()
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == {"verify_references", "search_papers"}
    assert "参考文献" in tools["verify_references"].description
    assert "真实" in tools["search_papers"].description


def test_verify_references_tool_returns_report():
    server, _ = make_server()
    text = ("参考文献\n\n1. He, K., Zhang, X. Deep Residual Learning for Image Recognition. CVPR, 2016. "
            "DOI: 10.1109/CVPR.2016.90\n")
    report = call(server, "verify_references", {"text": text})
    assert "CiteGuard 核查报告" in report and "✅ VERIFIED" in report


def test_search_papers_tool_dedupes_and_drops_records_without_authors():
    server, crossref = make_server()
    text = call(server, "search_papers", {"query": "residual learning", "limit": 3, "from_year": 2015})
    assert crossref.calls == [("residual learning", 6, 2015)]
    assert text.count("Deep Residual Learning") == 1
    assert "Table 1" not in text
    assert "DOI: 10.1109/cvpr.2016.90" in text


def test_search_papers_reports_empty_and_errors():
    class Empty(SearchSpy):
        def search(self, query, limit=5, from_year=None):
            return []

    class Down(SearchSpy):
        def search(self, query, limit=5, from_year=None):
            from citeguard.http import FetchError
            raise FetchError("crossref down")

    assert "没有找到" in search_papers(Empty(), "x")
    assert "暂时不可用" in search_papers(Down(), "x")


def test_search_papers_limit_is_clamped():
    crossref = SearchSpy()
    search_papers(crossref, "x", limit=500)
    assert crossref.calls[0][1] == 40
