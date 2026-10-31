import json
import subprocess
from pathlib import Path

import pytest

from experiments import agent_runner
from experiments.agent_runner import (
    DEEPSEEK_BASE_URL,
    build_command,
    build_env,
    load_dotenv,
    resolve_api_key,
)


def test_load_dotenv_parses_pairs_and_skips_comments(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\n\nDEEPSEEK_API_KEY="sk-abc"\nOTHER=1\n', encoding="utf-8")

    assert load_dotenv(env_file) == {"DEEPSEEK_API_KEY": "sk-abc", "OTHER": "1"}


def test_load_dotenv_returns_empty_when_file_missing(tmp_path: Path):
    assert load_dotenv(tmp_path / "missing.env") == {}


def test_resolve_api_key_prefers_environment_over_dotenv():
    assert resolve_api_key({"DEEPSEEK_API_KEY": "from-env"}, {"DEEPSEEK_API_KEY": "from-file"}) == "from-env"


def test_resolve_api_key_falls_back_to_dotenv():
    assert resolve_api_key({}, {"DEEPSEEK_API_KEY": "from-file"}) == "from-file"


def test_resolve_api_key_raises_when_missing():
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        resolve_api_key({}, {})


def test_build_env_drops_inherited_claude_vars_and_sets_deepseek(tmp_path: Path):
    base = {
        "PATH": "x",
        "ANTHROPIC_API_KEY": "parent-key",
        "ANTHROPIC_AUTH_TOKEN": "parent-token",
        "CLAUDE_CODE_ENTRYPOINT": "desktop",
        "CLAUDECODE": "1",
    }

    env = build_env(base, api_key="sk-test", model="deepseek-flash", config_dir=tmp_path)

    assert env["PATH"] == "x"
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_ENTRYPOINT" not in env
    assert "CLAUDECODE" not in env
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-test"
    assert env["ANTHROPIC_BASE_URL"] == DEEPSEEK_BASE_URL
    assert env["ANTHROPIC_MODEL"] == "deepseek-flash"
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path)


def test_build_env_does_not_mutate_base():
    base = {"ANTHROPIC_API_KEY": "parent-key"}

    build_env(base, api_key="sk-test", model="m", config_dir=Path("."))

    assert base == {"ANTHROPIC_API_KEY": "parent-key"}


def test_build_command_isolates_settings_and_mcp():
    cmd = build_command("claude.exe", model="deepseek-flash", mcp_config=None)

    assert cmd[:2] == ["claude.exe", "-p"]
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--setting-sources") + 1] == "project"
    assert "--strict-mcp-config" in cmd
    assert "--no-session-persistence" in cmd
    assert "--mcp-config" not in cmd


def test_build_command_adds_mcp_config_when_given(tmp_path: Path):
    config = tmp_path / "mcp.json"

    cmd = build_command("claude.exe", model="m", mcp_config=config)

    assert cmd[cmd.index("--mcp-config") + 1] == str(config)


def _patch_runtime(monkeypatch, tmp_path: Path, completed: subprocess.CompletedProcess) -> dict:
    calls: dict = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls.update(kwargs)
        return completed

    monkeypatch.setattr(agent_runner.shutil, "which", lambda _: "claude.exe")
    monkeypatch.setattr(agent_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(agent_runner, "RUNTIME_CONFIG_DIR", tmp_path / "runtime")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    return calls


def test_run_agent_passes_prompt_via_stdin_and_parses_json(monkeypatch, tmp_path: Path):
    completed = subprocess.CompletedProcess([], 0, stdout='{"result": "ok", "is_error": false}', stderr="")
    calls = _patch_runtime(monkeypatch, tmp_path, completed)

    result = agent_runner.run_agent("写一段简介", workdir=tmp_path)

    assert result == {"result": "ok", "is_error": False}
    assert calls["input"] == "写一段简介"
    assert calls["env"]["ANTHROPIC_AUTH_TOKEN"] == "sk-test"
    assert (tmp_path / "runtime").is_dir()


def test_run_agent_raises_on_nonzero_exit(monkeypatch, tmp_path: Path):
    completed = subprocess.CompletedProcess([], 1, stdout="", stderr="boom")
    _patch_runtime(monkeypatch, tmp_path, completed)

    with pytest.raises(RuntimeError, match="boom"):
        agent_runner.run_agent("x", workdir=tmp_path)


def test_build_command_adds_allowed_tools():
    cmd = build_command("claude.exe", model="m", mcp_config=None, allowed_tools=["mcp__citeguard__search_papers", "Skill"])
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__citeguard__search_papers,Skill"
    assert "--allowedTools" not in build_command("claude.exe", model="m", mcp_config=None)


def test_install_skill_copies_into_project_skills_dir(tmp_path: Path):
    skill = tmp_path / "src" / "citeguard"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: citeguard\n---\n", encoding="utf-8")
    workdir = tmp_path / "work"
    workdir.mkdir()

    agent_runner.install_skill(skill, workdir)

    assert (workdir / ".claude" / "skills" / "citeguard" / "SKILL.md").read_text(encoding="utf-8").startswith("---")


def test_write_citeguard_mcp_config(tmp_path: Path):
    path = agent_runner.write_citeguard_mcp_config(tmp_path / "mcp.json", cache_dir=tmp_path / "cache")
    server = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["citeguard"]
    assert server["command"].endswith("citeguard-mcp")
    assert server["env"] == {"CITEGUARD_CACHE_DIR": str(tmp_path / "cache")}


def test_run_agent_with_skill_and_tools(monkeypatch, tmp_path: Path):
    completed = subprocess.CompletedProcess([], 0, stdout='{"result": "ok"}', stderr="")
    calls = _patch_runtime(monkeypatch, tmp_path, completed)
    skill = tmp_path / "skill" / "citeguard"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("x", encoding="utf-8")
    workdir = tmp_path / "w"
    workdir.mkdir()

    agent_runner.run_agent("p", workdir=workdir, allowed_tools=["Skill"], skill_dir=skill)

    assert "--allowedTools" in calls["cmd"]
    assert (workdir / ".claude" / "skills" / "citeguard" / "SKILL.md").exists()


def test_build_command_stream_json_needs_verbose():
    cmd = build_command("claude.exe", model="m", mcp_config=None, stream=True)
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in cmd


def test_parse_stream_output_returns_result_with_transcript():
    lines = [
        '{"type": "system", "subtype": "init"}',
        '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__citeguard__search_papers"}]}}',
        "",
        '{"type": "result", "result": "终稿", "num_turns": 3}',
    ]
    parsed = agent_runner.parse_stream_output("\n".join(lines))
    assert parsed["result"] == "终稿" and parsed["num_turns"] == 3
    assert len(parsed["transcript"]) == 3
    assert agent_runner.tool_calls(parsed) == ["mcp__citeguard__search_papers"]


def test_parse_stream_output_without_result_raises():
    with pytest.raises(RuntimeError, match="result"):
        agent_runner.parse_stream_output('{"type": "assistant"}')


def test_parse_stream_output_drops_thinking_progress_events():
    lines = ['{"type": "system", "subtype": "thinking_tokens", "message": "..."}',
             '{"type": "system", "subtype": "init"}',
             '{"type": "result", "result": "ok"}']
    parsed = agent_runner.parse_stream_output("\n".join(lines))
    assert [e.get("subtype") for e in parsed["transcript"]] == ["init", None]
