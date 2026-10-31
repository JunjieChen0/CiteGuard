import json
from pathlib import Path

from citeguard.checker import Checker, build_default_checker
from citeguard.http import FetchError
from citeguard.models import Author, Paper, Severity, Status
from citeguard.parser import parse_reference
from citeguard.sources.base import csl_to_paper

FIXTURES = Path(__file__).parent / "fixtures"


def cr(name: str) -> Paper:
    return csl_to_paper(json.loads((FIXTURES / name).read_text(encoding="utf-8"))["message"], "crossref")


def cr_search(name: str) -> list[Paper]:
    items = json.loads((FIXTURES / name).read_text(encoding="utf-8"))["message"]["items"]
    return [csl_to_paper(i, "crossref") for i in items]


class FakeSource:
    def __init__(self, name, by_doi=None, search=None, fail=False):
        self.name = name
        self.by_doi = {k.lower(): v for k, v in (by_doi or {}).items()}
        self.search_results = search or {}
        self.fail = fail
        self.doi_calls: list[str] = []
        self.search_calls: list[str] = []

    def get_by_doi(self, doi):
        self.doi_calls.append(doi)
        if self.fail:
            raise FetchError(f"{self.name} down")
        return self.by_doi.get(doi.lower())

    def search(self, query, limit=5):
        self.search_calls.append(query)
        if self.fail:
            raise FetchError(f"{self.name} down")
        for key, papers in self.search_results.items():
            if key.lower() in query.lower():
                return papers[:limit]
        return []


def checker(crossref=None, doi_org=None, openalex=None, s2=None, arxiv=None):
    return Checker(
        crossref=crossref or FakeSource("crossref"),
        doi_org=doi_org or FakeSource("doi.org"),
        search_sources=[s for s in (openalex, s2) if s is not None],
        arxiv=arxiv,
    )


def fields(result):
    return [(d.field, d.severity) for d in result.diffs if d.severity is not Severity.INFO]


RESNET = ("He, K., Zhang, X., Ren, S., Sun, J. Deep Residual Learning for Image Recognition. In: CVPR, 2016. "
          "DOI: 10.1109/CVPR.2016.90")
RESNEXT_WRONG_DOI = ("Xie, S., Girshick, R., Dollár, P., Tu, Z., He, K. Aggregated Residual Transformations for Deep "
                     "Neural Networks. In: CVPR, 2017. DOI: 10.1109/CVPR.2017.317")


def test_verified_when_doi_title_authors_year_match():
    c = FakeSource("crossref", by_doi={"10.1109/cvpr.2016.90": cr("cr_doi_resnet.json")})
    result = checker(crossref=c).check(parse_reference(RESNET))
    assert result.status is Status.VERIFIED
    assert result.matched.doi == "10.1109/cvpr.2016.90"
    assert c.search_calls == []  # DOI 已确认，不再检索


def test_doi_pointing_to_another_paper_is_major_and_suggests_correct_doi():
    # 案例 01/02
    c = FakeSource("crossref", by_doi={"10.1109/cvpr.2017.317": cr("cr_doi_cvpr2017_317.json")},
                   search={"Aggregated Residual": cr_search("cr_search_resnext.json")})
    result = checker(crossref=c).check(parse_reference(RESNEXT_WRONG_DOI))
    assert result.status is Status.MISMATCH
    assert fields(result) == [("doi", Severity.MAJOR)]
    doi_diff = result.diffs[0]
    assert "Low-Rank-Sparse Subspace Representation" in doi_diff.message
    assert doi_diff.actual == "10.1109/cvpr.2017.634"
    assert result.matched.title == "Aggregated Residual Transformations for Deep Neural Networks"


def test_unresolvable_doi_with_existing_title_is_mismatch():
    c = FakeSource("crossref", search={"Aggregated Residual": cr_search("cr_search_resnext.json")})
    ref = parse_reference(RESNEXT_WRONG_DOI.replace("10.1109/CVPR.2017.317", "10.9999/fake.1"))
    result = checker(crossref=c).check(ref)
    assert result.status is Status.MISMATCH
    assert "无法解析" in result.diffs[0].message and result.diffs[0].actual == "10.1109/cvpr.2017.634"


def test_fabricated_authors_detected():
    # 案例 03
    c = FakeSource("crossref", by_doi={"10.1093/nar/gky987": cr("cr_doi_etcm.json")})
    ref = parse_reference("Xu H Y, Zhang Y Q, Liu Z M, Chen T, Chai C Y, Li R L, et al. ETCM: an encyclopaedia of "
                          "traditional Chinese medicine. Nucleic Acids Research, 2019, 47(D1): D976–D982. "
                          "DOI: 10.1093/nar/gky987")
    result = checker(crossref=c).check(ref)
    assert result.status is Status.MISMATCH
    assert fields(result) == [("authors", Severity.MAJOR), ("authors", Severity.MAJOR)]


