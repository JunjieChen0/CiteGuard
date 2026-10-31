import pytest

from citeguard.models import Author
from citeguard.parser import parse_reference, parse_references, split_references

# 以下样本均摘自第 3 步试跑中 Agent 的真实输出（experiments/results/pilot*/）
APA = ("Zhang, X., & Lapata, M. (2014). Chinese Poetry Generation with Recurrent Neural Networks. "
       "*Proceedings of EMNLP 2014*, 670–680. DOI: 10.3115/v1/D14-1074")
SURNAME_COMMA = ("He, K., Zhang, X., Ren, S., Sun, J. Deep Residual Learning for Image Recognition. In: Proceedings "
                 "of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR), 2016. DOI: 10.1109/CVPR.2016.90")
SURNAME_INITIALS = ("Kipf T N, Welling M. Semi-Supervised Classification with Graph Convolutional Networks. "
                    "International Conference on Learning Representations (ICLR), 2017. DOI: 10.48550/arXiv.1609.02907")
DOTTED_INITIALS = ("Nichol A. Q., Dhariwal P. Improved Denoising Diffusion Probabilistic Models. *International "
                   "Conference on Machine Learning (ICML)*, 2021. DOI: 10.48550/arXiv.2102.09672")
QUOTED = ('Neftci, E. O., Mostafa, H., Zenke, F. "Surrogate Gradient Learning in Spiking Neural Networks." '
          "*IEEE Signal Processing Magazine*, 36(6), 51–63, 2019. DOI: 10.1109/MSP.2019.2931595")
GBT_FULL_NAMES = ("Pavan Kumar Anasosalu Vasu, James Gabrielsson, Chunuan Zhu, Oncel Tuzel, Anurag Ranjan. FastViT: "
                  "A Fast Hybrid Vision Transformer using Structural Reparameterization[C]//Proceedings of the IEEE/CVF "
                  "International Conference on Computer Vision (ICCV). 2023. arXiv:2303.14189. "
                  "DOI: 10.48550/arXiv.2303.14189.")
ETAL = ("Xu H Y, Zhang Y Q, Liu Z M, Chen T, Chai C Y, Li R L, et al. ETCM: an encyclopaedia of traditional Chinese "
        "medicine. Nucleic Acids Research, 2019, 47(D1): D976–D982. DOI: 10.1093/nar/gky987")
TITLE_ONLY = "ShenNong-TCM: A Traditional Chinese Medicine Large Language Model from Professional Data Synthesis. arXiv 预印本，2024."
MULTI_DOT_TITLE = ("Szegedy, C., Ioffe, S., Vanhoucke, V., Alemi, A. Inception-v4, Inception-ResNet and the Impact of "
                   "Residual Connections on Learning. In: Proceedings of the AAAI Conference on Artificial Intelligence "
                   "(AAAI), 2017. DOI: 10.1609/aaai.v31i1.11231")
VS_TITLE = ("Kulyukin, V., Mukherjee, S., Amlathe, P. Toward audio beehive monitoring: Deep learning vs. standard "
            "machine learning in classifying beehive audio samples. *Applied Sciences*, 2018. DOI: 10.3390/app8091573")


@pytest.mark.parametrize(
    ("raw", "title"),
    [
        (APA, "Chinese Poetry Generation with Recurrent Neural Networks"),
        (SURNAME_COMMA, "Deep Residual Learning for Image Recognition"),
        (SURNAME_INITIALS, "Semi-Supervised Classification with Graph Convolutional Networks"),
        (DOTTED_INITIALS, "Improved Denoising Diffusion Probabilistic Models"),
        (QUOTED, "Surrogate Gradient Learning in Spiking Neural Networks"),
        (GBT_FULL_NAMES, "FastViT: A Fast Hybrid Vision Transformer using Structural Reparameterization"),
        (ETAL, "ETCM: an encyclopaedia of traditional Chinese medicine"),
        (TITLE_ONLY, "ShenNong-TCM: A Traditional Chinese Medicine Large Language Model from Professional Data Synthesis"),
        (MULTI_DOT_TITLE, "Inception-v4, Inception-ResNet and the Impact of Residual Connections on Learning"),
        (VS_TITLE, "Toward audio beehive monitoring: Deep learning vs. standard machine learning in classifying "
                   "beehive audio samples"),
    ],
)
def test_parse_title(raw, title):
    assert parse_reference(raw).title == title


def test_parse_doi_strips_trailing_period_and_lowercases():
    assert parse_reference(GBT_FULL_NAMES).doi == "10.48550/arxiv.2303.14189"
    assert parse_reference(SURNAME_COMMA).doi == "10.1109/cvpr.2016.90"


def test_parse_arxiv_id_from_text_or_arxiv_doi():
    assert parse_reference(GBT_FULL_NAMES).arxiv_id == "2303.14189"
    assert parse_reference(SURNAME_INITIALS).arxiv_id == "1609.02907"
    assert parse_reference(SURNAME_COMMA).arxiv_id is None


def test_parse_year_prefers_year_after_title():
    assert parse_reference(APA).year == 2014
    assert parse_reference(GBT_FULL_NAMES).year == 2023
    assert parse_reference(TITLE_ONLY).year == 2024


def test_parse_pages():
    assert parse_reference(QUOTED).pages == "51-63"
    assert parse_reference(ETAL).pages == "D976-D982"
    assert parse_reference(SURNAME_COMMA).pages is None


