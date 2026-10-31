"""从 Agent 写的综述文本中抽取参考文献，并解析出标题、作者、年份、DOI 等字段。

支持试跑中出现过的格式：APA、"Surname, I."、"Surname I I"、GB/T 7714 全名 + [C]//、引号标题、仅标题。
"""

from __future__ import annotations

import re

from citeguard.models import Author, Reference

_UPPER = r"[A-Z\u00C0-\u00DE\u0100-\u024F]"  # 含 Ł、Č 等带变音符号的大写字母
_NAME_WORD = rf"{_UPPER}[\w\u00C0-\u024F'’\-]*"
_PARTICLES = r"(?:(?:van|von|der|den|de|del|da|di|le|la)\s+)*"
_SURNAME = rf"{_PARTICLES}{_NAME_WORD}(?:\s+y\s+{_NAME_WORD})?"
_INITIALS_DOTTED = rf"{_UPPER}\.(?:\s?-?{_UPPER}\.)*"
_INITIALS_BARE = rf"{_UPPER}(?:[\s-]{_UPPER})*(?=[,.;]|\s+et\s+al)"
_SEP = r"(?:[,;]\s*(?:&\s*|and\s+)?|\s*&\s*|\s+and\s+)"
_ET_AL = r"(?:et\s+al\.?|等)"

# 风格 A：He, K., Zhang, X.    风格 B：Kipf T N, Welling M / Nichol A. Q.
_STYLE_A_ITEM = re.compile(rf"(?P<family>{_SURNAME}),\s*(?P<given>{_INITIALS_DOTTED})")
_STYLE_B_ITEM = re.compile(rf"(?P<family>{_SURNAME})\s+(?P<given>{_INITIALS_DOTTED}|{_INITIALS_BARE})")
# 风格 D：S.-H. Gao, L. Van Der Maaten（首字母在前；姓氏前缀可能大写）
_CAP_PARTICLES = r"(?:(?:[Vv]an|[Vv]on|[Dd]er|[Dd]en|[Dd]e|[Dd]el|[Dd]a|[Dd]i|[Ll]e|[Ll]a)\s+)*"
_STYLE_D_ITEM = re.compile(
    rf"(?P<given>{_INITIALS_DOTTED})\s+(?P<family>{_CAP_PARTICLES}{_NAME_WORD}(?:\s+y\s+{_NAME_WORD})?)(?!\w)"
)
_SEP_RE = re.compile(_SEP)
_ET_AL_RE = re.compile(rf"{_ET_AL}")

_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>，。]+)", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arXiv[:\s.]*(\d{4}\.\d{4,5})", re.IGNORECASE)
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_PAGES_RE = re.compile(r"(?<![\w.])([A-Z]?\d+)\s*[–—-]\s*([A-Z]?\d+)(?!\w|\.\d)")
_TYPE_MARK_RE = re.compile(r"\[(?:C|J|M|D|A|R|S|P|EB/OL|J/OL)\](?://)?")
_HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:\*\*)?\s*(?:参考文献|References|Bibliography|引用文献)\s*[:：]?\s*(?:\*\*)?\s*$",
    re.IGNORECASE,
)
_ITEM_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)、])\s+(.*)$")
_SENTENCE_END_RE = re.compile(r"(?<!\bvs)(?<!\be\.g)(?<!\bi\.e)\.(?=\s|$)")


# ---------------------------------------------------------------- 文本切分

def _section_lines(text: str) -> list[str]:
    lines = text.splitlines()
    heading = [i for i, line in enumerate(lines) if _HEADING_RE.match(line)]
    if heading:
        return lines[heading[-1] + 1:]
    starts = [i for i, line in enumerate(lines) if (m := _ITEM_RE.match(line)) and (m.group(1) or m.group(2)) == "1"]
    return lines[starts[-1]:] if starts else []


def split_references(text: str) -> list[str]:
    """返回参考文献部分的每一条（已合并续行）。"""
    items: list[str] = []
    open_item = False
    prev_blank = False
    for line in _section_lines(text):
        m = _ITEM_RE.match(line)
        if m:
            items.append(m.group(3).strip())
            open_item = True
        elif not line.strip():
            prev_blank = True
            continue
        elif open_item and (line[:1].isspace() or not prev_blank):
            items[-1] += " " + line.strip()
        else:
            open_item = False
        prev_blank = False
    return items


# ---------------------------------------------------------------- 作者

def _parse_style(text: str, item_re: re.Pattern) -> tuple[list[Author], bool, int] | None:
    authors: list[Author] = []
    pos = 0
    while True:
        m = item_re.match(text, pos)
        if not m:
            return None
        authors.append(Author(m.group("family"), m.group("given")))
        pos = m.end()
        sep = _SEP_RE.match(text, pos)
        if sep:
            after = sep.end()
            if (et := _ET_AL_RE.match(text, after)):
                return authors, True, et.end()
            if item_re.match(text, after):
                pos = after
                continue
        return authors, False, pos


_LOWER_PARTICLES = {"van", "von", "der", "den", "de", "del", "da", "di", "le", "la", "y"}
_NAME_TOKEN = rf"(?:{_NAME_WORD}|(?:{_UPPER}\.-?)+|{_UPPER}[a-z]{{1,2}}\.|{'|'.join(sorted(_LOWER_PARTICLES))})"
_NAME_RE = re.compile(rf"{_NAME_TOKEN}(?:\s+{_NAME_TOKEN})*")
_NEXT_SEGMENT_RE = re.compile(r"\s+([^,;]*?)(?=[,;]|\.\s|\.?$)")


def _is_name(text: str) -> bool:
    return bool(_NAME_RE.fullmatch(text)) and len(text.split()) <= 4