def test_fabricated_paper_not_found_with_candidates():
    c = FakeSource("crossref", search={"Hierarchical Quantum": cr_search("cr_search_fabricated.json")})
    s2 = FakeSource("semantic_scholar")
    ref = parse_reference("Smith J., Lee K. Hierarchical Quantum Attention Networks for Few-shot Botanical "
                          "Segmentation. CVPR, 2023.")
    result = checker(crossref=c, s2=s2).check(ref)
    assert result.status is Status.NOT_FOUND
    assert result.matched is None
    assert 1 <= len(result.candidates) <= 3
    assert s2.search_calls  # Crossref 没找到时继续查其他数据源


def test_all_sources_failing_gives_unknown_not_not_found():
    down = FakeSource("crossref", fail=True)
    result = checker(crossref=down, doi_org=FakeSource("doi.org", fail=True),
                     openalex=FakeSource("openalex", fail=True)).check(parse_reference(RESNET))
    assert result.status is Status.UNKNOWN
    assert "crossref down" in result.note


def test_partial_failure_falls_back_to_next_source():
    openalex = FakeSource("openalex", search={"Deep Residual": [cr("cr_doi_resnet.json")]})
    ref = parse_reference("He, K., Zhang, X., et al. Deep Residual Learning for Image Recognition. CVPR, 2016.")
    result = checker(crossref=FakeSource("crossref", fail=True), openalex=openalex).check(ref)
    assert result.status is Status.VERIFIED
    assert "crossref down" in result.note


def test_not_found_when_some_sources_fail_mentions_failures():
    c = FakeSource("crossref", search={"Hierarchical": cr_search("cr_search_fabricated.json")})
    ref = parse_reference("Hierarchical Quantum Attention Networks for Few-shot Botanical Segmentation. 2023.")
    result = checker(crossref=c, openalex=FakeSource("openalex", fail=True)).check(ref)
    assert result.status is Status.NOT_FOUND
    assert "openalex" in result.note


ARXIV_PAPER = Paper("CSWin Transformer: A General Vision Transformer Backbone with Cross-Shaped Windows",
                    [Author("Dong", "Xiaoyi"), Author("Bao", "Jianmin"), Author("Chen", "Dongdong"),
                     Author("Zhang", "Weiming")], 2021, "arXiv", "10.48550/arxiv.2107.00652", None, "doi.org")
CVPR_PAPER = Paper("CSWin Transformer: A General Vision Transformer Backbone with Cross-Shaped Windows",
                   ARXIV_PAPER.authors, 2022, "CVPR", "10.1109/cvpr52688.2022.01181", "12114-12124", "crossref")


def test_arxiv_doi_resolved_via_doi_org_and_compared_with_published_version():
    c = FakeSource("crossref", search={"CSWin": [CVPR_PAPER]})
    d = FakeSource("doi.org", by_doi={"10.48550/arxiv.2107.00652": ARXIV_PAPER})
    ref = parse_reference("Xiaoyi Dong, Jianmin Bao, Dongdong Chen, Weining Zhang. CSWin Transformer: A General "
                          "Vision Transformer Backbone with Cross-Shaped Windows[C]//CVPR. 2022: 12124–12134. "
                          "DOI: 10.48550/arXiv.2107.00652.")
    result = checker(crossref=c, doi_org=d).check(ref)
    assert c.doi_calls == []  # arXiv DOI 直接走 doi.org
    assert result.status is Status.MISMATCH
    assert sorted(fields(result)) == [("authors", Severity.MINOR), ("pages", Severity.MINOR)]
    info = [d.message for d in result.diffs if d.severity is Severity.INFO]
    assert any("10.1109/cvpr52688.2022.01181" in m for m in info)
    assert result.matched.doi == "10.1109/cvpr52688.2022.01181"


def test_arxiv_id_lookup_when_no_doi():
    arxiv = FakeSource("arxiv")
    arxiv.get_by_id = lambda arxiv_id: ARXIV_PAPER if arxiv_id == "2107.00652" else None
    ref = parse_reference("Xiaoyi Dong, Jianmin Bao, et al. CSWin Transformer: A General Vision Transformer Backbone with "
                          "Cross-Shaped Windows. arXiv:2107.00652, 2021.")
    result = checker(arxiv=arxiv).check(ref)
    assert result.status is Status.VERIFIED
    assert result.matched.doi == "10.48550/arxiv.2107.00652"


def test_subtitle_differs_is_title_mismatch_with_alternatives():
    # 案例 05 Zhongjing：Crossref 返回两篇同名前缀的论文
    c = FakeSource("crossref", search={"Zhongjing": cr_search("cr_search_zhongjing.json")})
    ref = parse_reference("Zhongjing: A Chinese Medical Large Language Model. arXiv 预印本，2024.")
    result = checker(crossref=c).check(ref)
    assert result.status is Status.MISMATCH
    assert fields(result) == [("title", Severity.MAJOR)]
    dois = {result.matched.doi} | {p.doi for p in result.candidates}
    assert {"10.1609/aaai.v38i17.29907", "10.1145/3644116.3644294"} <= dois


