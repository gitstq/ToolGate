"""Safe execution of command-line tools.

A CLI tool is executed with ``shell=False`` and an argv list, so caller input
can never be interpreted by a shell.  Named arguments must be whitelisted in
the tool's :class:`~toolgate.models.ArgSchema`; free positional arguments are
only allowed when explicitly enabled.  Credentials are injected through
environment variables rather than argv where possible.
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass

from .errors import ToolExecutionError, ValidationError


@dataclass
class CliResult:
    tool: str
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool = False

    def ok(self) -> bool:
        return self.exit_code == 0

    def public_dict(self) -> dict:
        return {
            "tool": self.tool,
            "argv": self.argv,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "truncated": self.truncated,
        }


def build_argv(tool, params: dict, free_args: list[str]) -> list[str]:
    """Assemble the final argv from the whitelisted schema."""
    schema = tool.cli.arg_schema
    allowed = {arg.name: arg for arg in schema.named}
    unknown = sorted(set(params) - set(allowed))
    if unknown:
        raise ValidationError(
            "Tool '" + tool.name + "' does not accept argument(s): " + ", ".join(unknown)
        )

    argv = list(tool.cli.argv)
    for name, arg in allowed.items():
        if name not in params or params[name] is None:
            continue
        value = params[name]
        if arg.repeatable:
            items = value if isinstance(value, list) else [value]
            for item in items:
                argv.extend([arg.flag, str(item)])
        else:
            if isinstance(value, list):
                raise ValidationError(f"Argument '{name}' is not repeatable; pass a single value")
            argv.extend([arg.flag, str(value)])

    if free_args:
        if not schema.free_args:
            raise ValidationError("Tool '" + tool.name + "' does not accept free arguments")
        if schema.free_args_flag:
            argv.append(schema.free_args_flag)
        argv.extend(str(a) for a in free_args)
    return argv


def run_cli(
    tool,
    params: dict | None = None,
    free_args: list[str] | None = None,
    stdin: str | None = None,
    env_secrets: dict[str, str] | None = None,
    timeout: float = 60.0,
    output_cap: int = 1_048_576,
) -> CliResult:
    argv = build_argv(tool, params or {}, free_args or [])
    env = os.environ.copy()
    if env_secrets:
        env.update(env_secrets)

    start = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            input=(stdin.encode("utf-8") if stdin is not None else None),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolExecutionError(
            f"Tool '{tool.name}' timed out after {timeout}s and was terminated"
        ) from exc
    except FileNotFoundError as exc:
        raise ToolExecutionError(
            f"Executable not found for tool '{tool.name}': {argv[0]}"
        ) from exc
    except OSError as exc:  # pragma: no cover - defensive
        raise ToolExecutionError(f"Failed to launch tool '{tool.name}': {exc}") from exc
    duration_ms = int((time.monotonic() - start) * 1000)

    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    truncated = len(stdout) > output_cap or len(stderr) > output_cap
    return CliResult(
        tool=tool.name,
        argv=argv,
        exit_code=completed.returncode,
        stdout=stdout[:output_cap],
        stderr=stderr[:output_cap],
        duration_ms=duration_ms,
        truncated=truncated,
    )
