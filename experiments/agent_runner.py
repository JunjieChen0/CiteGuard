"""以无头模式运行一个与本机 Claude Code 配置隔离、后端为 DeepSeek 的 Agent。

用法：
    uv run python -m experiments.agent_runner "写一段 ResNet 简介，附 3 条参考文献"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

DEEPSEEK_BASE_URL = "https://api.deepseek.com/anthropic"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_TIMEOUT_SECONDS = 600

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_CONFIG_DIR = PROJECT_ROOT / ".claude-runtime"
DOTENV_PATH = PROJECT_ROOT / ".env"

# 从父进程继承、可能把子进程连回 Anthropic 或带入本机配置的变量
_INHERITED_PREFIXES = ("ANTHROPIC_", "CLAUDE_CODE_", "CLAUDE_CONFIG_DIR")
_INHERITED_NAMES = {"CLAUDECODE"}


def load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_api_key(environ: Mapping[str, str], dotenv: Mapping[str, str]) -> str:
    key = environ.get("DEEPSEEK_API_KEY") or dotenv.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY：请在系统环境变量或项目根目录 .env 中设置")
    return key


def build_env(base: Mapping[str, str], api_key: str, model: str, config_dir: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in base.items()
        if not k.startswith(_INHERITED_PREFIXES) and k not in _INHERITED_NAMES
    }
    env.update(
        {
            "ANTHROPIC_BASE_URL": DEEPSEEK_BASE_URL,
            "ANTHROPIC_AUTH_TOKEN": api_key,
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
            "CLAUDE_CODE_SUBAGENT_MODEL": model,
            "CLAUDE_CONFIG_DIR": str(config_dir),
        }
    )
    return env


def build_command(claude_exe: str, model: str, mcp_config: Path | None) -> list[str]:
    cmd = [
        claude_exe,
        "-p",
        "--output-format", "json",
        "--model", model,
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]
    if mcp_config is not None:
        cmd += ["--mcp-config", str(mcp_config)]
    return cmd


def run_agent(
    prompt: str,
    workdir: Path,
    mcp_config: Path | None = None,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    claude_exe = shutil.which("claude")
    if claude_exe is None:
        raise RuntimeError("找不到 claude 命令，请先安装 Claude Code")
    api_key = resolve_api_key(os.environ, load_dotenv(DOTENV_PATH))
    RUNTIME_CONFIG_DIR.mkdir(exist_ok=True)

    proc = subprocess.run(
        build_command(claude_exe, model, mcp_config),
        input=prompt,
        cwd=workdir,
        env=build_env(os.environ, api_key, model, RUNTIME_CONFIG_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude 退出码 {proc.returncode}：{(proc.stderr or proc.stdout)[-2000:]}")
    return json.loads(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="用 DeepSeek 后端运行一次隔离的 Claude Code")
    parser.add_argument("prompt")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="citeguard-run-") as workdir:
        result = run_agent(args.prompt, Path(workdir), model=args.model)

    sys.stdout.reconfigure(encoding="utf-8")
    print(result.get("result", ""))
    print("\n---")
    print(f"is_error={result.get('is_error')}  duration_ms={result.get('duration_ms')}  "
          f"cost_usd={result.get('total_cost_usd')}  usage={result.get('usage')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
