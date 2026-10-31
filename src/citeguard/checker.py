"""核查流程：DOI → arXiv 编号 → 多源标题检索 → 找正式发表版本 → 逐字段比对 → 判定。"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from citeguard.cache import Cache
from citeguard.http import FetchError, HttpClient
from citeguard.matcher import (
    TitleMatch,
    compare_authors,
    compare_pages,
    compare_titles,
    compare_year,
    decide_status,
)
from citeguard.models import Diff, Paper, Reference, Result, Severity, Status
from citeguard.parser import parse_references
from citeguard.sources import ArxivSource, CrossrefSource, DoiOrgSource, OpenAlexSource, SemanticScholarSource, Source

T = TypeVar("T")
_RANK = {TitleMatch.SAME: 3, TitleMatch.SAME_MAIN_TITLE: 2, TitleMatch.SUBTITLE_DIFFERS: 1, TitleMatch.DIFFERENT: 0}
_ARXIV_PREFIX = "10.48550/"
MAX_CANDIDATES = 3
DEFAULT_CACHE_DIR = Path(".citeguard_cache")


@dataclass
class _Hit:
    paper: Paper
    match: TitleMatch
    score: float
    author_overlap: int

    @property
    def key(self) -> tuple:
        return _RANK[self.match], self.author_overlap, self.score


@dataclass
class _Run:
    """一次核查中的数据源调用记录：用于区分"找不到"和"查不了"。"""

    failures: list[str] = field(default_factory=list)
    successes: int = 0

    def call(self, fn: Callable[..., T], *args) -> T | None:
        try:
            value = fn(*args)
        except FetchError as exc:
            self.failures.append(str(exc))
            return None
        self.successes += 1
        return value


def _author_overlap(ref: Reference, paper: Paper) -> int:
    families = {a.family.lower() for a in paper.authors}
    return sum(1 for a in ref.authors if a.family.lower() in families)


@dataclass
class Checker:
    crossref: Source
    doi_org: Source
    search_sources: list[Source] = field(default_factory=list)  # Crossref 之后依次尝试
    arxiv: ArxivSource | None = None

    # ------------------------------------------------------------ 查找

    def _lookup_doi(self, doi: str, run: _Run) -> Paper | None:
        order = [self.doi_org, self.crossref] if doi.startswith(_ARXIV_PREFIX) else [self.crossref, self.doi_org]
        for source in order:
            paper = run.call(source.get_by_doi, doi)
            if paper:
                return paper
        return None

    def _hit(self, ref: Reference, paper: Paper) -> _Hit:
        match, score = compare_titles(ref.title, paper.title)
        return _Hit(paper, match, score, _author_overlap(ref, paper))

    def _search(self, ref: Reference, run: _Run) -> list[_Hit]:
        hits: list[_Hit] = []
        first_author = f" {ref.authors[0].family}" if ref.authors else ""
        for source in [self.crossref, *self.search_sources]:
            query = ref.title + first_author if source is self.crossref else ref.title
            for paper in run.call(source.search, query) or []:
                hits.append(self._hit(ref, paper))
            if any(_RANK[h.match] >= 2 for h in hits):
                break
        main_title = ref.title.partition(":")[0].strip()
        if main_title != ref.title and not any(_RANK[h.match] >= 1 for h in hits):
            # 副标题被改写（如中文意译）时全标题检索不到，用"模型名"主标题再查一次
            hits += [self._hit(ref, p) for p in run.call(self.crossref.search, main_title) or []]
        return sorted(hits, key=lambda h: h.key, reverse=True)

    def _published_version(self, preprint: Paper, run: _Run) -> Paper | None:
        for paper in run.call(self.crossref.search, preprint.title) or []:
            same = compare_titles(preprint.title, paper.title)[0] in (TitleMatch.SAME, TitleMatch.SAME_MAIN_TITLE)
            if same and paper.doi and not paper.doi.startswith(_ARXIV_PREFIX) and _author_overlap_papers(preprint, paper):
                return paper
        return None

    # ------------------------------------------------------------ 主流程

    def check(self, ref: Reference) -> Result:
        run = _Run()
        diffs: list[Diff] = []
        matched: Paper | None = None
        title_match = TitleMatch.SAME
        candidates: list[Paper] = []
        doi_diff: Diff | None = None

        if ref.doi:
            paper = self._lookup_doi(ref.doi, run)
            if paper:
                hit = self._hit(ref, paper) if ref.title else _Hit(paper, TitleMatch.SAME, 1.0, 0)
                if _RANK[hit.match] >= 2:
                    matched, title_match = paper, hit.match
                else:
                    doi_diff = Diff("doi", ref.doi, "", Severity.MAJOR,
                                    f"DOI {ref.doi} 指向另一篇论文：《{paper.title}》")
            elif not run.failures:
                doi_diff = Diff("doi", ref.doi, "", Severity.MAJOR, f"DOI {ref.doi} 无法解析（不存在）")

        if matched is None and ref.arxiv_id and self.arxiv is not None:
            paper = run.call(self.arxiv.get_by_id, ref.arxiv_id)
            if paper and _RANK[self._hit(ref, paper).match] >= 2:
                matched, title_match = paper, self._hit(ref, paper).match

        if matched is None and ref.title:
            hits = self._search(ref, run)
            best = hits[0] if hits else None
            if best and (_RANK[best.match] >= 2 or (
                    best.match is TitleMatch.SUBTITLE_DIFFERS and (not ref.authors or best.author_overlap))):
                matched, title_match = best.paper, best.match
                if best.match is TitleMatch.SUBTITLE_DIFFERS:
                    diffs.append(Diff("title", ref.title, best.paper.title, Severity.MAJOR,
                                      f"标题不符，最接近的真实论文是《{best.paper.title}》"))
            pool = hits[1:] if matched is not None else hits
            candidates = [h.paper for h in pool if h.match is not TitleMatch.DIFFERENT or h.score >= 0.5]
            candidates = candidates[:MAX_CANDIDATES] or [h.paper for h in pool[:MAX_CANDIDATES]]

        note = "；".join(f"数据源请求失败：{f}" for f in run.failures)
        if doi_diff is not None:
            if matched is not None and matched.doi:
                doi_diff.actual = matched.doi
                doi_diff.message += f"；正确 DOI 应为 {matched.doi}"
            diffs.insert(0, doi_diff)

        if matched is None:
            status = Status.UNKNOWN if run.failures and not run.successes else Status.NOT_FOUND
            return Result(ref, status, None, diffs, candidates, note)

        target = matched
        if matched.doi and matched.doi.startswith(_ARXIV_PREFIX):
            published = self._published_version(matched, run)
            if published is not None:
                target = published
                diffs.append(Diff("doi", ref.doi or "", published.doi or "", Severity.INFO,
                                  f"该论文已正式发表于 {published.venue}（{published.year}），DOI {published.doi}"))
        elif not ref.doi and matched.doi:
            diffs.append(Diff("doi", "", matched.doi, Severity.INFO, f"可补充 DOI：{matched.doi}"))
        if title_match is TitleMatch.SAME_MAIN_TITLE:
            diffs.append(Diff("title", ref.title, target.title, Severity.INFO,
                              f"标题与数据库记录不完全一致（省略副标题或数据库标题截断）：《{target.title}》"))

        diffs += compare_authors(ref.authors, ref.authors_truncated, target.authors)
        if compare_year(ref.year, matched.year) and compare_year(ref.year, target.year):
            diffs += compare_year(ref.year, target.year)
        diffs += compare_pages(ref.pages, target.pages)
        note = "；".join(f"数据源请求失败：{f}" for f in run.failures)  # 找正式版本时也可能失败
        return Result(ref, decide_status(True, diffs), target, diffs, candidates, note)

    def check_text(self, text: str) -> list[Result]:
        return [self.check(ref) for ref in parse_references(text)]


def _author_overlap_papers(a: Paper, b: Paper) -> bool:
    """预印本与正式版至少有一位作者姓氏相同（数据库缺作者时不作要求）。"""
    if not a.authors or not b.authors:
        return True
    last_token = lambda author: author.family.lower().split()[-1] if author.family.strip() else ""  # noqa: E731
    return bool({last_token(x) for x in a.authors} & {last_token(x) for x in b.authors} - {""})


def build_default_checker(cache_dir: Path | None = DEFAULT_CACHE_DIR,
                          environ: Mapping[str, str] | None = None) -> Checker:
    env = os.environ if environ is None else environ
    http = HttpClient(cache=Cache(cache_dir))
    search_sources: list[Source] = [OpenAlexSource(http, env.get("OPENALEX_API_KEY") or None)]
    search_sources.append(SemanticScholarSource(http, env.get("S2_API_KEY") or None))
    return Checker(
        crossref=CrossrefSource(http, env.get("CROSSREF_MAILTO") or None),
        doi_org=DoiOrgSource(http),
        search_sources=search_sources,
        arxiv=ArxivSource(http),
    )
