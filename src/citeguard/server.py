"""CiteGuard MCP Server：向 Agent 提供 verify_references 与 search_papers 两个工具。

运行：uv run citeguard-mcp（stdio）。环境变量：OPENALEX_API_KEY、S2_API_KEY、CROSSREF_MAILTO、
CITEGUARD_CACHE_DIR（默认 ~/.cache/citeguard）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from citeguard.checker import Checker, build_default_checker
from citeguard.http import FetchError
from citeguard.report import format_paper, format_report
from citeguard.sources import CrossrefSource

MAX_SEARCH_LIMIT = 20

INSTRUCTIONS = (
    "CiteGuard 核查学术参考文献是否真实存在、元数据（DOI、作者、年份、标题、页码）是否正确。"
    "写含参考文献的文本时：输出前先用 verify_references 核查完整的参考文献列表，按报告修正后再次核查；"
    "需要真实文献时用 search_papers 检索，不要凭记忆编写题录。"
)


def search_papers(crossref: CrossrefSource, query: str, limit: int = 8, from_year: int | None = None) -> str:
    limit = max(1, min(limit, MAX_SEARCH_LIMIT))
    try:
        papers = crossref.search(query, limit=limit * 2, from_year=from_year)
    except FetchError as exc:
        return f"文献数据源暂时不可用（{exc}），请稍后重试；在此之前不要凭记忆补写参考文献。"
    seen: set[str] = set()
    unique = []
    for paper in papers:
        key = paper.doi or paper.title.lower()
        if paper.authors and paper.title and key not in seen:
            seen.add(key)
            unique.append(paper)
    if not unique:
        return f"没有找到与“{query}”相关的论文。可以换用更通用的英文关键词再试。"
    lines = [f"## 检索结果：{query}" + (f"（{from_year} 年及以后）" if from_year else ""), "",
             "以下均为 Crossref 中真实存在的论文，题录可直接使用。请只选择与正文论述直接相关的条目；"
             "标题相关不代表内容支持你的论点，必要时在正文中如实表述。", ""]
    lines += [f"{i}. {format_paper(p)}" for i, p in enumerate(unique[:limit], 1)]
    return "\n".join(lines) + "\n"


def create_server(checker: Checker, crossref: CrossrefSource) -> MCPServer:
    server = MCPServer("citeguard", instructions=INSTRUCTIONS)

    @server.tool()
    def verify_references(text: str) -> str:
        """核查一段文本中的参考文献是否真实存在、元数据是否正确。

        text：包含参考文献列表的完整文本（或只有参考文献部分），每条以 [1] 或 1. 编号。
        返回逐条报告：✅ 通过；⚠️ 论文存在但 DOI/作者/年份/标题有误（附建议替换的正确题录）；
        ❌ 所有数据源都查不到（很可能是编造的）；❓ 数据源不可用、无法判断。
        """
        return format_report(checker.check_text(text))

    @server.tool()
    def search_papers(query: str, limit: int = 8, from_year: int | None = None) -> str:
        """在 Crossref 中检索真实存在的论文，返回带 DOI 的完整题录，用于补充或替换参考文献。

        query：英文关键词或标题（如 "diffusion model plant disease data augmentation"）。
        limit：返回条数（1–20）。from_year：只要该年及以后发表的论文。
        """
        return _search(crossref, query, limit, from_year)

    return server


_search = search_papers


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)  # 每个请求一行的日志对 Agent 无用
    cache_dir = Path(os.environ.get("CITEGUARD_CACHE_DIR") or Path.home() / ".cache" / "citeguard")
    checker = build_default_checker(cache_dir=cache_dir)
    assert isinstance(checker.crossref, CrossrefSource)
    create_server(checker, checker.crossref).run("stdio")


if __name__ == "__main__":
    main()
