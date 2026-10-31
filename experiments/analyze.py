"""第 8 步统计：每篇综述的引用数、自动判定、人工复核后的判定、代价与工具调用。

引用切分用金标准的极简规则（不依赖 CiteGuard 解析器）；自动判定用冻结的 CiteGuard；
人工复核结果（review.csv：condition,id,final）覆盖自动判定（计划 §5.4：所有 ⚠️/❌ 人工复核）。

用法：
    uv run python -m experiments.analyze            # → results/main/per_article.csv, per_reference.csv, summary.json
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from experiments.agent_runner import tool_calls
from experiments.experiment import OUT_DIR
from experiments.gold import agent_marks, split_references_simple

STATUSES = ["VERIFIED", "MISMATCH", "NOT_FOUND", "UNKNOWN"]
REQUIRED_REFS = 10


def collect(out_dir: Path, conditions: list[str], judge: Callable[[str], str]):
    rows, refs = [], []
    for cond in conditions:
        for path in sorted((out_dir / cond).glob("*__run1.json")):
            rec = json.loads(path.read_text(encoding="utf-8"))
            resp = rec.get("response") or {}
            items = split_references_simple(resp.get("result", ""))
            marks = agent_marks(resp.get("result", ""))
            usage = resp.get("usage") or {}
            calls = Counter(tool_calls(resp))
            verdicts = []
            for idx, raw in enumerate(items, 1):
                v = judge(raw)
                verdicts.append(v)
                refs.append({"condition": cond, "slug": rec["slug"], "id": f"{rec['slug']}#{idx}", "raw": raw, "auto": v,
                             "agent_mark": marks[idx - 1]})
            auto = Counter(verdicts)
            rows.append({
                "condition": cond, "slug": rec["slug"], "kind": rec.get("kind", ""), "error": bool(rec.get("error")),
                "n_refs": len(items), "refused": len(items) == 0,
                **{f"auto_{s}": auto[s] for s in STATUSES},
                "elapsed_s": rec.get("elapsed_s"), "turns": resp.get("num_turns"),
                "input_tokens": (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0),
                "output_tokens": usage.get("output_tokens"),
                "search_calls": calls["mcp__citeguard__search_papers"],
                "verify_calls": calls["mcp__citeguard__verify_references"],
                "skill_calls": calls["Skill"],
                "denied_calls": len(resp.get("permission_denials") or []),
            })
    return rows, refs


def summarize(rows: list[dict], refs: list[dict], review: dict[tuple[str, str], str]) -> dict:
    out = {}
    for cond in dict.fromkeys(r["condition"] for r in rows):
        crow = [r for r in rows if r["condition"] == cond]
        cref = [r for r in refs if r["condition"] == cond]
        final = [review.get((cond, r["id"]), r["auto"]) for r in cref]
        final_by_slug: dict[str, list[str]] = {}
        for r, f in zip(cref, final):
            final_by_slug.setdefault(r["slug"], []).append(f)
        usable = sum(1 for slug, fs in final_by_slug.items() if len(fs) >= REQUIRED_REFS and all(f == "VERIFIED" for f in fs))

        def mean(key):
            vals = [r[key] for r in crow if r[key] is not None]
            return round(sum(vals) / len(vals), 1) if vals else None

        out[cond] = {
            "articles": len(crow), "refusals": sum(r["refused"] for r in crow), "refs": len(cref),
            "auto": {s: sum(r["auto"] == s for r in cref) for s in STATUSES},
            "final": {s: Counter(final)[s] for s in STATUSES},
            "usable_articles": usable,
            "needs_fix_per_article": round(sum(f != "VERIFIED" for f in final) / max(len(crow), 1), 2),
            "mean_elapsed_s": mean("elapsed_s"), "mean_output_tokens": mean("output_tokens"),
            "mean_input_tokens": mean("input_tokens"), "mean_turns": mean("turns"),
            "mean_search_calls": mean("search_calls"), "mean_verify_calls": mean("verify_calls"),
            "articles_calling_verify": sum(r["verify_calls"] > 0 for r in crow),
            "mean_denied_calls": mean("denied_calls"),
        }
    return out


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    from citeguard.checker import build_default_checker
    from citeguard.parser import parse_reference

    checker = build_default_checker()
    rows, refs = collect(OUT_DIR, ["B0", "B1", "S", "S-mark", "S-noskill"], judge=lambda raw: checker.check(parse_reference(raw)).status.value)
    review_path = OUT_DIR / "review.csv"
    review = {}
    if review_path.exists():
        with review_path.open(encoding="utf-8-sig") as f:
            review = {(r["condition"], r["id"]): r["final"] for r in csv.DictReader(f)}
    _write(OUT_DIR / "per_article.csv", rows)
    _write(OUT_DIR / "per_reference.csv", refs)
    summary = summarize(rows, refs, review)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
