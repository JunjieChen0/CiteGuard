"""用第 3 步的人工标注（annotation.csv）检验 CiteGuard 的自动判定。

注意：第 4 步的判定规则正是根据这批引用总结出来的，这里的一致率只是"规则是否实现正确"的回归检查，
不能当作泛化精度；正式的精确率/召回率在第 7 步用新的金标准计算。

用法：
    uv run python -m experiments.eval_pilot
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from citeguard.checker import build_default_checker
from citeguard.matcher import TitleMatch, compare_titles
from experiments.pilot import RESULTS_DIR

ROUND_DIRS = [RESULTS_DIR / "pilot", RESULTS_DIR / "pilot_r2"]
OUT_PATH = RESULTS_DIR / "pilot_eval.csv"


def load_gold(directory: Path) -> dict[tuple[str, int], dict]:
    with (directory / "annotation.csv").open(encoding="utf-8-sig") as f:
        return {(row["slug"], int(row["idx"])): row for row in csv.DictReader(f)}


def main() -> int:
    checker = build_default_checker()
    rows = []
    for directory in ROUND_DIRS:
        gold = load_gold(directory)
        for path in sorted(directory.glob("*__run*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            text = (record.get("response") or {}).get("result", "")
            for idx, result in enumerate(checker.check_text(text), 1):
                g = gold.get((record["slug"], idx))
                aligned = g is not None and compare_titles(result.reference.title, g["raw"])[0] is not TitleMatch.SAME
                rows.append({
                    "round": directory.name, "slug": record["slug"], "idx": idx,
                    "gold": g["status"] if g else "（无标注）",
                    "auto": result.status.value,
                    "agree": bool(g) and g["status"] == result.status.value,
                    "title": result.reference.title,
                    "diffs": " | ".join(f"[{d.severity.value}] {d.message}" for d in result.diffs),
                    "matched_doi": result.matched.doi if result.matched else "",
                    "note": result.note[:300],
                    "_aligned": aligned or g is None,
                })
                print(f"{record['slug']}#{idx} gold={rows[-1]['gold']} auto={result.status.value}", file=sys.stderr)

    with OUT_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[k for k in rows[0] if not k.startswith("_")])
        writer.writeheader()
        writer.writerows({k: v for k, v in r.items() if not k.startswith("_")} for r in rows)

    sys.stdout.reconfigure(encoding="utf-8")
    labelled = [r for r in rows if r["gold"] != "（无标注）"]
    confusion = Counter((r["gold"], r["auto"]) for r in labelled)
    statuses = ["VERIFIED", "MISMATCH", "NOT_FOUND", "UNKNOWN"]
    print(f"自动判定 {len(rows)} 条，有人工标注 {len(labelled)} 条，一致 {sum(r['agree'] for r in labelled)} 条\n")
    print("| 人工 \\ 自动 | " + " | ".join(statuses) + " |")
    print("|---" * (len(statuses) + 1) + "|")
    for g in statuses[:3]:
        print(f"| {g} | " + " | ".join(str(confusion[(g, a)]) for a in statuses) + " |")
    print(f"\n逐条结果：{OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
