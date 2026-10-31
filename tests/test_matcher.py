import pytest

from citeguard.matcher import (
    TitleMatch,
    compare_authors,
    compare_pages,
    compare_titles,
    compare_year,
    decide_status,
    normalize_title,
)
from citeguard.models import Author, Diff, Severity, Status


# ---------------------------------------------------------------- 标题

def test_normalize_title_strips_markup_accents_and_punctuation():
    raw = "A 0.086-mm&lt;formula&gt;&lt;tex&gt;$^2$&lt;/tex&gt;&lt;/formula&gt; 12.7-pJ/SOP <i>Processor</i> — Veličković"
    assert normalize_title(raw) == "a 0 086 mm 2 12 7 pj sop processor velickovic"


def test_compare_titles_same_ignoring_case_and_punctuation():
    match, score = compare_titles("Deep residual learning for image recognition.",
                                  "Deep Residual Learning for Image Recognition")
    assert match is TitleMatch.SAME and score == 1.0


def test_compare_titles_tolerates_small_typos():
    assert compare_titles("Spatio-temporal backpropagation for training high-performance spiking neural networks",
                          "Spatio-Temporal Backpropagation for Training High-Performance Spiking Neural Networks"
                          )[0] is TitleMatch.SAME


def test_compare_titles_claimed_omits_subtitle():
    match, _ = compare_titles(
        "Surrogate Gradient Learning in Spiking Neural Networks",
        "Surrogate Gradient Learning in Spiking Neural Networks: Bringing the Power of Gradient-Based Optimization "
        "to Spiking Neural Networks",
    )
    assert match is TitleMatch.SAME_MAIN_TITLE


def test_compare_titles_database_title_truncated():
    # Crossref 中 10.1145/3298981 的标题被截断为 "Federated Machine Learning"
    match, _ = compare_titles("Federated machine learning: Concept and applications", "Federated Machine Learning")
    assert match is TitleMatch.SAME_MAIN_TITLE


def test_compare_titles_claimed_adds_model_name_prefix():
    match, _ = compare_titles("EfficientFormerV2: Rethinking Vision Transformers for MobileNet Size and Speed",
                              "Rethinking Vision Transformers for MobileNet Size and Speed")
    assert match is TitleMatch.SAME_MAIN_TITLE


def test_compare_titles_subtitle_differs():
    match, _ = compare_titles(
        "Zhongjing: A Chinese Medical Large Language Model",
        "Zhongjing: Enhancing the Chinese Medical Capabilities of Large Language Model through Expert Feedback and "
        "Real-world Multi-turn Dialogue",
    )
    assert match is TitleMatch.SUBTITLE_DIFFERS


def test_compare_titles_different_papers():
    match, score = compare_titles("Aggregated Residual Transformations for Deep Neural Networks",
                                  "Low-Rank-Sparse Subspace Representation for Robust Regression")
    assert match is TitleMatch.DIFFERENT and score < 0.6


def test_compare_titles_short_prefix_is_not_enough():
    # 只共享一个很短的前缀（如 "Graph"）不能算同一篇
    assert compare_titles("Graph", "Graph Attention Networks")[0] is TitleMatch.DIFFERENT


def test_compare_titles_fabricated_title_vs_nearest_search_hit():
    match, _ = compare_titles("Hierarchical Quantum Attention Networks for Few-shot Botanical Segmentation",
                              "Few-Shot Semantic Segmentation of Batik Patterns Using Attention Networks")
    assert match is TitleMatch.DIFFERENT


# ---------------------------------------------------------------- 作者

def _fields(diffs: list[Diff]) -> list[tuple[str, Severity]]:
    return [(d.field, d.severity) for d in diffs]


ETCM_DB = [Author("Xu", "Hai-Yu"), Author("Zhang", "Yan-Qiong"), Author("Liu", "Zhen-Ming"), Author("Chen", "Tong"),
           Author("Lv", "Chuan-Yu"), Author("Tang", "Shi-Huan"), Author("Zhang", "Xiao-Bo")]


def test_authors_all_match_with_initials():
    claimed = [Author("Xu", "H Y"), Author("Zhang", "Y Q"), Author("Liu", "Z M"), Author("Chen", "T")]
    assert compare_authors(claimed, True, ETCM_DB) == []


