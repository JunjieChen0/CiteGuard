import json
from pathlib import Path

from experiments import pilot
from experiments.pilot import TOPICS, build_prompt, result_path, run_pilot


def test_topics_have_unique_slugs_and_one_hot_control():
    slugs = [t["slug"] for t in TOPICS]

    assert len(slugs) == len(set(slugs))
    assert sum(t["kind"] == "hot" for t in TOPICS) == 1
    assert sum(t["kind"] == "niche" for t in TOPICS) >= 5


def test_build_prompt_embeds_topic_and_forbids_tools():
    prompt = build_prompt("脉冲神经网络在边缘设备上的训练")

    assert "脉冲神经网络在边缘设备上的训练" in prompt
    assert "DOI" in prompt
    assert "不要使用任何工具" in prompt


def test_result_path_uses_slug_and_run_index(tmp_path: Path):
    assert result_path(tmp_path, "snn-edge", 2) == tmp_path / "snn-edge__run2.json"


def _fake_runner(calls: list):
    def runner(prompt, workdir):
        calls.append((prompt, workdir))
        return {"result": "综述正文", "is_error": False, "usage": {"input_tokens": 1}}

    return runner


def test_run_pilot_saves_record_per_topic(tmp_path: Path):
    calls: list = []
    topics = [{"slug": "a", "topic": "主题A", "kind": "niche"}]

    saved = run_pilot(topics, tmp_path, runner=_fake_runner(calls))

    record = json.loads((tmp_path / "a__run1.json").read_text(encoding="utf-8"))
    assert saved == [tmp_path / "a__run1.json"]
    assert record["slug"] == "a"
    assert record["topic"] == "主题A"
    assert record["prompt"] == build_prompt("主题A")
    assert record["response"]["result"] == "综述正文"
    assert record["error"] is None
    assert len(calls) == 1


def test_run_pilot_skips_existing_results(tmp_path: Path):
    calls: list = []
    topics = [{"slug": "a", "topic": "主题A", "kind": "niche"}]
    (tmp_path / "a__run1.json").write_text("{}", encoding="utf-8")

    saved = run_pilot(topics, tmp_path, runner=_fake_runner(calls))

    assert saved == []
    assert calls == []


def test_run_pilot_repeats_runs(tmp_path: Path):
    calls: list = []
    topics = [{"slug": "a", "topic": "主题A", "kind": "niche"}]

    run_pilot(topics, tmp_path, runner=_fake_runner(calls), runs=2)

    assert (tmp_path / "a__run2.json").exists()
    assert len(calls) == 2


def test_run_pilot_records_error_instead_of_crashing(tmp_path: Path):
    def failing_runner(prompt, workdir):
        raise RuntimeError("claude 退出码 1：boom")

    topics = [{"slug": "a", "topic": "主题A", "kind": "niche"}]

    run_pilot(topics, tmp_path, runner=failing_runner)

    record = json.loads((tmp_path / "a__run1.json").read_text(encoding="utf-8"))
    assert record["response"] is None
    assert "boom" in record["error"]


def test_main_filters_topics_by_slug(monkeypatch, tmp_path: Path):
    seen: dict = {}

    def fake_run_pilot(topics, out_dir, runs):
        seen.update(slugs=[t["slug"] for t in topics], out_dir=out_dir, runs=runs)
        return []

    monkeypatch.setattr(pilot, "run_pilot", fake_run_pilot)

    code = pilot.main(["--only", TOPICS[0]["slug"], "--out", str(tmp_path), "--runs", "3"])

    assert code == 0
    assert seen == {"slugs": [TOPICS[0]["slug"]], "out_dir": tmp_path, "runs": 3}
