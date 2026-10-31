from citeguard.models import Author, Diff, Paper, Reference, Result, Severity, Status
from citeguard.report import format_paper, format_report, summarize

RESNEXT = Paper("Aggregated Residual Transformations for Deep Neural Networks",
                [Author("Xie", "Saining"), Author("Girshick", "Ross"), Author("Dollar", "Piotr"), Author("Tu", "Zhuowen"),
                 Author("He", "Kaiming")], 2017, "CVPR", "10.1109/cvpr.2017.634", "5987-5995", "crossref")


def ref(title, raw=None):
    return Reference(raw=raw or title, title=title)


def test_format_paper_full_citation():
    assert format_paper(RESNEXT) == ("Saining Xie, Ross Girshick, Piotr Dollar, Zhuowen Tu, Kaiming He. Aggregated "
                                     "Residual Transformations for Deep Neural Networks. CVPR, 2017, 5987-5995. "
                                     "DOI: 10.1109/cvpr.2017.634")


def test_format_paper_truncates_long_author_lists_and_skips_missing_fields():
    many = Paper("T", [Author(f"F{i}", "G") for i in range(12)], None, "", None, None, "crossref")
    assert format_paper(many) == "G F0, G F1, G F2, G F3, G F4, G F5, G F6, G F7, G F8, G F9, G F10, G F11. T."


def test_summarize_counts():
    results = [Result(ref("a"), Status.VERIFIED), Result(ref("b"), Status.MISMATCH), Result(ref("c"), Status.MISMATCH),
               Result(ref("d"), Status.NOT_FOUND), Result(ref("e"), Status.UNKNOWN)]
    assert summarize(results) == {"total": 5, "VERIFIED": 1, "MISMATCH": 2, "NOT_FOUND": 1, "UNKNOWN": 1}


def test_report_for_mismatch_lists_problems_and_corrected_citation():
    diff = Diff("doi", "10.1109/cvpr.2017.317", "10.1109/cvpr.2017.634", Severity.MAJOR,
                "DOI 10.1109/cvpr.2017.317 指向另一篇论文：《Low-Rank…》；正确 DOI 应为 10.1109/cvpr.2017.634")
    report = format_report([Result(ref("Aggregated Residual Transformations for Deep Neural Networks"),
                                   Status.MISMATCH, RESNEXT, [diff])])
    assert "[1] ⚠️ MISMATCH" in report
    assert "指向另一篇论文" in report
    assert "建议改为" in report and "DOI: 10.1109/cvpr.2017.634" in report
    assert "再次调用 verify_references" in report


def test_report_for_not_found_offers_candidates_and_warns_about_relevance():
    result = Result(ref("Hierarchical Quantum Attention Networks"), Status.NOT_FOUND, candidates=[RESNEXT])
    report = format_report([result])
    assert "[1] ❌ NOT_FOUND" in report
    assert "删除" in report and "Aggregated Residual" in report
    assert "相关" in report  # 提醒 Agent 只能换成与正文相关的文献


def test_report_for_verified_is_compact_but_keeps_info():
    info = Diff("doi", "", "10.1109/x", Severity.INFO, "该论文已正式发表于 CVPR（2022），DOI 10.1109/x")
    report = format_report([Result(ref("Good Paper"), Status.VERIFIED, RESNEXT, [info])])
    assert "[1] ✅ VERIFIED" in report and "已正式发表" in report
    assert "建议改为" not in report


def test_report_for_unknown_says_not_verified_rather_than_fabricated():
    report = format_report([Result(ref("X"), Status.UNKNOWN, note="数据源请求失败：timeout")])
    assert "[1] ❓ UNKNOWN" in report and "未核验" in report and "timeout" in report


def test_report_all_verified_says_done():
    report = format_report([Result(ref("Good Paper"), Status.VERIFIED, RESNEXT)])
    assert "全部通过" in report
    assert "再次调用" not in report


def test_report_when_no_references_found_explains_expected_format():
    report = format_report([])
    assert "没有识别到参考文献" in report and "参考文献" in report and "[1]" in report


def test_report_marks_severity_of_each_problem():
    diffs = [Diff("authors", "a", "b", Severity.MAJOR, "第 5 作者 X 不在作者列表中"),
             Diff("pages", "1-2", "3-4", Severity.MINOR, "页码不符：1-2 → 3-4")]
    report = format_report([Result(ref("T"), Status.MISMATCH, RESNEXT, diffs)])
    assert "严重" in report and "次要" in report


def test_format_paper_includes_volume_and_issue():
    paper = Paper("Res2Net: A New Multi-Scale Backbone Architecture", [Author("Gao", "Shang-Hua")], 2021,
                  "IEEE TPAMI", "10.1109/tpami.2019.2938758", "652-662", "crossref", volume="43", issue="2")
    assert format_paper(paper).endswith("IEEE TPAMI, 2021, 43(2): 652-662. DOI: 10.1109/tpami.2019.2938758")
    no_pages = Paper("T", [], 2020, "J", None, None, "crossref", volume="11")
    assert format_paper(no_pages) == "T. J, 2020, 11."


def test_format_paper_lists_up_to_twenty_authors():
    paper = Paper("T", [Author(f"F{i}", "G") for i in range(12)], 2020, "V", None, None, "crossref")
    assert "G F11" in format_paper(paper) and "et al" not in format_paper(paper)
    huge = Paper("T", [Author(f"F{i}", "G") for i in range(281)], 2023, "V", None, None, "crossref")
    assert format_paper(huge).count(",") < 30 and "et al" in format_paper(huge)