def _author_block_end(text: str) -> int | None:
    """全名格式的作者段在哪个句点结束。

    首字母后的句点（Jose M. Alvarez、A. Ezil Sam Leni、Vairamuthu M. 标题……）要看后面：
    紧跟着的一段（到下一个逗号/分号/句点为止）仍像人名，就还在作者段内。
    """
    for m in re.finditer(r"\.(?=\s)", text):
        before = text[:m.start()]
        nxt = _NEXT_SEGMENT_RE.match(text, m.end())
        next_is_name = bool(nxt and nxt.group(1) and _is_name(nxt.group(1)))
        if next_is_name and re.search(r"(?:^|[\s.-])[A-Z]$", before):
            continue
        # 名字缩写（Saroj Kr. Biswas、Md. Rahman）：后面一段是人名且以逗号/分号结束
        if next_is_name and re.search(r"(?:^|\s)[A-Z][a-z]{1,2}$", before) and \
                text[nxt.end():nxt.end() + 1] in (",", ";"):
            continue
        return m.start()
    return None


def _split_full_name(name: str) -> Author:
    tokens = name.split()
    i = len(tokens) - 1
    while i > 0 and tokens[i - 1] in _LOWER_PARTICLES:  # Laurens van der Maaten
        i -= 1
    return Author(" ".join(tokens[i:]), " ".join(tokens[:i]))


def _parse_full_names(text: str) -> tuple[list[Author], bool, int] | None:
    end = _author_block_end(text)
    if end is None:
        return None
    block = text[:end]
    truncated = False
    if (et := re.search(rf"{_SEP}{_ET_AL}$", block)):
        truncated, block = True, block[:et.start()]
    names = [n.strip() for n in re.split(_SEP, block) if n.strip()]
    if not names or not all(_NAME_RE.fullmatch(n) and len(n.split()) <= 6 for n in names):
        return None
    if len(names) == 1 and len(names[0].split()) > 3:  # 很可能是"仅标题"的条目
        return None
    if len(names) > 1 and any(len(n.split()) < 2 for n in names):  # "Vaswani, A., ..." 是风格 A，不是全名
        return None
    return [_split_full_name(n) for n in names], truncated, end + 1


def _parse_authors(text: str) -> tuple[list[Author], bool, int]:
    """各种格式都试一遍，取识别出作者最多的一种（并列时按 A、B、D、全名的顺序）。"""
    parses = [_parse_style(text, r) for r in (_STYLE_A_ITEM, _STYLE_B_ITEM, _STYLE_D_ITEM)]
    parses.append(_parse_full_names(text))
    candidates = [p for p in parses if p]
    if not candidates:
        return [], False, 0
    return max(candidates, key=lambda p: len(p[0]))


# ---------------------------------------------------------------- 标题与其他字段

def _extract_title(rest: str) -> tuple[str, str]:
    """rest 以标题开头；返回 (标题, 标题之后的文本)。"""
    quoted = re.match(r"\s*[\"“](.+?)[\"”]", rest)
    if quoted:
        return quoted.group(1).strip().rstrip("."), rest[quoted.end():]
    cuts = [len(rest)]
    for pattern in (_TYPE_MARK_RE, re.compile(r"\s\*|\*\s|\.\s+In:"), _SENTENCE_END_RE):
        m = pattern.search(rest)
        if m:
            cuts.append(m.start())
    cut = min(cuts)
    return rest[:cut].strip().strip("*").strip().rstrip("."), rest[cut:]


def parse_reference(raw: str) -> Reference:
    text = re.sub(r"\s+", " ", raw).strip()
    doi_m = _DOI_RE.search(text)
    doi = doi_m.group(1).rstrip(".,;)]").lower() if doi_m else None
    arxiv_m = _ARXIV_RE.search(text) or (re.search(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})", doi) if doi else None)

    body = re.split(r"\bDOI\b|https?://doi\.org/", text, maxsplit=1, flags=re.IGNORECASE)[0]
    authors, truncated, pos = _parse_authors(body)
    rest = body[pos:].lstrip(" .,")
    year = None
    apa = re.match(r"\((\d{4})[a-z]?\)\.?\s*", rest)
    if apa:
        year, rest = int(apa.group(1)), rest[apa.end():]
    title, after = _extract_title(rest)
    if year is None:
        years = _YEAR_RE.findall(_ARXIV_RE.sub("", after)) or _YEAR_RE.findall(body[:pos])
        year = int(years[0]) if years else None
    pages_m = _PAGES_RE.search(after)
    venue = re.split(r",?\s*(?:19|20)\d{2}", _TYPE_MARK_RE.sub("", after), maxsplit=1)[0]
    venue = re.sub(r"^[\s.,:*]*(?:In:\s*)?", "", venue)
    venue = re.split(r"\*|,\s*\d", venue, maxsplit=1)[0].strip(" .,")
    return Reference(
        raw=raw.strip(),
        title=title,
        authors=authors,
        authors_truncated=truncated,
        year=year,
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_m.group(1) if arxiv_m else None,
        pages=f"{pages_m.group(1)}-{pages_m.group(2)}" if pages_m else None,
    )


def _looks_like_reference(ref: Reference) -> bool:
    # Agent 拒答时也会写编号列表（"1. 允许我联网检索……"），这类条目没有作者/DOI，且是第一/二人称的句子
    if ref.doi or ref.authors:
        return True
    return ref.year is not None and len(ref.title) <= 200 and not re.search(r"[我你您]", ref.raw)


def parse_references(text: str) -> list[Reference]:
    return [ref for ref in map(parse_reference, split_references(text)) if _looks_like_reference(ref)]
