import json
from pathlib import Path

from experiments import experiment
from experiments.experiment import CONDITIONS, TEST_TOPICS, build_prompt_for, result_path, run_condition
from experiments.pilot import ROUNDS


def test_test_topics_are_new_unique_and_balanced():
    slugs = [t["slug"] for t in TEST_TOPICS]
    dev = {t["slug"] for cfg in ROUNDS.values() for t in cfg["topics"]}
    assert len(slugs) == 25 == len(set(slugs))
    assert not dev & set(slugs)
    assert sum(t["kind"] == "hot" for t in TEST_TOPICS) == 10


def test_prompts_identical_except_b1_suffix():
    b0, b1, s = (build_prompt_for(c, "主题X") for c in ("B0", "B1", "S"))
    assert b0 == s
    assert b1.startswith(b0) and len(b1) > len(b0)
    assert "不要使用任何工具" not in b0
    assert "全部作者" in b0 and "10 条" in b0


def test_conditions_tools():
    assert CONDITIONS["B0"]["tools"] == [] and CONDITIONS["B1"]["tools"] == []
    assert "Skill" in CONDITIONS["S"]["tools"] and CONDITIONS["S"]["skill"]


def test_ablation_conditions():
    smark, noskill = CONDITIONS["S-mark"], CONDITIONS["S-noskill"]
    assert smark["tools"] == ["mcp__citeguard__verify_references"] and not smark["skill"]
    assert "不要修改" in build_prompt_for("S-mark", "主题X")
    assert "Skill" not in noskill["tools"] and not noskill["skill"]
    assert build_prompt_for("S-noskill", "主题X") == build_prompt_for("S", "主题X")


def test_run_condition_saves_and_skips_existing(tmp_path: Path):
    calls = []

    def runner(condition, prompt, workdir):
        calls.append((condition, prompt))
        return {"result": "x", "transcript": [], "usage": {}}

    topics = TEST_TOPICS[:2]
    saved = run_condition("B0", topics, tmp_path, runner=runner)
    assert len(saved) == 2 and len(calls) == 2
    record = json.loads(result_path(tmp_path, "B0", topics[0]["slug"], 1).read_text(encoding="utf-8"))
    assert record["condition"] == "B0" and record["prompt"] == build_prompt_for("B0", topics[0]["topic"])
    assert run_condition("B0", topics, tmp_path, runner=runner) == []


def test_run_condition_records_errors(tmp_path: Path):
    def runner(condition, prompt, workdir):
        raise RuntimeError("timeout")

    run_condition("B1", TEST_TOPICS[:1], tmp_path, runner=runner)
    record = json.loads(result_path(tmp_path, "B1", TEST_TOPICS[0]["slug"], 1).read_text(encoding="utf-8"))
    assert record["response"] is None and "timeout" in record["error"]


def test_main_parses_args(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(experiment, "run_condition",
                        lambda c, topics, out, runs=1: seen.update(c=c, n=len(topics), runs=runs) or [])
    assert experiment.main(["B1", "--only", TEST_TOPICS[0]["slug"], "--runs", "2", "--out", str(tmp_path)]) == 0
    assert seen == {"c": "B1", "n": 1, "runs": 2}