def test_authors_fabricated_tail_is_major():
    # 案例 03：前 4 位正确，第 5、6 位不存在
    claimed = [Author("Xu", "H Y"), Author("Zhang", "Y Q"), Author("Liu", "Z M"), Author("Chen", "T"),
               Author("Chai", "C Y"), Author("Li", "R L")]
    diffs = compare_authors(claimed, True, ETCM_DB)
    assert _fields(diffs) == [("authors", Severity.MAJOR), ("authors", Severity.MAJOR)]
    assert "Chai" in diffs[0].claimed and "Lv" in diffs[0].actual


FASTVIT_DB = [Author("Anasosalu Vasu", "Pavan Kumar"), Author("Gabriel", "James"), Author("Zhu", "Jeff"),
              Author("Tuzel", "Oncel"), Author("Ranjan", "Anurag")]


def test_authors_multi_word_family_names_match():
    claimed = [Author("Vasu", "Pavan Kumar Anasosalu"), Author("Gabriel", "James"), Author("Zhu", "Jeff"),
               Author("Tuzel", "Oncel"), Author("Ranjan", "Anurag")]
    assert compare_authors(claimed, False, FASTVIT_DB) == []


def test_authors_fabricated_given_or_family_names():
    # 案例 04：Gabrielsson（姓错）、Chunuan Zhu（名错）
    claimed = [Author("Vasu", "Pavan Kumar Anasosalu"), Author("Gabrielsson", "James"), Author("Zhu", "Chunuan"),
               Author("Tuzel", "Oncel"), Author("Ranjan", "Anurag")]
    diffs = compare_authors(claimed, False, FASTVIT_DB)
    assert _fields(diffs) == [("authors", Severity.MAJOR), ("authors", Severity.MINOR)]
    assert "Chunuan Zhu" in diffs[1].claimed and "Jeff Zhu" in diffs[1].actual


def test_authors_given_name_typo_is_minor():
    diffs = compare_authors([Author("Zhang", "Weining")], True, [Author("Zhang", "Weiming")])
    assert _fields(diffs) == [("authors", Severity.MINOR)]


def test_authors_missing_and_reordered():
    # 案例 04 EfficientFormerV2：漏 Salahi，Wang/Tulyakov 顺序颠倒
    db = [Author("Li", "Yanyu"), Author("Hu", "Ju"), Author("Salahi", "Kamyar"), Author("Wang", "Yanzhi"),
          Author("Tulyakov", "Sergey")]
    claimed = [Author("Li", "Yanyu"), Author("Hu", "Ju"), Author("Tulyakov", "Sergey"), Author("Wang", "Yanzhi")]
    diffs = compare_authors(claimed, False, db)
    messages = " ".join(d.message for d in diffs)
    assert all(d.severity is Severity.MINOR for d in diffs)
    assert "顺序" in messages and "Salahi" in messages


def test_authors_accents_case_particles_and_hyphens_are_ignored():
    claimed = [Author("Velickovic", "P."), Author("van der Maaten", "L."), Author("Chang", "M.-W."),
               Author("Xu", "Haiyu")]
    db = [Author("Veličković", "Petar"), Author("Van Der Maaten", "Laurens"), Author("Chang", "Ming-Wei"),
          Author("Xu", "Hai-Yu")]
    assert compare_authors(claimed, False, db) == []


def test_authors_skipped_when_database_has_none():
    assert compare_authors([Author("Smith", "J.")], False, []) == []


def test_authors_truncated_list_does_not_report_missing():
    assert compare_authors([Author("Kairouz", "P.")], True, [Author("Kairouz", "Peter"), Author("McMahan", "H.")]) == []


# ---------------------------------------------------------------- 年份、页码

@pytest.mark.parametrize(("claimed", "actual", "has_diff"), [
    (2016, 2016, False), (2015, 2016, False), (2019, 2018, False), (2022, 2024, True), (None, 2020, False),
    (2020, None, False),
])
def test_compare_year(claimed, actual, has_diff):
    assert bool(compare_year(claimed, actual)) is has_diff


