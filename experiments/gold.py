"""第 7 步金标准：从 B0 输出中随机抽取引用，收集独立证据供人工标注，标注完成后再给冻结版本的 CiteGuard 打分。

独立性：抽样与证据收集不使用 citeguard 包（条目切分用本文件中极简、可人工审查的规则），
CiteGuard 只在 score 阶段、标注完成之后运行。

用法：
    uv run python -m experiments.gold sample      # → results/gold/sample.csv
    uv run python -m experiments.gold evidence    # → results/gold/evidence.json + evidence.md（人工核对用）
    uv run python -m experiments.gold score       # 读 annotation.csv，输出混淆矩阵与精确率/召回率
    uv run python -m experiments.gold sample --set 2   # gold-2：从 gold-1 之外的条目中再抽 100 条（结果在 results/gold2/）
    uv run python -m experiments.gold sample --condition S   # 第 8 步：从 S（或 B1）条件中随机抽 40 条（results/review_S/）
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from experiments.pilot import RESULTS_DIR

B0_DIR = RESULTS_DIR / "main" / "B0"
GOLD_DIR = RESULTS_DIR / "gold"
GOLD2_DIR = RESULTS_DIR / "gold2"
GOLD3_DIR = RESULTS_DIR / "gold3"
SAMPLE_SIZE = 100
SEED = 20261031
SEED2 = 20261101
SEED3 = 20261102
MAIN_REVIEW_SIZE = 40
MAIN_REVIEW_SEED = 20261103
ABLATION_REVIEW_SEED = 20261104  # 消融条件 S-mark / S-noskill（实验设计变更记录 11）
REVIEW_SEEDS = {"B1": MAIN_REVIEW_SEED, "S": MAIN_REVIEW_SEED,
                "S-mark": ABLATION_REVIEW_SEED, "S-noskill": ABLATION_REVIEW_SEED}
STATUSES = ["VERIFIED", "MISMATCH", "NOT_FOUND"]


def _order(item_id: str) -> tuple[str, int]:
    slug, idx = item_id.split("#")
    return slug, int(idx)


_ITEM_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)、])\s+(.*\S)")
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


_MARK_RE = re.compile(r"\s*【核查[:：]\s*([^】]*)】")


def split_marks(raw: str) -> tuple[str, str]:
    """S-mark 条件中 Agent 在条目末尾加的【核查：✅】标记：返回（去掉标记的条目, 标记内容）。"""
    marks = _MARK_RE.findall(raw)
    return _MARK_RE.sub("", raw).strip(), " ".join(m.strip() for m in marks)


def split_references_simple(text: str) -> list[str]:
    """以 [n] 或 n. 开头且含年份的行即一条参考文献（去掉【核查：…】标记，盲标时看不到）。

    不依赖"参考文献"标题（Agent 常在文末说明里再次提到这个词），也排除拒答说明中的编号列表。
    """
    return [split_marks(m.group(3))[0] for line in text.splitlines()
            if (m := _ITEM_RE.match(line)) and _YEAR_RE.search(m.group(3))]


def agent_marks(text: str) -> list[str]:
    """与 split_references_simple 逐条对应的 Agent 标记（无标记为空串）。"""
    return [split_marks(m.group(3))[1] for line in text.splitlines()
            if (m := _ITEM_RE.match(line)) and _YEAR_RE.search(m.group(3))]


def enumerate_references(directory: Path) -> list[dict]:
    items = []
    for path in sorted(directory.glob("*__run1.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        text = (record.get("response") or {}).get("result", "")
        for idx, raw in enumerate(split_references_simple(text), 1):
            items.append({"id": f"{record['slug']}#{idx}", "slug": record["slug"], "idx": idx, "raw": raw})
    return items


def sample(items: list[dict], size: int, seed: int = SEED) -> list[dict]:
    chosen = random.Random(seed).sample(items, min(size, len(items)))
    return sorted(chosen, key=lambda i: _order(i["id"]))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- 证据（独立于 citeguard）

def _get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    for attempt in range(6):
        resp = client.get(url, **kwargs)
        if resp.status_code != 429:
            return resp
        retry = resp.headers.get("Retry-After", "")
        if retry.isdigit() and int(retry) > 60:
            return resp
        time.sleep(2 ** attempt)
    return resp


def _csl_summary(data: dict) -> dict:
    date = (data.get("issued") or {}).get("date-parts") or [[None]]
    title = data.get("title")
    return {
        "title": title[0] if isinstance(title, list) and title else title,
        "authors": [f"{a.get('given', '')} {a.get('family') or a.get('literal') or a.get('name', '')}".strip()
                    for a in data.get("author", [])],
        "year": date[0][0] if date and date[0] else None,
        "container": (data.get("container-title") or [None])[0] if isinstance(data.get("container-title"), list)
        else data.get("container-title"),
        "volume": data.get("volume"), "issue": data.get("issue"), "page": data.get("page"),
        "doi": data.get("DOI"), "type": data.get("type"),
    }


def collect_evidence(item: dict, client: httpx.Client) -> dict:
    raw = item["raw"]
    evidence: dict = {**item}
    doi_m = re.search(r"\b(10\.\d{4,9}/[^\s\"<>，。]+)", raw)
    doi = doi_m.group(1).rstrip(".,;)]") if doi_m else None
    evidence["claimed_doi"] = doi
    if doi:
        resp = _get(client, f"https://doi.org/{quote(doi, safe='/()')}",
                    headers={"Accept": "application/vnd.citationstyles.csl+json"}, follow_redirects=True)
        evidence["doi_status"] = resp.status_code
        evidence["doi_record"] = _csl_summary(resp.json()) if resp.status_code == 200 else None
        time.sleep(0.3)
    query = re.sub(r"\bDOI\b.*$", "", raw)
    resp = _get(client, "https://api.crossref.org/works", params={"query.bibliographic": query[:300], "rows": 3})
    evidence["crossref_search"] = [_csl_summary(i) for i in resp.json()["message"]["items"]] \
        if resp.status_code == 200 else f"HTTP {resp.status_code}"
    time.sleep(1.0)
    return evidence


def evidence_markdown(evidence: list[dict]) -> str:
    lines = ["# 金标准证据（人工核对用）", ""]
    for e in evidence:
        lines += [f"## {e['id']}", "", f"**Agent**：{e['raw']}", ""]
        rec = e.get("doi_record")
        if e.get("claimed_doi"):
            lines.append(f"**DOI {e['claimed_doi']} → HTTP {e.get('doi_status')}**")
            if rec:
                lines += [f"- 标题：{rec['title']}", f"- 作者（{len(rec['authors'])}）：{', '.join(rec['authors'])}",
                          f"- {rec['container']} · {rec['year']} · 卷 {rec['volume']} 期 {rec['issue']} · "
                          f"页 {rec['page']} · {rec['type']}"]
        lines.append("")
        lines.append("**Crossref 检索前 3 条**：")
        for hit in e.get("crossref_search") or []:
            if isinstance(hit, dict):
                lines.append(f"- {hit['doi']} · {hit['title']} · {', '.join(hit['authors'][:8])} · {hit['year']} · "
                             f"{hit['container']} {hit['volume']}({hit['issue']}) {hit['page']}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 打分

def _prf(tp: int, fp: int, fn: int, tn: int) -> dict:
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


def metrics(pairs: list[tuple[str, str]]) -> dict:
    """pairs：(人工标注, CiteGuard 判定)。UNKNOWN 计为"未报问题"。"""
    def counts(positive: set[str]) -> dict:
        tp = sum(g in positive and a in positive for g, a in pairs)
        fp = sum(g not in positive and a in positive for g, a in pairs)
        fn = sum(g in positive and a not in positive for g, a in pairs)
        return _prf(tp, fp, fn, len(pairs) - tp - fp - fn)

    return {
        "n": len(pairs),
        "exact_agreement": sum(g == a for g, a in pairs) / len(pairs) if pairs else None,
        "problem": counts({"MISMATCH", "NOT_FOUND"}),
        "not_found": counts({"NOT_FOUND"}),
    }


def score(gold_dir: Path) -> dict:
    from citeguard.checker import build_default_checker
    from citeguard.parser import parse_reference

    rows = [r for r in read_csv(gold_dir / "annotation.csv") if r["gold"] in STATUSES]
    checker = build_default_checker()
    results = []
    for row in rows:
        r = checker.check(parse_reference(row["raw"]))
        results.append({**row, "auto": r.status.value,
                        "auto_diffs": " | ".join(f"[{d.severity.value}] {d.message}" for d in r.diffs),
                        "auto_note": r.note[:200]})
    write_csv(gold_dir / "scored.csv", results, list(results[0]))
    return metrics([(r["gold"], r["auto"]) for r in results])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="金标准")
    parser.add_argument("command", choices=["sample", "evidence", "score"])
    parser.add_argument("--set", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--condition", choices=sorted(REVIEW_SEEDS), help="第 8 步：从该条件的输出中抽样")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    gold_dir = {1: GOLD_DIR, 2: GOLD2_DIR, 3: GOLD3_DIR}[args.set]
    if args.condition:
        gold_dir = RESULTS_DIR / f"review_{args.condition}"
    if args.command == "sample" and args.condition:
        items = enumerate_references(RESULTS_DIR / "main" / args.condition)
        chosen = sample(items, MAIN_REVIEW_SIZE, seed=REVIEW_SEEDS[args.condition])
        write_csv(gold_dir / "sample.csv", chosen, ["id", "slug", "idx", "raw"])
        print(f"{args.condition}：共 {len(items)} 条，抽取 {len(chosen)} 条 → {gold_dir / 'sample.csv'}")
    elif args.command == "sample":
        items = enumerate_references(B0_DIR)
        previous = [GOLD_DIR, GOLD2_DIR][:args.set - 1]  # gold-2 排除 gold-1；gold-3 排除前两批（即剩余全部）
        used = {row["id"] for d in previous for row in read_csv(d / "sample.csv")}
        items = [i for i in items if i["id"] not in used]
        chosen = sample(items, SAMPLE_SIZE, seed={1: SEED, 2: SEED2, 3: SEED3}[args.set])
        write_csv(gold_dir / "sample.csv", chosen, ["id", "slug", "idx", "raw"])
        print(f"可抽 {len(items)} 条，抽取 {len(chosen)} 条 → {gold_dir / 'sample.csv'}")
    elif args.command == "evidence":
        items = read_csv(gold_dir / "sample.csv")
        with httpx.Client(timeout=30, headers={"User-Agent": "CiteGuard-gold/0.1"}) as client:
            evidence = [collect_evidence(i, client) for i in items]
        (gold_dir / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
        (gold_dir / "evidence.md").write_text(evidence_markdown(evidence), encoding="utf-8")
        print(gold_dir / "evidence.md")
    else:
        print(json.dumps(score(gold_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
