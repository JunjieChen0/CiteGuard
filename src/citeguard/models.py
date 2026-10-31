"""核查流程中共享的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    VERIFIED = "VERIFIED"  # ✅ 论文存在，元数据无实质错误
    MISMATCH = "MISMATCH"  # ⚠️ 论文存在，但 DOI/作者/年份/标题等有误
    NOT_FOUND = "NOT_FOUND"  # ❌ 所有数据源都找不到
    UNKNOWN = "UNKNOWN"  # 网络或限流导致无法判断（不算编造）


class Severity(str, Enum):
    MAJOR = "major"  # DOI 指向他文、编造作者、标题错误
    MINOR = "minor"  # 页码、作者名拼写、年份等
    INFO = "info"  # 不影响判定的提示（如用了预印本 DOI）


@dataclass(frozen=True)
class Author:
    family: str
    given: str = ""

    @property
    def full(self) -> str:
        return f"{self.given} {self.family}".strip()


@dataclass
class Reference:
    """从 Agent 文本中解析出的一条参考文献（Agent 的说法）。"""

    raw: str
    title: str = ""
    authors: list[Author] = field(default_factory=list)
    authors_truncated: bool = False  # 有 et al. / 等
    year: int | None = None
    venue: str = ""
    doi: str | None = None
    arxiv_id: str | None = None
    pages: str | None = None


@dataclass
class Paper:
    """数据源返回的一篇真实论文。"""

    title: str
    authors: list[Author] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str | None = None
    pages: str | None = None
    source: str = ""
    volume: str | None = None
    issue: str | None = None


@dataclass
class Diff:
    field: str
    claimed: str
    actual: str
    severity: Severity
    message: str


@dataclass
class Result:
    reference: Reference
    status: Status
    matched: Paper | None = None
    diffs: list[Diff] = field(default_factory=list)
    candidates: list[Paper] = field(default_factory=list)
    note: str = ""
