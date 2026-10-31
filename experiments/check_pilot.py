"""第 3 步人工核查辅助：逐条取回试跑引用中 DOI 指向的真实元数据，并按标题检索正确记录。

这是一次性核查脚本，只负责"把证据摆出来"，最终判定由人工完成并写入
experiments/results/pilot/annotation.csv。正式的核查逻辑在第 4 步 TDD 实现。

用法：
    uv run python -m experiments.check_pilot > experiments/results/pilot/evidence.json
"""

from __future__ import annotations

import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from experiments.pilot import DEFAULT_OUT_DIR

CSL_ACCEPT = "application/vnd.citationstyles.csl+json"
DOI_RE = re.compile(r"DOI:\s*(10\.\S+?)\s*$", re.IGNORECASE)
NUMBERED_RE = re.compile(r"^\s*(?:\[\d+\]|\d+\.)\s+(.*)$")


def norm(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", title.lower())).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def references_section(text: str) -> str:
    idx = max(text.rfind("参考文献"), text.rfind("References"))
    return text[idx:] if idx >= 0 else text


def split_references(text: str) -> list[str]:
    refs = []
    for line in references_section(text).splitlines():
        m = NUMBERED_RE.match(line)
        if m and "DOI" in line:
            refs.append(m.group(1).strip())
    return refs


def guess_title(ref: str) -> str:
    quoted = re.search(r"[\"“](.+?)[\"”]", ref)
    if quoted:
        return quoted.group(1).rstrip(".")
    apa = re.search(r"\(\d{4}\)\.\s*(.+?)\.\s+\*", ref)
    if apa:
        return apa.group(1)
    head = re.split(r"\*|\s+In:", ref)[0]
    # 作者段多为缩写和逗号；取"长单词"最多的一段作为标题
    segments = re.split(r"(?<!\bvs)\.\s+", head)

    def score(seg: str) -> int:
        if re.search(r"\b(?:19|20)\d{2}\b", seg) or len(re.findall(r"\b[A-Z]\b", seg)) >= 2:
            return -1  # 会议+年份段 或 作者缩写段
        return len(re.findall(r"[A-Za-z]{4,}", seg))

    return max(segments, key=score).strip(" .")


def get_with_retry(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    for attempt in range(6):
        resp = client.get(url, **kwargs)
        if resp.status_code != 429:
            return resp
        time.sleep(2 ** attempt)
    return resp


def fetch_doi(client: httpx.Client, doi: str) -> dict | None:
    resp = get_with_retry(client, f"https://doi.org/{doi}", headers={"Accept": CSL_ACCEPT}, follow_redirects=True)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    authors = [a.get("family") or a.get("literal", "") for a in data.get("author", [])]
    year = None
    for key in ("issued", "published-print", "published-online"):
        parts = (data.get(key) or {}).get("date-parts") or [[None]]
        if parts[0][0]:
            year = parts[0][0]
            break
    title = data.get("title")
    if isinstance(title, list):
        title = title[0] if title else ""
    container = data.get("container-title")
    if isinstance(container, list):
        container = container[0] if container else ""
    return {"doi": data.get("DOI", doi), "title": title, "authors": authors[:4], "year": year,
            "container": container}


def search_crossref(client: httpx.Client, title: str) -> list[dict]:
    resp = get_with_retry(client, "https://api.crossref.org/works",
                      params={"query.bibliographic": title, "rows": 5})
    resp.raise_for_status()
    hits = []
    for item in resp.json()["message"]["items"]:
        t = (item.get("title") or [""])[0]
        hits.append({
            "doi": item.get("DOI"),
            "title": t,
            "authors": [a.get("family", "") for a in item.get("author", [])][:4],
            "year": (item.get("issued", {}).get("date-parts") or [[None]])[0][0],
            "container": (item.get("container-title") or [""])[0],
            "sim": round(similarity(title, t), 3),
        })
    return sorted(hits, key=lambda h: -h["sim"])[:3]


def main() -> int:
    evidence = []
    with httpx.Client(timeout=30, headers={"User-Agent": "CiteGuard-pilot/0.1"}) as client:
        for path in sorted(Path(DEFAULT_OUT_DIR).glob("*__run*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            text = (record.get("response") or {}).get("result", "")
            for i, ref in enumerate(split_references(text), 1):
                doi_m = DOI_RE.search(ref)
                doi = doi_m.group(1).rstrip(".") if doi_m else None
                title = guess_title(ref)
                doi_meta = fetch_doi(client, doi) if doi else None
                time.sleep(1.0)
                entry = {"slug": record["slug"], "idx": i, "raw": ref, "claimed_title": title,
                         "claimed_doi": doi, "doi_resolves": doi_meta is not None, "doi_meta": doi_meta}
                if doi_meta:
                    entry["doi_title_sim"] = round(similarity(title, doi_meta["title"] or ""), 3)
                if not doi_meta or entry["doi_title_sim"] < 0.9:
                    entry["crossref_search"] = search_crossref(client, title)
                    time.sleep(1.0)
                evidence.append(entry)
                print(f"{record['slug']}#{i} sim={entry.get('doi_title_sim')} {title[:60]}", file=sys.stderr)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
