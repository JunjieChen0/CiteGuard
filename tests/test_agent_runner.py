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
