"""比对 Agent 给出的题录与数据库记录：标题、作者、年份、页码，以及最终判定。

规则来自第 2、3 步的实测（docs/数据源实测.md、docs/试跑结果.md §6.2）。
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from enum import Enum

from citeguard.models import Author, Diff, Severity, Status

SAME_TITLE_THRESHOLD = 0.90
YEAR_TOLERANCE = 1  # 预印本与正式版年份常差 1 年


class TitleMatch(str, Enum):
    SAME = "same"
    SAME_MAIN_TITLE = "same_main_title"  # 省略副标题 / 数据库标题截断 / 加了模型名前缀
    SUBTITLE_DIFFERS = "subtitle_differs"  # 主标题相同、副标题不同
    DIFFERENT = "different"


# ---------------------------------------------------------------- 文本归一化

def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_title(title: str) -> str:
    text = html.unescape(html.unescape(title or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\$\^?\{?([^$}]*)\}?\$", r" \1 ", text)  # $^2$ → 2
    text = _strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9一-鿿]+", " ", text)
    return " ".join(text.split())


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _split_title(title: str) -> tuple[str, str]:
    main, _, sub = (title or "").partition(":")
    return normalize_title(main), normalize_title(sub)


def _is_word_prefix(short: str, long: str) -> bool:
    return long.startswith(short) and (len(long) == len(short) or long[len(short)] == " ")


def compare_titles(claimed: str, actual: str) -> tuple[TitleMatch, float]:
    c, a = normalize_title(claimed), normalize_title(actual)
    score = _ratio(c, a)
    if score >= SAME_TITLE_THRESHOLD:
        return TitleMatch.SAME, score
    short, long = sorted((c, a), key=len)
    if len(short.split()) >= 2 and len(short) >= 15 and _is_word_prefix(short, long):
        return TitleMatch.SAME_MAIN_TITLE, score
    c_main, c_sub = _split_title(claimed)
    a_main, a_sub = _split_title(actual)
    if c_sub and _ratio(c_sub, a) >= SAME_TITLE_THRESHOLD and len(c_sub.split()) >= 3:
        return TitleMatch.SAME_MAIN_TITLE, score
    if c_main and c_main == a_main and c_sub and a_sub:
        return TitleMatch.SUBTITLE_DIFFERS, score
    return TitleMatch.DIFFERENT, score


# ---------------------------------------------------------------- 作者

def _norm_name(text: str) -> str:
    return re.sub(r"[^a-z ]", "", _strip_accents(text).lower().replace("-", "").replace(".", " "))


def _tokens(text: str) -> list[str]:
    return _norm_name(text).split()


def _family_matches(claimed: Author, actual: Author) -> bool:
    c_tokens, a = _tokens(claimed.family), _tokens(actual.family)
    c = "".join(c_tokens)
    if not c or not a:
        return False
    # 末词相同也算：DataCite 常把 van den / Agüera y 放进 given（family 只有 Berg / Arcas）
    return c == "".join(a) or c in a or c_tokens[-1] == a[-1]


def _given_matches(claimed: Author, actual: Author) -> bool:
    family_tokens = set(_tokens(actual.family))
    c_tokens = [t for t in _tokens(claimed.given) if t not in family_tokens]  # "L. Van Der" + "Maaten"
    a_given = "".join(_tokens(actual.given))
    if not c_tokens or not a_given:
        return True
    if all(len(t) == 1 for t in c_tokens):  # 只给了首字母：比第一个首字母
        return c_tokens[0] == a_given[0]
    if "".join(c_tokens) == a_given:
        return True
    a_tokens = [t for t in _tokens(actual.given) if t not in family_tokens]
    return len(c_tokens) == len(a_tokens) and all(_token_matches(c, a) for c, a in zip(c_tokens, a_tokens))


def _is_abbreviation(short: str, long: str) -> bool:
    """Kr ↔ Kumar、Md ↔ Mohammed：首字母相同、≤3 个字母且按顺序出现在全名中。"""
    if len(short) > 3 or len(short) >= len(long) or short[0] != long[0]:
        return False
    rest = iter(long[1:])
    return all(ch in rest for ch in short[1:])


def _token_matches(c: str, a: str) -> bool:
    if c == a or (len(c) == 1 and a.startswith(c)) or (len(a) == 1 and c.startswith(a)):
        return True
    return _is_abbreviation(c, a) or _is_abbreviation(a, c)


def _same_person(claimed: Author, actual: Author) -> bool:
    full_c = Counter(_tokens(claimed.full))
    if len(full_c) > 1 and full_c == Counter(_tokens(actual.full)):  # 多词姓氏拆分方式不同（Anasosalu Vasu）
        return True
    if len(full_c) > 1 and "".join(_tokens(claimed.full)) == "".join(_tokens(actual.full)):  # Sudhan MB / Sudhan M B
        return True
    if _family_matches(claimed, actual) and _given_matches(claimed, actual):
        return True
    # 姓名顺序颠倒："Sirishantha GMAD" ↔ given="G.M.A.D.", family="Sirishantha"
    initials = "".join(t[0] for t in _tokens(actual.given))
    return bool(initials) and "".join(_tokens(claimed.family)) == initials and \
        "".join(_tokens(claimed.given)) == "".join(_tokens(actual.family))


def compare_authors(claimed: list[Author], truncated: bool, actual: list[Author]) -> list[Diff]:
    if not claimed or not actual:
        return []
    if len(claimed) == 1 and not claimed[0].given:
        truncated = True  # 机构作者（如 "OpenAI"）代表全体作者
    diffs: list[Diff] = []
    used: set[int] = set()
    for i, c in enumerate(claimed):
        if i < len(actual) and _same_person(c, actual[i]):
            used.add(i)
            continue
        if i < len(actual) and _family_matches(c, actual[i]):
            used.add(i)
            diffs.append(Diff("authors", c.full, actual[i].full, Severity.MINOR,
                              f"第 {i + 1} 作者名字不符：{c.full} → {actual[i].full}"))
            continue
        elsewhere = next((j for j, a in enumerate(actual) if j not in used and _same_person(c, a)), None)
        if elsewhere is not None:
            used.add(elsewhere)
            diffs.append(Diff("authors", c.full, actual[elsewhere].full, Severity.MINOR,
                              f"作者顺序不符：{c.full} 应为第 {elsewhere + 1} 作者，而不是第 {i + 1} 作者"))
            continue
        expected = actual[i].full if i < len(actual) else "（无）"
        if i < len(actual) and i not in used:
            used.add(i)  # 该位置已在本条差异里给出正确作者，不再重复报"漏掉"
        diffs.append(Diff("authors", c.full, expected, Severity.MAJOR,
                          f"第 {i + 1} 作者 {c.full} 不在该论文的作者列表中（该位置应为 {expected}）"))
    if not truncated:
        missing = [a.full for j, a in enumerate(actual) if j not in used
                   and not any(_family_matches(c, a) for c in claimed)]
        if missing:
            diffs.append(Diff("authors", "", ", ".join(missing), Severity.MINOR,
                              f"漏掉作者：{', '.join(missing)}（该论文共 {len(actual)} 位作者）"))
    return diffs


# ---------------------------------------------------------------- 年份、页码

def compare_year(claimed: int | None, actual: int | None) -> list[Diff]:
    if claimed is None or actual is None or abs(claimed - actual) <= YEAR_TOLERANCE:
        return []
    return [Diff("year", str(claimed), str(actual), Severity.MINOR, f"年份不符：{claimed} → {actual}")]


def _first_page(pages: str | None) -> str | None:
    if not pages:
        return None
    parts = re.split(r"\s*[–—-]\s*", pages.strip())
    return parts[0] or None


def compare_pages(claimed: str | None, actual: str | None) -> list[Diff]:
    c, a = _first_page(claimed), _first_page(actual)
    if not c or not a or re.fullmatch(r"1\s*[–—-]\s*1", actual or ""):  # 早期访问记录的占位页码
        return []
    if c.lower() == a.lower():
        return []
    return [Diff("pages", claimed or "", actual or "", Severity.MINOR, f"页码不符：{claimed} → {actual}")]


# ---------------------------------------------------------------- 判定

def decide_status(found: bool, diffs: list[Diff]) -> Status:
    if not found:
        return Status.NOT_FOUND
    if any(d.severity is not Severity.INFO for d in diffs):
        return Status.MISMATCH
    return Status.VERIFIED
