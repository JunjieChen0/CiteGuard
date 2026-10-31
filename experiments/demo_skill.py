"""第 5 步：接入 CiteGuard（MCP + Skill）后让 Agent 写综述，记录完整的工具调用过程。

用法：
    uv run python -m experiments.demo_skill resnet rl-greenhouse
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from citeguard.checker import build_default_checker
from citeguard.report import summarize
from experiments.agent_runner import (
    CACHE_DIR,
    CITEGUARD_TOOLS,
    SKILL_DIR,
    run_agent,
    tool_calls,
    write_citeguard_mcp_config,
)
from experiments.pilot import RESULTS_DIR, ROUNDS, build_prompt

OUT_DIR = RESULTS_DIR / "demo"
_NO_TOOLS = "直接输出文本，不要使用任何工具。"


def neutral_prompt(topic: str, template: str) -> str:
    """试跑提示词去掉"不要使用任何工具"：接入 Skill 的条件必须允许调用工具（第 8 步 B0 也应使用同一版本）。"""
    return build_prompt(topic, template).replace(_NO_TOOLS, "直接输出综述文本。")


_SUMMARY_RE = re.compile(r"共 (\d+) 条：✅ (\d+)\s+⚠️ (\d+)\s+❌ (\d+)\s+❓ (\d+)")


def verify_rounds(response: dict) -> list[dict]:
    """从工具调用记录中取出每一轮 verify_references 的统计。"""
    names: dict[str, str] = {}
    rounds = []
    for event in response.get("transcript", []):
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use":
                names[block["id"]] = block["name"]
            elif block.get("type") == "tool_result" and names.get(block.get("tool_use_id"), "").endswith(
                    "verify_references"):
                raw = block.get("content")
                text = raw if isinstance(raw, str) else "".join(x.get("text", "") for x in raw or [])
                m = _SUMMARY_RE.search(text.replace("\\n", "\n"))
                if m:
                    total, ok, mismatch, missing, unknown = map(int, m.groups())
                    rounds.append({"total": total, "VERIFIED": ok, "MISMATCH": mismatch, "NOT_FOUND": missing,
                                   "UNKNOWN": unknown})
    return rounds


def find_topic(slug: str) -> tuple[str, dict]:
    for name, cfg in ROUNDS.items():
        for item in cfg["topics"]:
            if item["slug"] == slug:
                return name, item
    raise KeyError(slug)


def run_demo(slug: str) -> Path:
    round_name, item = find_topic(slug)
    prompt = neutral_prompt(item["topic"], ROUNDS[round_name]["template"])
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="citeguard-demo-") as tmp:
        workdir = Path(tmp)
        config = write_citeguard_mcp_config(workdir / "mcp.json", cache_dir=CACHE_DIR)
        response = run_agent(prompt, workdir, mcp_config=config, allowed_tools=CITEGUARD_TOOLS,
                             skill_dir=SKILL_DIR, stream=True, timeout=1800)
    elapsed = time.monotonic() - started
    final_check = build_default_checker(cache_dir=CACHE_DIR).check_text(response.get("result", ""))
    record = {
        **item, "round": round_name, "condition": "S", "prompt": prompt,
        "timestamp": datetime.now(timezone.utc).isoformat(), "elapsed_s": round(elapsed),
        "tool_calls": tool_calls(response),
        "verify_rounds": verify_rounds(response),
        "permission_denials": [p.get("tool_name") for p in response.get("permission_denials", [])],
        "final_check": summarize(final_check),
        "final_check_detail": [{"title": r.reference.title, "status": r.status.value,
                                "diffs": [d.message for d in r.diffs]} for r in final_check],
        "response": response,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{slug}__S.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="接入 CiteGuard 后的演示运行")
    parser.add_argument("slugs", nargs="+")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    for slug in args.slugs:
        path = run_demo(slug)
        record = json.loads(path.read_text(encoding="utf-8"))
        print(f"{path}\n  工具调用：{record['tool_calls']}\n  核查轮次：{record['verify_rounds']}\n"
              f"  终稿独立核查：{record['final_check']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