@pytest.mark.parametrize(("claimed", "actual", "has_diff"), [
    ("12124-12134", "12114-12124", True),
    ("51-63", "51-63", False),
    ("D976-D982", "D976-D982", False),
    ("145-158", "1-1", False),  # Crossref 早期访问记录，页码不可信
    ("145-158", None, False),
    (None, "51-63", False),
    ("4171-4186", "4171–4186", False),
])
def test_compare_pages(claimed, actual, has_diff):
    assert bool(compare_pages(claimed, actual)) is has_diff


# ---------------------------------------------------------------- 状态

def test_decide_status():
    info = Diff("doi", "", "", Severity.INFO, "")
    minor = Diff("pages", "", "", Severity.MINOR, "")
    assert decide_status(True, []) is Status.VERIFIED
    assert decide_status(True, [info]) is Status.VERIFIED
    assert decide_status(True, [info, minor]) is Status.MISMATCH
    assert decide_status(False, []) is Status.NOT_FOUND


def test_authors_particles_stored_in_given_name_by_datacite():
    # arXiv/DataCite 记录：given="Rianne van den", family="Berg"
    claimed = [Author("van den Berg", "R"), Author("Agüera y Arcas", "B.")]
    db = [Author("Berg", "Rianne van den"), Author("Arcas", "Blaise Agüera y")]
    assert compare_authors(claimed, False, db) == []


def test_single_group_author_is_not_checked_for_missing_authors():
    # GPT-4 Technical Report：Agent 写 "OpenAI"，数据库列出 281 位作者
    db = [Author("OpenAI", ""), Author("Achiam", "Josh"), Author("Adler", "Steven")]
    assert compare_authors([Author("OpenAI", "")], False, db) == []


def test_authors_initial_plus_particles_matches_full_db_name():
    # 若解析器把姓氏前缀划进了名字（"L. Van Der" + "Maaten"），比对也不应误报
    assert compare_authors([Author("Maaten", "L. Van Der")], True, [Author("Van Der Maaten", "Laurens")]) == []


def test_authors_reversed_name_order_with_initials():
    # Agent 写 "Sirishantha GMAD"，数据库为 given="G.M.A.D.", family="Sirishantha"
    assert compare_authors([Author("GMAD", "Sirishantha")], True, [Author("Sirishantha", "G.M.A.D.")]) == []


def test_authors_initials_spacing_differs():
    db = [Author("B", "Sudhan M"), Author("M B", "Sudhan")]
    assert compare_authors([Author("MB", "Sudhan")], True, db[:1]) == []
    assert compare_authors([Author("MB", "Sudhan")], True, db[1:]) == []


def test_authors_abbreviated_given_name_in_database():
    assert compare_authors([Author("Biswas", "Saroj Kumar")], True, [Author("Biswas", "Saroj Kr.")]) == []
    assert compare_authors([Author("Biswas", "Saroj Kr.")], True, [Author("Biswas", "Saroj Kumar")]) == []
    # 但名字整体不同仍要报
    assert compare_authors([Author("Zheng", "Nannan")], True, [Author("Zheng", "Ningxin")])


def test_authors_database_omits_middle_name():
    assert compare_authors([Author("Chi", "Ed H.")], True, [Author("Chi", "Ed")]) == []
    assert compare_authors([Author("Thai", "Zhen Leng")], True, [Author("Thai", "Zhen")]) == []


def test_authors_concatenated_initials():
    assert compare_authors([Author("Hoang", "TN"), Author("Shi", "JY")], True,
                           [Author("Hoang", "Trong Nghia"), Author("Shi", "Jian-Yu")]) == []


def test_compare_titles_database_has_only_the_name():
    assert compare_titles("PressLight: Learning max pressure control to coordinate traffic signals in arterial network",
                          "PressLight")[0] is TitleMatch.SAME_MAIN_TITLE


def test_compare_volume():
    from citeguard.matcher import compare_volume
    assert compare_volume("154", "151")
    assert not compare_volume("36", "36") and not compare_volume(None, "3") and not compare_volume("3", None)


def test_pages_on_cvf_conference_dois_are_info_only():
    from citeguard.models import Severity
    diffs = compare_pages("4700-4708", "2261-2269", doi="10.1109/cvpr.2017.243")
    assert diffs and diffs[0].severity is Severity.INFO
    assert compare_pages("4700-4708", "2261-2269", doi="10.1109/tpami.2019.1")[0].severity is Severity.MINOR
