import json

from experiments import analyze


def _record(tmp_path, cond, slug, refs, usage=None, denials=0, tools=()):
    d = tmp_path / cond
    d.mkdir(parents=True, exist_ok=True)
    text = "正文。\n\n参考文献\n\n" + "\n".join(f"[{i}] {r}" for i, r in enumerate(refs, 1))
    transcript = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": n}
                                                                for i, n in enumerate(tools)]}}]
    resp = {"result": text, "usage": usage or {"input_tokens": 10, "output_tokens": 5}, "num_turns": 3,
            "permission_denials": [{"tool_name": "WebSearch"}] * denials, "transcript": transcript}
    (d / f"{slug}__run1.json").write_text(json.dumps({"slug": slug, "kind": "hot", "condition": cond, "elapsed_s": 42,
                                                     "response": resp, "error": None}), encoding="utf-8")


def test_per_article_rows_and_summary(tmp_path):
    _record(tmp_path, "S", "a", ["A B. Real paper. 2020. DOI: 10.1/a", "C D. Fake paper. 2021."],
            tools=["mcp__citeguard__search_papers", "mcp__citeguard__verify_references"])
    _record(tmp_path, "S", "b", [], denials=2)  # 拒答
    verdicts = {"A B. Real paper. 2020. DOI: 10.1/a": "VERIFIED", "C D. Fake paper. 2021.": "NOT_FOUND"}
    rows, refs = analyze.collect(tmp_path, ["S"], judge=lambda raw: verdicts[raw])
    by = {r["slug"]: r for r in rows}
    assert by["a"]["n_refs"] == 2 and by["a"]["auto_NOT_FOUND"] == 1 and by["a"]["search_calls"] == 1
    assert by["b"]["refused"] and by["b"]["denied_calls"] == 2
    s = analyze.summarize(rows, refs, review={})
    assert s["S"]["articles"] == 2 and s["S"]["refusals"] == 1 and s["S"]["refs"] == 2
    assert s["S"]["auto"]["NOT_FOUND"] == 1


def test_review_overrides_auto_verdict(tmp_path):
    _record(tmp_path, "B1", "a", ["A B. Paper. 2020."])
    rows, refs = analyze.collect(tmp_path, ["B1"], judge=lambda raw: "MISMATCH")
    s = analyze.summarize(rows, refs, review={("B1", "a#1"): "VERIFIED"})
    assert s["B1"]["final"]["VERIFIED"] == 1 and s["B1"]["final"]["MISMATCH"] == 0
    assert s["B1"]["usable_articles"] == 0  # 少于 10 条不算可用
