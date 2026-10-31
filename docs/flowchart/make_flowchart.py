"""生成 docs/流程图.png：python docs/flowchart/make_flowchart.py（需要 Node + Playwright 截图）。

图用 SVG 手工布局，源文件 docs/flowchart/流程图.html 可直接在浏览器打开编辑。
"""

from __future__ import annotations

import subprocess
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
W, H = 1500, 960
FONT = "'WenQuanYi Zen Hei', 'Microsoft YaHei', 'PingFang SC', sans-serif"

INK, MUTED, LINE = "#1f2328", "#57606a", "#8c959f"
AGENT, TOOL, ENGINE = "#eef4ff", "#fff4e5", "#f6f8fa"
AGENT_B, TOOL_B, ENGINE_B = "#4b74c9", "#c97a1e", "#8c959f"
OK, WARN, BAD, UNK = "#1a7f37", "#9a6700", "#cf222e", "#57606a"

parts: list[str] = []


def box(x, y, w, h, lines, fill=ENGINE, stroke=ENGINE_B, bold_first=True, size=16, rx=10, align="middle"):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="1.6"/>')
    line_h = size * 1.45
    top = y + h / 2 - line_h * (len(lines) - 1) / 2 + size * 0.35
    tx = x + w / 2 if align == "middle" else x + 16
    for i, text in enumerate(lines):
        weight = "700" if bold_first and i == 0 else "400"
        color = INK if i == 0 else MUTED
        fs = size if i == 0 else size - 2
        parts.append(f'<text x="{tx}" y="{top + i * line_h:.1f}" text-anchor="{align if align == "middle" else "start"}" '
                     f'font-size="{fs}" font-weight="{weight}" fill="{color}">{escape(text)}</text>')


def diamond(cx, cy, w, h, text):
    pts = f"{cx},{cy - h / 2} {cx + w / 2},{cy} {cx},{cy + h / 2} {cx - w / 2},{cy}"
    parts.append(f'<polygon points="{pts}" fill="#ffffff" stroke="{AGENT_B}" stroke-width="1.6"/>')
    parts.append(f'<text x="{cx}" y="{cy + 6}" text-anchor="middle" font-size="16" font-weight="700" '
                 f'fill="{INK}">{escape(text)}</text>')


def arrow(points, label=None, label_at=None, color=LINE, dashed=False):
    d = "M " + " L ".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8"{dash} marker-end="url(#arrow)"/>')
    if label:
        lx, ly = label_at
        parts.append(f'<text x="{lx}" y="{ly}" font-size="14" fill="{MUTED}" text-anchor="middle">{escape(label)}</text>')


def badge(x, y, w, color, title, desc):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="62" rx="8" fill="#ffffff" stroke="{color}" '
                 f'stroke-width="2"/>')
    parts.append(f'<text x="{x + w / 2}" y="{y + 25}" text-anchor="middle" font-size="15" font-weight="700" '
                 f'fill="{color}">{escape(title)}</text>')
    parts.append(f'<text x="{x + w / 2}" y="{y + 47}" text-anchor="middle" font-size="13" fill="{MUTED}">'
                 f'{escape(desc)}</text>')


# ---------------------------------------------------------------- 标题
parts.append(f'<text x="40" y="48" font-size="26" font-weight="700" fill="{INK}">CiteGuard 工作流程</text>')
parts.append(f'<text x="40" y="76" font-size="15" fill="{MUTED}">左：Agent 在 SKILL.md 约束下的写作循环；'
             f'右：verify_references 对每条参考文献的核查过程</text>')

# ---------------------------------------------------------------- 左：Agent 循环
LX, LW = 70, 420
CX = LX + LW / 2
box(LX, 105, LW, 58, ["用户：写一篇带参考文献的综述", "例：扩散模型用于农作物病害数据增广，附 15 条文献"], fill="#ffffff", stroke=LINE)
box(LX, 195, LW, 58, ["Claude Code Agent 加载 SKILL.md", "Skill 规定：先检索、写完核查、按报告修正"], AGENT, AGENT_B)
box(LX, 285, LW, 58, ["search_papers：检索真实论文", "Crossref，返回带 DOI、卷期页码的完整题录"], TOOL, TOOL_B)
box(LX, 375, LW, 58, ["写初稿", "正文 + 编号的参考文献列表"], AGENT, AGENT_B)
box(LX, 465, LW, 58, ["verify_references：核查完整列表", "返回逐条报告（右侧流程）"], TOOL, TOOL_B)
diamond(CX, 600, 250, 82, "有 ⚠️ 或 ❌ ？")
box(LX, 690, LW, 96, ["按报告修正", "⚠️ 按「建议改为」整条替换为数据库题录",
                      "❌ 删除并改写正文对应处，需要时再检索", "❓ 保留并注明未核验"], AGENT, AGENT_B, size=16)
box(LX, 860, LW, 58, ["输出终稿", "只保留通过核查的文献，并附核查说明"], "#e9f7ef", OK)

for y0, y1 in ((163, 195), (253, 285), (343, 375), (433, 465), (523, 559)):
    arrow([(CX, y0), (CX, y1 - 2)])
arrow([(CX, 641), (CX, 688)], "是", (CX + 18, 670))
arrow([(CX - 125, 600), (30, 600), (30, 905), (LX - 2, 905)], "否（全部通过）", (100, 590))
arrow([(LX + LW, 738), (LX + LW + 22, 738), (LX + LW + 22, 508), (LX + LW + 2, 508)])
parts.append(f'<text x="{LX + LW + 56}" y="690" font-size="14" fill="{MUTED}" text-anchor="middle">再次核查</text>')
parts.append(f'<text x="{LX + LW + 56}" y="710" font-size="13" fill="{MUTED}" text-anchor="middle">（最多 3 轮）</text>')

