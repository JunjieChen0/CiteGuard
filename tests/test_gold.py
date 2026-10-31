import csv
import json
from pathlib import Path

from experiments import gold


def _write_b0(directory: Path, slug: str, refs: list[str]):
    directory.mkdir(parents=True, exist_ok=True)
    text = "正文。\n\n参考文献\n\n" + "\n".join(f"[{i}] {r}" for i, r in enumerate(refs, 1))
    (directory / f"{slug}__run1.json").write_text(json.dumps({"slug": slug, "response": {"result": text}}),
                                                  encoding="utf-8")


def test_enumerate_uses_independent_splitter(tmp_path):
    _write_b0(tmp_path, "a", ["A. Title one. 2020. DOI: 10.1/a", "B. Title two. 2021."])
    _write_b0(tmp_path, "b", ["C. Title three. 2022."])
    items = gold.enumerate_references(tmp_path)
    assert [(i["id"], i["raw"][:1]) for i in items] == [("a#1", "A"), ("a#2", "B"), ("b#1", "C")]


def test_sample_is_seeded_and_bounded(tmp_path):
    _write_b0(tmp_path, "a", [f"X{i}. Title {i}. 2020." for i in range(30)])
    items = gold.enumerate_references(tmp_path)
    s1 = gold.sample(items, 10, seed=1)
    assert s1 == gold.sample(items, 10, seed=1) and len(s1) == 10
    assert [i["id"] for i in s1] == sorted((i["id"] for i in s1), key=lambda x: (x.split("#")[0], int(x.split("#")[1])))
    assert len(gold.sample(items, 100, seed=1)) == 30


def test_score_confusion_and_metrics(tmp_path):
    gold_rows = [("x#1", "VERIFIED"), ("x#2", "MISMATCH"), ("x#3", "NOT_FOUND"), ("x#4", "MISMATCH"), ("x#5", "VERIFIED")]
    auto = {"x#1": "VERIFIED", "x#2": "MISMATCH", "x#3": "NOT_FOUND", "x#4": "VERIFIED", "x#5": "MISMATCH"}
    m = gold.metrics([(g, auto[i]) for i, g in gold_rows])
    # "有问题" = MISMATCH 或 NOT_FOUND
    assert m["problem"] == {"tp": 2, "fp": 1, "fn": 1, "tn": 1, "precision": 2 / 3, "recall": 2 / 3}
    assert m["not_found"]["recall"] == 1.0 and m["not_found"]["precision"] == 1.0
    assert m["exact_agreement"] == 3 / 5


def test_metrics_handle_zero_division():
    m = gold.metrics([("VERIFIED", "VERIFIED")])
    assert m["problem"]["precision"] is None and m["problem"]["recall"] is None


def test_write_and_read_sample_csv(tmp_path):
    items = [{"id": "a#1", "slug": "a", "idx": 1, "raw": "R, 中文"}]
    path = tmp_path / "s.csv"
    gold.write_csv(path, items, ["id", "slug", "idx", "raw"])
    with path.open(encoding="utf-8-sig") as f:
        assert next(csv.DictReader(f))["raw"] == "R, 中文"


def test_split_ignores_trailing_notes_and_refusal_lists():
    text = ("参考文献\n\n[1] A B. Title one. Venue, 2020. DOI: 10.1/a\n[2] C D. Title two. Venue, 2021.\n\n---\n"
            "说明：参考文献中 [1]–[2] 与正文对应。\n1. 逐条通过 DOI 解析核对；\n2. 补齐条目。\n")
    assert [r[:1] for r in gold.split_references_simple(text)] == ["A", "C"]


def test_second_sample_excludes_first(tmp_path):
    _write_b0(tmp_path, "a", [f"X{i}. Title {i}. 2020." for i in range(30)])
    items = gold.enumerate_references(tmp_path)
    first = gold.sample(items, 10, seed=1)
    second = gold.sample([i for i in items if i["id"] not in {f["id"] for f in first}], 10, seed=2)
    assert not {i["id"] for i in first} & {i["id"] for i in second}


def test_split_marks_hidden_for_blind_annotation():
    text = ("## 参考文献\n[1] He K. Deep residual learning. CVPR, 2016. DOI: 10.1109/CVPR.2016.90.【核查：✅】\n"
            "[2] Doe J. Fake paper. 2020.【核查：⚠️】\n[3] Roe R. Unmarked. 2019.")
    assert gold.split_references_simple(text) == [
        "He K. Deep residual learning. CVPR, 2016. DOI: 10.1109/CVPR.2016.90.", "Doe J. Fake paper. 2020.",
        "Roe R. Unmarked. 2019."]
    assert gold.agent_marks(text) == ["✅", "⚠️", ""]
