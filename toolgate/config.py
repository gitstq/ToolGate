"""Runtime configuration and filesystem layout.

ToolGate keeps all of its state under a single *home* directory so that a
self-hosted deployment is trivial to back up or move.  The location is
resolved, in order of precedence:

1. the ``--home`` CLI flag / ``ToolGateConfig(home=...)`` argument
2. the ``TOOLGATE_HOME`` environment variable
3. ``~/.toolgate``

A small ``.env`` file inside the home directory (or the current working
directory) is parsed on startup; real environment variables always win over
values from that file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError

#: files / directories created inside the home directory
DB_FILENAME = "toolgate.sqlite3"
MASTERKEY_FILENAME = "master.key"
ENV_FILENAME = ".env"
WEB_DIRNAME = "web"


def _default_home() -> Path:
    env = os.environ.get("TOOLGATE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".toolgate"


def load_dotenv(path: Path) -> None:
    """Parse a very small subset of ``.env`` syntax into ``os.environ``.

    Existing environment variables are never overridden.  Supported lines::

        KEY=value
        KEY="quoted value"
        # comment
    """
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Unable to read {path}: {exc}") from exc


@dataclass
class ToolGateConfig:
    """Resolved configuration for a ToolGate instance."""

    home: Path = field(default_factory=_default_home)
    host: str = "127.0.0.1"
    port: int = 8848
    #: default per-token rate limit (requests / minute); 0 disables limiting
    rate_limit_per_minute: int = 600
    #: max seconds an upstream HTTP call may take
    upstream_timeout: float = 60.0
    #: max seconds a CLI tool may run before it is killed
    cli_timeout: float = 60.0
    #: max bytes captured from a CLI tool's stdout/stderr
    cli_output_cap: int = 1_048_576

    # -- derived paths ----------------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.home / DB_FILENAME

    @property
    def master_key_path(self) -> Path:
        return self.home / MASTERKEY_FILENAME

    @property
    def web_dir(self) -> Path:
        # bundled web assets live next to this package
        return Path(__file__).resolve().parent / WEB_DIRNAME

    # -- factories --------------------------------------------------------
    @classmethod
    def from_env(cls, home: str | os.PathLike | None = None, **overrides) -> "ToolGateConfig":
        home_path = Path(home).expanduser() if home else _default_home()
        # load .env from cwd first, then from the home directory
        load_dotenv(Path.cwd() / ENV_FILENAME)
        load_dotenv(home_path / ENV_FILENAME)

        values: dict = {
            "host": os.environ.get("TOOLGATE_HOST", "127.0.0.1"),
            "port": int(os.environ.get("TOOLGATE_PORT", "8848")),
            "rate_limit_per_minute": int(os.environ.get("TOOLGATE_RATE_LIMIT", "600")),
            "upstream_timeout": float(os.environ.get("TOOLGATE_UPSTREAM_TIMEOUT", "60")),
            "cli_timeout": float(os.environ.get("TOOLGATE_CLI_TIMEOUT", "60")),
            "cli_output_cap": int(os.environ.get("TOOLGATE_CLI_OUTPUT_CAP", str(1_048_576))),
        }
        values.update(overrides)
        return cls(home=home_path, **values)

    def ensure_dirs(self) -> None:
        """Create the home directory with safe permissions if needed."""
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.home, 0o700)
            except OSError:  # pragma: no cover - non-POSIX filesystems
                pass
        except OSError as exc:
            raise ConfigError(f"Unable to create home directory {self.home}: {exc}") from exc