# ---------------------------------------------------------------- 右：核查引擎
RX, RW = 600, 860
parts.append(f'<rect x="{RX - 20}" y="100" width="{RW + 40}" height="840" rx="14" fill="none" stroke="{TOOL_B}" '
             f'stroke-width="1.4" stroke-dasharray="8 6"/>')
parts.append(f'<text x="{RX}" y="128" font-size="17" font-weight="700" fill="{TOOL_B}">verify_references 内部'
             f'（每条参考文献并发处理）</text>')
arrow([(LX + LW + 2, 480), (RX - 22, 480)], color=TOOL_B)

BX, BW = RX + 10, 520
box(BX, 145, BW, 58, ["① 解析", "切分条目，抽取标题、全部作者、年份、DOI、arXiv 编号、页码"], align="start")
box(BX, 228, BW, 76, ["② 按 DOI 取回元数据（Crossref / doi.org）", "比对 DOI 指向论文的标题：",
                      "不一致 → 记录「DOI 指向他文」，继续找正确论文"], align="start")
box(BX, 329, BW, 58, ["③ arXiv 编号查询（arXiv API）", "只用于带 arXiv 编号的条目"], align="start")
box(BX, 412, BW, 76, ["④ 标题检索：Crossref → OpenAlex → Semantic Scholar", "每源前 5 条按自算相似度重排；找到同一篇即停",
                      "副标题被改写时，用「名称:」主标题再查一次"], align="start")
box(BX, 513, BW, 58, ["⑤ 匹配到预印本 → 查找正式发表版本", "以正式版为准比对，并提示正式 DOI"], align="start")
box(BX, 596, BW, 76, ["⑥ 逐字段比对", "全部作者（名字/首字母级、顺序、漏/多）· 年份 ±1",
                      "首页码 · 标题（副标题不同 / 截断 / 前缀）"], align="start")
for y0, y1 in ((203, 228), (304, 329), (387, 412), (488, 513), (571, 596)):
    arrow([(BX + BW / 2, y0), (BX + BW / 2, y1 - 2)])

# 判定
VY = 712
arrow([(BX + BW / 2, 672), (BX + BW / 2, VY - 2)])
parts.append(f'<text x="{BX}" y="{VY - 8}" font-size="14" fill="{MUTED}"></text>')
bw = (RW - 30) / 4
labels = [(OK, "✅ VERIFIED", "存在且题录正确"), (WARN, "⚠️ MISMATCH", "附正确题录与差异"),
          (BAD, "❌ NOT_FOUND", "各源都查不到，附候选"), (UNK, "❓ UNKNOWN", "数据源不可用，不算编造")]
for i, (color, title, desc) in enumerate(labels):
    badge(RX + i * (bw + 10), VY + 4, bw, color, title, desc)
arrow([(RX - 20, 600), (CX + 127, 600)], "核查报告", (CX + 158, 590), color=TOOL_B, dashed=True)

# 右侧说明：数据源与严重程度
NX, NW = BX + BW + 24, RW - BW - 34
box(NX, 145, NW, 186, ["严重程度", "严重：DOI 指向他文 / 不存在、", "编造作者、标题不符", "次要：名字拼写、作者顺序、",
                      "漏作者、年份差 >1、页码", "提示：省略副标题、预印本 DOI"], "#ffffff", LINE, size=15, align="start")
box(NX, 356, NW, 140, ["容错（来自试跑与演示）", "多词姓氏、首字母在前/在后、", "名字缩写（Kr.）、姓名颠倒、",
                      "机构作者、et al.、", "Crossref 早期访问占位页码"], "#ffffff", LINE, size=15, align="start")
box(NX, 521, NW, 151, ["Agent 只拿到", "· 逐条状态与差异说明", "· 可直接替换的正确题录", "· ❌ 条目的真实候选论文",
                      "· 下一步怎么做"], "#ffffff", LINE, size=15, align="start")

# 底部：HTTP 层
box(RX, 812, RW, 108, ["HTTP 层（所有数据源共用）",
                      "本地 JSON 缓存（含 404，不含密钥）· 按接口限速：Crossref DOI 5 次/秒、检索 1 次/秒、arXiv 3 秒/次",
                      "429 / 5xx 指数退避 · Retry-After 超过 30 秒（如 OpenAlex 额度耗尽）立即放弃该数据源并暂停使用",
                      "数据源：Crossref · doi.org（DataCite/arXiv DOI）· OpenAlex · Semantic Scholar · arXiv"],
    "#ffffff", ENGINE_B, size=15, align="start")
arrow([(BX + BW / 2 + 140, 790), (BX + BW / 2 + 140, 810)], dashed=True)
parts.append(f'<text x="{BX + BW / 2 + 152}" y="803" font-size="13" fill="{MUTED}">②③④⑤ 的请求</text>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
<path d="M 0 0 L 10 5 L 0 10 z" fill="{LINE}"/></marker></defs>
<rect width="{W}" height="{H}" fill="#ffffff"/>
{chr(10).join(parts)}
</svg>'''

html = f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>CiteGuard 流程图</title>' \
       f'<style>body{{margin:0;background:#fff}}</style></head><body>{svg}</body></html>'
(HERE / "流程图.html").write_text(html, encoding="utf-8")

shot = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const browser = await chromium.launch();
  const page = await browser.newPage({{ viewport: {{ width: {W}, height: {H} }}, deviceScaleFactor: 2 }});
  await page.goto('file://{HERE / "流程图.html"}');
  await page.screenshot({{ path: '{HERE.parent / "流程图.png"}', fullPage: true }});
  await browser.close();
}})();
"""
subprocess.run(["node", "-e", shot], check=True)
print(HERE.parent / "流程图.png")