@pytest.mark.parametrize(
    ("raw", "authors"),
    [
        (SURNAME_COMMA, [Author("He", "K."), Author("Zhang", "X."), Author("Ren", "S."), Author("Sun", "J.")]),
        (APA, [Author("Zhang", "X."), Author("Lapata", "M.")]),
        (SURNAME_INITIALS, [Author("Kipf", "T N"), Author("Welling", "M.")]),
        (DOTTED_INITIALS, [Author("Nichol", "A. Q."), Author("Dhariwal", "P.")]),
        (QUOTED, [Author("Neftci", "E. O."), Author("Mostafa", "H."), Author("Zenke", "F.")]),
        (GBT_FULL_NAMES, [Author("Vasu", "Pavan Kumar Anasosalu"), Author("Gabrielsson", "James"),
                          Author("Zhu", "Chunuan"), Author("Tuzel", "Oncel"), Author("Ranjan", "Anurag")]),
    ],
)
def test_parse_authors(raw, authors):
    assert parse_reference(raw).authors == authors


def test_parse_authors_marks_et_al():
    ref = parse_reference(ETAL)
    assert ref.authors_truncated
    assert [a.family for a in ref.authors] == ["Xu", "Zhang", "Liu", "Chen", "Chai", "Li"]
    assert not parse_reference(SURNAME_COMMA).authors_truncated


def test_parse_title_only_reference_has_no_authors():
    ref = parse_reference(TITLE_ONLY)
    assert ref.authors == []
    assert ref.doi is None


def test_parse_handles_multi_word_surname():
    ref = parse_reference("Huang, G., Liu, Z., van der Maaten, L., Weinberger, K. Q. Densely Connected Convolutional "
                          "Networks. In: CVPR, 2017. DOI: 10.1109/CVPR.2017.243")
    assert ref.authors[2] == Author("van der Maaten", "L.")


def test_parse_hyphenated_initials():
    ref = parse_reference("Nilsback M.-E., Zisserman A. Automated Flower Classification over a Large Number of "
                          "Classes. *ICVGIP*, 2008. DOI: 10.1109/ICVGIP.2008.47")
    assert ref.authors == [Author("Nilsback", "M.-E."), Author("Zisserman", "A.")]


REVIEW = """# 综述标题

正文第一段提到 2017 年的工作。

1. 这一行不在参考文献里

## References

1. Ho J., Jain A., Abbeel P. Denoising Diffusion Probabilistic Models. *NeurIPS*, 2020. DOI: 10.48550/arXiv.2006.11239
2. Song J., Meng C., Ermon S. Denoising Diffusion Implicit Models. *ICLR*, 2021.
   DOI: 10.48550/arXiv.2010.02502

[3] Kairouz, P., McMahan, H. B., et al. Advances and open problems in federated learning. *Foundations and Trends in Machine Learning*, 2021. DOI: 10.1561/2200000083

**备注：** 以上文献未联网核对。
"""


def test_split_references_only_after_heading_and_joins_continuation_lines():
    items = split_references(REVIEW)
    assert len(items) == 3
    assert items[1].endswith("DOI: 10.48550/arXiv.2010.02502")
    assert items[2].startswith("Kairouz")


def test_split_references_supports_chinese_heading():
    text = "正文。\n\n参考文献\n\n[1] Zhang, X., & Lapata, M. (2014). Title A. *EMNLP*.\n[2] B. Title B. 2020.\n"
    assert len(split_references(text)) == 2


def test_split_references_without_heading_uses_trailing_numbered_block():
    text = "正文。\n\n1. A, B. Some Title Here. Venue, 2020.\n2. C, D. Other Title Here. Venue, 2021.\n"
    assert len(split_references(text)) == 2


def test_parse_references_returns_parsed_items():
    refs = parse_references(REVIEW)
    assert [r.title for r in refs] == [
        "Denoising Diffusion Probabilistic Models",
        "Denoising Diffusion Implicit Models",
        "Advances and open problems in federated learning",
    ]


def test_parse_authors_with_non_ascii_initials():
    ref = parse_reference(
        "Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. "
        "(2017). Attention Is All You Need. *Advances in Neural Information Processing Systems (NeurIPS)*. "
        "DOI: 10.48550/arXiv.1706.03762"
    )
    assert ref.title == "Attention Is All You Need"
    assert [a.family for a in ref.authors][-2:] == ["Kaiser", "Polosukhin"]
    assert ref.year == 2017


def test_parse_year_after_arxiv_id():
    ref = parse_reference("Sachin Mehta, Mohammad Rastegari. Separable Self-attention for Mobile Vision Transformers[J]. "
                          "arXiv preprint arXiv:2206.02680, 2022. DOI: 10.48550/arXiv.2206.02680.")
    assert ref.year == 2022
    assert ref.venue == "arXiv preprint arXiv:2206.02680"


def test_venue_stops_at_markdown_and_volume():
    assert parse_reference(QUOTED).venue == "IEEE Signal Processing Magazine"


def test_parse_references_skips_numbered_items_that_are_not_references():
    text = (
        "参考文献部分我无法凭记忆给出。可行的替代方案：\n\n"
        "1. **允许我联网检索**，我可以按“diffusion model + plant disease”检索 2022 年以来的研究；\n"
        "2. **你自己检索后把条目发我**，我负责核对。\n"
    )
    assert parse_references(text) == []


def test_parse_references_keeps_title_only_items_with_year():
    text = "参考文献\n\n1. PresRecST: 面向中草药处方推荐的序列推荐方法. 2022.\n2. TCMChat: A Generative Model. 2024.\n"
    assert [r.year for r in parse_references(text)] == [2022, 2024]
