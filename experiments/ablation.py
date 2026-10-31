"""消融条件 S-mark 的依从性检查：Agent 是否只加标记、没有改动参考文献（实验设计变更记录 11）。

把每篇最终输出的参考文献与 Agent 最后一次调用 verify_references 时提交的参考文献逐条比较
（去掉标记、空白和末尾标点后完全相同才算未改动），并记录核查调用次数、首次核查提交了几条。
Agent 常先用核查工具试探候选文献再定稿（变更记录 12）。

用法：
    uv run python -m experiments.ablation      # → results/main/S-mark_compliance.csv
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from experiments.experiment import OUT_DIR, VERIFY_TOOL
from experiments.gold import agent_marks, split_references_simple


def verify_inputs(response: dict) -> list[str]:
    """按顺序列出每次 verify_references 提交的文本。"""
    texts = []
    for event in response.get("transcript", []):
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == VERIFY_TOOL:
                texts.append((block.get("input") or {}).get("text", ""))
    return texts


def first_verify_input(response: dict) -> str | None:
    texts = verify_inputs(response)
    return texts[0] if texts else None


def _norm(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip().rstrip("。.").casefold()


def compare(submitted: list[str], final: list[str]) -> dict:
    before = [_norm(r) for r in submitted]
    after = [_norm(r) for r in final]
    unchanged = sum(1 for r in after if r in before)
    return {"submitted": len(before), "final": len(after), "unchanged": unchanged,
            "changed_or_added": len(after) - unchanged, "removed": sum(1 for r in before if r not in after)}


def check(out_dir: Path = OUT_DIR, condition: str = "S-mark") -> list[dict]:
    rows = []
    for path in sorted((out_dir / condition).glob("*__run1.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        resp = rec.get("response") or {}
        text = resp.get("result", "")
        final = split_references_simple(text)
        marks = agent_marks(text)
        inputs = verify_inputs(resp)
        first = split_references_simple(inputs[0]) if inputs else []
        last = split_references_simple(inputs[-1]) if inputs else []
        row = {"slug": rec["slug"], "verify_calls": len(inputs), "first_call_refs": len(first),
               "denied_calls": len(resp.get("permission_denials") or []),
               "marked": sum(1 for m in marks if m), **compare(last, final),
               "unchanged_vs_first": compare(first, final)["unchanged"]}
        rows.append(row)
    return rows


def main() -> int:
    rows = check()
    out = OUT_DIR / "S-mark_compliance.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    sys.stdout.reconfigure(encoding="utf-8")
    total = {k: sum(r[k] for r in rows) for k in ["final", "marked", "unchanged", "changed_or_added",
                                                    "unchanged_vs_first", "verify_calls", "denied_calls"]}
    print(json.dumps({"articles": len(rows), "called_verify": sum(r["verify_calls"] > 0 for r in rows),
                      "first_call_full": sum(r["first_call_refs"] >= 10 for r in rows), **total},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
