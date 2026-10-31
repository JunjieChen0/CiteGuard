# CiteGuard：学术引用核查 Skill

Agent 写综述时会编造参考文献：DOI 指向别的论文、作者名字是编的、标题和年份记错，甚至论文根本不存在。这些错误格式完全正确，读者很难发现。CiteGuard 是一个 Claude Code Skill + MCP Server，让 Agent 在输出前**检索真实文献、逐条核查、按报告修正**。

- 课程：信息技术前沿与综合素养 · 大作业方向二（Agent Skill 开发）
- 实施计划：[`docs/实施计划.md`](docs/实施计划.md)；失败案例：[`failure_cases/`](failure_cases/)

## 组成

| 部分 | 位置 | 作用 |
|---|---|---|
| MCP Server | `src/citeguard/server.py` | 两个工具：`verify_references`（逐条核查并给出修正建议）、`search_papers`（检索真实论文） |
| Skill | `skill/citeguard/SKILL.md` | 规定 Agent 何时、如何使用这两个工具：先检索 → 写 → 核查 → 修正 → 复查 |
| 核查引擎 | `src/citeguard/` | 解析参考文献 → 查询 Crossref / doi.org / OpenAlex / Semantic Scholar / arXiv → 比对标题、全部作者、年份、页码 → 判定 ✅ ⚠️ ❌ ❓。规则见 [`docs/核查模块.md`](docs/核查模块.md) |

## 环境

- Python ≥ 3.11，[uv](https://docs.astral.sh/uv/)
- Claude Code ≥ 2.1（运行实验时需要）
- 网络能访问 `api.crossref.org`、`doi.org`（必需），`api.openalex.org`、`api.semanticscholar.org`、`export.arxiv.org`（可选）

```bash
uv sync
```

```bash
uv run pytest --cov=citeguard
```

### 可选的环境变量（写在项目根目录 `.env` 或系统环境变量中）

| 变量 | 作用 |
|---|---|
| `DEEPSEEK_API_KEY` | 实验脚本用 DeepSeek 作为 Claude Code 后端时必需 |
| `OPENALEX_API_KEY` | OpenAlex 免费 Key；不配置时同一 IP 共享每日额度，很快耗尽 |
| `S2_API_KEY` | Semantic Scholar Key；不配置时容易被限流 |
| `CROSSREF_MAILTO` | 你的邮箱，进入 Crossref "礼貌池"，更稳定 |
| `CITEGUARD_CACHE_DIR` | 查询缓存目录，默认 `~/.cache/citeguard` |

## 在 Claude Code 中使用

1. 注册 MCP Server（在你要写文章的项目目录里执行）：

```bash
claude mcp add citeguard -- uv run --directory /path/to/CiteGuard citeguard-mcp
```

2. 安装 Skill（项目级；也可以复制到 `~/.claude/skills/` 作为用户级）：

```bash
mkdir -p .claude/skills && cp -r /path/to/CiteGuard/skill/citeguard .claude/skills/
```

3. 直接让 Claude Code 写带参考文献的内容，例如"写一篇关于扩散模型用于农作物病害数据增广的综述，附 10 条参考文献"。Agent 会先用 `search_papers` 找文献，写完后用 `verify_references` 核查并修正。

## 实验脚本

| 命令 | 内容 |
|---|---|
| `uv run python -m experiments.agent_runner "提示词"` | 用 DeepSeek 后端运行一次隔离的 Claude Code |
| `uv run python -m experiments.pilot [--round r2]` | 第 3 步：原生 Agent 试跑（B0） |
| `uv run python -m experiments.check_pilot <结果目录>` | 第 3 步：为人工核查收集证据 |
| `uv run python -m experiments.eval_pilot` | 第 4 步：自动判定与人工标注对照 |
| `uv run python -m experiments.demo_skill <slug>...` | 第 5 步：接入 CiteGuard 后的演示运行，记录完整工具调用 |

实验运行在临时目录中，使用独立的 Claude Code 配置目录（`.claude-runtime/`），不会读取或修改你本机的 Claude Code 设置。

## 适用边界

- 只核查**论文是否存在、题录是否正确**，不判断论文内容是否支持正文论点；
- 只覆盖英文学术文献（依赖 Crossref 等英文数据库的收录范围）；
- 数据源不可用时判为 ❓ UNKNOWN，不会把真论文误判为编造，但也无法给出结论。