def test_title_only_reference_found_suggests_doi():
    qibo = Paper("Qibo: A Large Language Model for traditional Chinese medicine", [Author("Jia", "Heyi")], 2025,
                 "Expert Systems with Applications", "10.1016/j.eswa.2025.127672", None, "crossref")
    c = FakeSource("crossref", search={"Qibo": [qibo]})
    result = checker(crossref=c).check(parse_reference("Qibo: A Large Language Model for Traditional Chinese "
                                                       "Medicine. arXiv 预印本，2024."))
    assert result.status is Status.VERIFIED
    assert any("10.1016/j.eswa.2025.127672" in d.message for d in result.diffs if d.severity is Severity.INFO)


def test_truncated_database_title_is_verified_with_info():
    c = FakeSource("crossref", by_doi={"10.1145/3298981": cr("cr_doi_fedml_truncated.json")})
    ref = parse_reference("Yang, Q., Liu, Y., Chen, T., Tong, Y. Federated machine learning: Concept and applications. "
                          "*ACM Transactions on Intelligent Systems and Technology*, 2019. DOI: 10.1145/3298981")
    result = checker(crossref=c).check(ref)
    assert result.status is Status.VERIFIED
    assert any(d.field == "title" for d in result.diffs)


def test_early_access_record_does_not_flag_pages_or_year():
    c = FakeSource("crossref", by_doi={"10.1109/tbcas.2018.2880425": cr("cr_doi_frenkel_early.json")})
    ref = parse_reference('Frenkel, C., Lefebvre, M., Legat, J.-D., Bol, D. "A 0.086-mm² 12.7-pJ/SOP 64k-Synapse '
                          '256-Neuron Online-Learning Digital Spiking Neuromorphic Processor in 28-nm CMOS." *IEEE '
                          'Transactions on Biomedical Circuits and Systems*, 13(1), 145–158, 2019. '
                          'DOI: 10.1109/TBCAS.2018.2880425')
    assert checker(crossref=c).check(ref).status is Status.VERIFIED


def test_fastvit_given_name_errors_against_published_version():
    c = FakeSource("crossref", search={"FastViT": [cr("cr_doi_fastvit.json")]})
    arxiv_fastvit = Paper("FastViT: A Fast Hybrid Vision Transformer using Structural Reparameterization",
                          cr("cr_doi_fastvit.json").authors, 2023, "arXiv", "10.48550/arxiv.2303.14189", None, "doi.org")
    d = FakeSource("doi.org", by_doi={"10.48550/arxiv.2303.14189": arxiv_fastvit})
    ref = parse_reference("Pavan Kumar Anasosalu Vasu, James Gabrielsson, Chunuan Zhu, Oncel Tuzel, Anurag Ranjan. "
                          "FastViT: A Fast Hybrid Vision Transformer using Structural Reparameterization[C]//ICCV. "
                          "2023. DOI: 10.48550/arXiv.2303.14189.")
    result = checker(crossref=c, doi_org=d).check(ref)
    assert result.status is Status.MISMATCH
    assert fields(result) == [("authors", Severity.MAJOR), ("authors", Severity.MINOR)]


def test_check_text_checks_every_reference():
    c = FakeSource("crossref", by_doi={"10.1109/cvpr.2016.90": cr("cr_doi_resnet.json")})
    text = f"正文。\n\n参考文献\n\n1. {RESNET}\n2. Hierarchical Quantum Attention Networks. 2023.\n"
    results = checker(crossref=c).check_text(text)
    assert [r.status for r in results] == [Status.VERIFIED, Status.NOT_FOUND]


def test_build_default_checker_reads_keys_from_env(tmp_path):
    env = {"OPENALEX_API_KEY": "oa", "S2_API_KEY": "s2", "CROSSREF_MAILTO": "a@b.c"}
    built = build_default_checker(cache_dir=tmp_path, environ=env)
    assert [s.name for s in built.search_sources] == ["openalex", "semantic_scholar"]
    assert built.crossref._params == {"mailto": "a@b.c"}
    assert built.search_sources[0]._params == {"api_key": "oa"}
    assert built.search_sources[1]._headers == {"x-api-key": "s2"}
    assert built.arxiv is not None


def test_falls_back_to_main_title_search_when_subtitle_is_mangled():
    # 案例 05 PresRecST：Agent 把副标题写成了中文意译，全标题检索不到
    real = Paper("PresRecST: a novel herbal prescription recommendation algorithm for real-world patients with "
                 "integration of syndrome differentiation and treatment planning", [Author("Dong", "Xin")], 2024,
                 "JAMIA", "10.1093/jamia/ocae066", None, "crossref")
    c = FakeSource("crossref", search={"PresRecST": [real]})
    c.search_results = {}
    c.search = lambda query, limit=5: [real] if query == "PresRecST" else []
    result = checker(crossref=c).check(parse_reference("PresRecST: 面向中草药处方推荐的序列推荐方法. 2022."))
    assert result.status is Status.MISMATCH
    assert sorted(fields(result)) == [("title", Severity.MAJOR), ("year", Severity.MINOR)]
    assert result.matched.doi == "10.1093/jamia/ocae066"
