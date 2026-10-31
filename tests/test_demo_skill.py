from experiments.demo_skill import find_topic, neutral_prompt
from experiments.pilot import PROMPT_TEMPLATE, PROMPT_TEMPLATE_R2


def test_neutral_prompt_drops_no_tool_instruction_only():
    for template in (PROMPT_TEMPLATE, PROMPT_TEMPLATE_R2):
        prompt = neutral_prompt("主题X", template)
        assert "不要使用任何工具" not in prompt
        assert "主题X" in prompt and "DOI" in prompt


def test_find_topic_across_rounds():
    assert find_topic("resnet") == ("r1", {"slug": "resnet", "topic": "深度残差网络（ResNet）及其主要变体", "kind": "hot"})
    assert find_topic("rl-greenhouse")[0] == "r2"


def test_verify_rounds_extracts_counts_from_tool_results():
    from experiments.demo_skill import verify_rounds

    report = "## CiteGuard 核查报告\n\n共 10 条：✅ 8　⚠️ 1　❌ 1　❓ 0\n"
    response = {"transcript": [
        {"type": "system", "message": "plain string message"},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "mcp__citeguard__verify_references", "input": {"text": "x"}},
            {"type": "tool_use", "id": "t2", "name": "mcp__citeguard__search_papers", "input": {"query": "q"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": report}]},
            {"type": "tool_result", "tool_use_id": "t2", "content": "检索结果"}]}},
    ]}
    assert verify_rounds(response) == [{"total": 10, "VERIFIED": 8, "MISMATCH": 1, "NOT_FOUND": 1, "UNKNOWN": 0}]
