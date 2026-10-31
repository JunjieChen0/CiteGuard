"""把核查结果整理成 Agent 能直接照做的 Markdown 报告。"""

from __future__ import annotations

from citeguard.models import Paper, Result, Severity, Status

MAX_AUTHORS = 20  # 提示词常要求"全部作者"；只给 6 位时 Agent 会想办法绕路获取
_ICON = {Status.VERIFIED: "✅", Status.MISMATCH: "⚠️", Status.NOT_FOUND: "❌", Status.UNKNOWN: "❓"}
_SEVERITY = {Severity.MAJOR: "严重", Severity.MINOR: "次要", Severity.INFO: "提示"}


def format_paper(paper: Paper) -> str:
    """按数据库元数据生成一条规范的参考文献，供 Agent 直接替换。"""
    names = [a.full for a in paper.authors if a.full]
    authors = ", ".join(names[:MAX_AUTHORS]) + (", et al" if len(names) > MAX_AUTHORS else "")
    parts = [f"{authors}." if authors else "", f"{paper.title}."]
    volume = f"{paper.volume}({paper.issue})" if paper.volume and paper.issue else paper.volume
    locator = ": ".join(x for x in (volume, paper.pages) if x)
    where = ", ".join(str(x) for x in (paper.venue, paper.year, locator) if x)
    if where:
        parts.append(f"{where}.")
    if paper.doi:
        parts.append(f"DOI: {paper.doi}")
    return " ".join(p for p in parts if p)


def summarize(results: list[Result]) -> dict[str, int]:
    counts = {"total": len(results)}
    for status in Status:
        counts[status.value] = sum(r.status is status for r in results)
    return counts


def _format_result(i: int, r: Result) -> list[str]:
    title = r.reference.title or r.reference.raw[:80]
    lines = [f"### [{i}] {_ICON[r.status]} {r.status.value}　《{title}》", ""]
    if r.status is Status.VERIFIED:
        lines += [f"- 提示：{d.message}" for d in r.diffs]
    elif r.status is Status.MISMATCH:
        lines += [f"- 问题（{_SEVERITY[d.severity]}）：{d.message}" for d in r.diffs if d.severity is not Severity.INFO]
        lines += [f"- 提示：{d.message}" for d in r.diffs if d.severity is Severity.INFO]
        if r.matched is not None:
            lines.append(f"- 建议改为：{format_paper(r.matched)}")
    elif r.status is Status.NOT_FOUND:
        lines += [f"- 问题（{_SEVERITY[d.severity]}）：{d.message}" for d in r.diffs]
        lines.append("- 所有数据源都找不到这篇论文，很可能是编造的。请删除；如需替换，只能换成与正文论述直接相关的真实论文"
                     "（可用 search_papers 检索），不要为了凑数换成无关文献。")
        if r.candidates:
            lines.append("- 标题最接近的真实论文（仅供参考，未必相关）：")
            lines += [f"  {k}. {format_paper(p)}" for k, p in enumerate(r.candidates, 1)]
    else:
        lines.append(f"- 数据源暂时不可用，无法判断（{r.note or '网络错误'}）。请在文中注明该条未核验，或稍后重新核查。")
    if r.note and r.status is not Status.UNKNOWN:
        lines.append(f"- 备注：{r.note}")
    lines.append("")
    return lines


def format_report(results: list[Result]) -> str:
    if not results:
        return ("## CiteGuard 核查报告\n\n没有识别到参考文献。请把参考文献放在单独的“参考文献”或“References”标题下，"
                "每条以 [1] 或 1. 编号开头，包含作者、标题、会议/期刊、年份和 DOI（如有）。")
    c = summarize(results)
    lines = ["## CiteGuard 核查报告", "",
             f"共 {c['total']} 条：✅ {c['VERIFIED']}　⚠️ {c['MISMATCH']}　❌ {c['NOT_FOUND']}　❓ {c['UNKNOWN']}", ""]
    for i, r in enumerate(results, 1):
        lines += _format_result(i, r)
    if c["MISMATCH"] or c["NOT_FOUND"]:
        lines += ["## 下一步", "",
                  "1. ⚠️ 条目：按“建议改为”替换整条参考文献（以数据库元数据为准，不要凭记忆修改）；",
                  "2. ❌ 条目：删除，并同步删除或改写正文中对它的引用；需要补充文献时先用 search_papers 检索；",
                  "3. 修改后再次调用 verify_references 核查完整的参考文献列表，直到没有 ⚠️ 和 ❌。"]
    else:
        lines.append("全部通过核查（❓ 条目除外），可以输出终稿。")
    return "\n".join(lines).rstrip() + "\n"
