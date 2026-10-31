from experiments import ablation


def test_compare_detects_changed_and_removed():
    submitted = ["A. Paper one. 2020.", "B. Paper two. 2021.", "C. Paper three. 2022."]
    final = ["A. Paper one. 2020", "B. Paper 2 (fixed). 2021.", "D. New. 2023."]
    r = ablation.compare(submitted, final)
    assert r == {"submitted": 3, "final": 3, "unchanged": 1, "changed_or_added": 2, "removed": 2}


def test_first_verify_input():
    resp = {"transcript": [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "mcp__citeguard__verify_references", "input": {"text": "[1] X. 2020."}}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "mcp__citeguard__verify_references", "input": {"text": "second"}}]}},
    ]}
    assert ablation.first_verify_input(resp) == "[1] X. 2020."
    assert ablation.first_verify_input({"transcript": []}) is None
