"""第 3 步小规模试跑：让原生 Agent 就若干主题写短综述，保存原始输出供人工核查引用。

用法：
    uv run python -m experiments.pilot                 # 第 1 轮：跑全部主题（已有结果的跳过）
    uv run python -m experiments.pilot --only snn-edge --runs 2
    uv run python -m experiments.pilot --round r2      # 第 2 轮：更细的主题 + 要求直接相关文献
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from experiments.agent_runner import PROJECT_ROOT, run_agent

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DEFAULT_OUT_DIR = RESULTS_DIR / "pilot"

# niche：冷门/交叉主题，容易暴露编造；hot：热门主题对照
TOPICS: list[dict[str, str]] = [
    {"slug": "gnn-tcm", "topic": "图神经网络用于中药配伍规律挖掘", "kind": "niche"},
    {"slug": "snn-edge", "topic": "脉冲神经网络在边缘设备上的片上训练", "kind": "niche"},
    {"slug": "diffusion-flower", "topic": "扩散模型用于花卉图像数据增广", "kind": "niche"},
    {"slug": "llm-ancient-poetry", "topic": "大语言模型用于中国古典诗词格律检测", "kind": "niche"},
    {"slug": "fl-beekeeping", "topic": "联邦学习在智慧养蜂（蜂群健康监测）中的应用", "kind": "niche"},
    {"slug": "resnet", "topic": "深度残差网络（ResNet）及其主要变体", "kind": "hot"},
]

PROMPT_TEMPLATE = (
    "用中文写一篇约 500 字的综述，主题是：{topic}。"
    "文末列出 8–10 条英文参考文献，每条包含作者、标题、会议/期刊、年份、DOI。"
    "直接输出文本，不要使用任何工具。"
)

# 第 2 轮：第 1 轮编造率为 0，模型靠引用通用经典回避冷门交叉领域（见 docs/试跑结果.md）。
# 本轮要求直接相关、较新的文献并增加条数，主题也更细。
TOPICS_R2: list[dict[str, str]] = [
    {"slug": "llm-tcm-prescription", "topic": "大语言模型用于中医处方生成与评估", "kind": "niche"},
    {"slug": "diffusion-crop-disease", "topic": "扩散模型用于农作物病害图像数据增广", "kind": "niche"},
    {"slug": "gnn-power-transient", "topic": "图神经网络用于电力系统暂态稳定评估", "kind": "niche"},
    {"slug": "snn-event-drone", "topic": "脉冲神经网络处理事件相机数据用于无人机避障", "kind": "niche"},
    {"slug": "llm-classical-chinese-ner", "topic": "大语言模型用于古汉语命名实体识别", "kind": "niche"},
    {"slug": "rl-greenhouse", "topic": "强化学习用于温室环境智能控制", "kind": "niche"},
    {"slug": "vit-efficient", "topic": "视觉 Transformer（ViT）的高效化变体", "kind": "hot"},
]

PROMPT_TEMPLATE_R2 = (
    "用中文写一篇约 800 字的综述，主题是：{topic}。"
    "文末列出 15 条英文参考文献，必须是直接研究该主题的论文，"
    "不要引用通用的基础模型或经典方法论文，优先选择 2022 年以后发表的工作。"
    "每条包含全部作者、标题、会议/期刊、年份、卷期页码、DOI。"
    "直接输出文本，不要使用任何工具。"
)

ROUNDS: dict[str, dict] = {
    "r1": {"topics": TOPICS, "template": PROMPT_TEMPLATE, "out": DEFAULT_OUT_DIR},
    "r2": {"topics": TOPICS_R2, "template": PROMPT_TEMPLATE_R2, "out": RESULTS_DIR / "pilot_r2"},
}

Runner = Callable[[str, Path], dict]


def build_prompt(topic: str, template: str = PROMPT_TEMPLATE) -> str:
    return template.format(topic=topic)


def result_path(out_dir: Path, slug: str, run: int) -> Path:
    return out_dir / f"{slug}__run{run}.json"


def _default_runner(prompt: str, workdir: Path) -> dict:
    return run_agent(prompt, workdir)


def run_pilot(
    topics: list[dict[str, str]],
    out_dir: Path,
    runner: Runner = _default_runner,
    runs: int = 1,
    template: str = PROMPT_TEMPLATE,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for item in topics:
        for run in range(1, runs + 1):
            path = result_path(out_dir, item["slug"], run)
            if path.exists():
                continue
            prompt = build_prompt(item["topic"], template)
            response, error = None, None
            with tempfile.TemporaryDirectory(prefix="citeguard-pilot-") as workdir:
                try:
                    response = runner(prompt, Path(workdir))
                except Exception as exc:  # 记录失败而不中断整批试跑
                    error = str(exc)
            record = {
                **item,
                "run": run,
                "prompt": prompt,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response": response,
                "error": error,
            }
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            saved.append(path)
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="原生 Agent 引用编造率试跑")
    parser.add_argument("--only", nargs="*", help="只跑这些 slug")
    parser.add_argument("--round", choices=sorted(ROUNDS), default="r1", help="试跑轮次")
    parser.add_argument("--out", type=Path, help="输出目录（默认按轮次）")
    parser.add_argument("--runs", type=int, default=1, help="每个主题重复次数")
    args = parser.parse_args(argv)

    cfg = ROUNDS[args.round]
    topics = [t for t in cfg["topics"] if not args.only or t["slug"] in args.only]
    saved = run_pilot(topics, args.out or cfg["out"], runs=args.runs, template=cfg["template"])

    sys.stdout.reconfigure(encoding="utf-8")
    for path in saved:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
