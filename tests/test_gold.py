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
