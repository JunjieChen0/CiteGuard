"""第 7、8 步正式实验：25 个新主题 × 三种条件（B0 原生 / B1 仅提示词 / S 接入 CiteGuard）。

与第 3 步试跑（开发集，用来总结判定规则）的主题完全不重叠。三种条件的提示词只有 B1 多一句，
且都不含"不要使用任何工具"（S 必须能调用工具；B0/B1 不放行任何工具，尝试调用会被拒绝并记录）。

用法：
    uv run python -m experiments.experiment B0            # 跑全部主题（已有结果跳过）
    uv run python -m experiments.experiment S --only cnn-architectures
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from experiments.agent_runner import CACHE_DIR, CITEGUARD_TOOLS, SKILL_DIR, run_agent, write_citeguard_mcp_config
from experiments.pilot import RESULTS_DIR

OUT_DIR = RESULTS_DIR / "main"

TEST_TOPICS: list[dict[str, str]] = [
    # 课程热门（10）
    {"slug": "cnn-architectures", "topic": "卷积神经网络经典架构的演进", "kind": "hot"},
    {"slug": "transformer-attention", "topic": "Transformer 与自注意力机制", "kind": "hot"},
    {"slug": "gan-variants", "topic": "生成对抗网络及其主要变体", "kind": "hot"},
    {"slug": "diffusion-sampling", "topic": "扩散模型的基本原理与加速采样方法", "kind": "hot"},
    {"slug": "deep-rl", "topic": "深度强化学习：从 DQN 到 PPO", "kind": "hot"},
    {"slug": "object-detection", "topic": "基于深度学习的目标检测方法", "kind": "hot"},
    {"slug": "semantic-segmentation", "topic": "语义分割网络的发展", "kind": "hot"},
    {"slug": "bert-pretraining", "topic": "BERT 系列预训练语言模型", "kind": "hot"},
    {"slug": "contrastive-ssl", "topic": "对比式自监督表示学习", "kind": "hot"},
    {"slug": "gnn-basics", "topic": "图神经网络的基础模型", "kind": "hot"},
    # 冷门 / 交叉（15）
    {"slug": "gnn-drug-interaction", "topic": "图神经网络用于药物相互作用预测", "kind": "niche"},
    {"slug": "llm-code-review", "topic": "大语言模型用于自动化代码审查", "kind": "niche"},
    {"slug": "rl-traffic-signal", "topic": "强化学习用于交通信号控制", "kind": "niche"},
    {"slug": "diffusion-ldct", "topic": "扩散模型用于低剂量 CT 图像去噪", "kind": "niche"},
    {"slug": "fl-medical-seg", "topic": "联邦学习用于医学影像分割", "kind": "niche"},
    {"slug": "nerf-urban", "topic": "神经辐射场用于大规模城市场景重建", "kind": "niche"},
    {"slug": "snn-speech", "topic": "脉冲神经网络用于语音识别", "kind": "niche"},
    {"slug": "llm-legal-cn", "topic": "大语言模型用于中文法律问答", "kind": "niche"},
    {"slug": "vit-rs-change", "topic": "视觉 Transformer 用于遥感图像变化检测", "kind": "niche"},
    {"slug": "kd-edge-detection", "topic": "知识蒸馏用于边缘设备上的目标检测", "kind": "niche"},
    {"slug": "transformer-load", "topic": "Transformer 用于电力负荷预测", "kind": "niche"},
    {"slug": "gnn-social-rec", "topic": "图神经网络用于社交推荐", "kind": "niche"},
    {"slug": "llm-math-eval", "topic": "大语言模型数学推理能力的评测", "kind": "niche"},
    {"slug": "pointcloud-phenotype", "topic": "点云深度学习用于作物表型分析", "kind": "niche"},
    {"slug": "asr-chinese-dialect", "topic": "端到端语音识别用于汉语方言", "kind": "niche"},
]

PROMPT = ("用中文写一篇约 600 字的综述，主题是：{topic}。"
          "文末列出 10 条英文参考文献，每条包含全部作者、标题、会议/期刊、年份、卷期页码、DOI。")
B1_SUFFIX = "请确保每条参考文献都真实存在、题录准确；不确定的文献宁可不写，也不要编造。"

CONDITIONS: dict[str, dict] = {
    "B0": {"suffix": "", "tools": False},
    "B1": {"suffix": B1_SUFFIX, "tools": False},
    "S": {"suffix": "", "tools": True},
}

Runner = Callable[[str, str, Path], dict]


def build_prompt_for(condition: str, topic: str) -> str:
    return PROMPT.format(topic=topic) + CONDITIONS[condition]["suffix"]


def result_path(out_dir: Path, condition: str, slug: str, run: int) -> Path:
    return out_dir / condition / f"{slug}__run{run}.json"


def _default_runner(condition: str, prompt: str, workdir: Path) -> dict:
    if not CONDITIONS[condition]["tools"]:
        return run_agent(prompt, workdir, stream=True)
    config = write_citeguard_mcp_config(workdir / "mcp.json", cache_dir=CACHE_DIR)
    return run_agent(prompt, workdir, mcp_config=config, allowed_tools=CITEGUARD_TOOLS, skill_dir=SKILL_DIR,
                     stream=True, timeout=1800)


def run_condition(condition: str, topics: list[dict[str, str]], out_dir: Path, runner: Runner = _default_runner,
                  runs: int = 1) -> list[Path]:
    saved = []
    for item in topics:
        for run in range(1, runs + 1):
            path = result_path(out_dir, condition, item["slug"], run)
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            prompt = build_prompt_for(condition, item["topic"])
            response, error = None, None
            started = time.monotonic()
            with tempfile.TemporaryDirectory(prefix=f"citeguard-{condition}-") as workdir:
                try:
                    response = runner(condition, prompt, Path(workdir))
                except Exception as exc:  # 记录失败而不中断整批实验
                    error = str(exc)
            record = {**item, "condition": condition, "run": run, "prompt": prompt,
                      "timestamp": datetime.now(timezone.utc).isoformat(),
                      "elapsed_s": round(time.monotonic() - started), "response": response, "error": error}
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            saved.append(path)
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="正式实验")
    parser.add_argument("condition", choices=sorted(CONDITIONS))
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    topics = [t for t in TEST_TOPICS if not args.only or t["slug"] in args.only]
    saved = run_condition(args.condition, topics, args.out, runs=args.runs)
    sys.stdout.reconfigure(encoding="utf-8")
    for path in saved:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
