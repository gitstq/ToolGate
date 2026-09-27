"""Shared test helpers."""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from toolgate.config import ToolGateConfig
from toolgate.server import build_server


def make_config(**overrides):
    tmp = Path(tempfile.mkdtemp(prefix="toolgate-test-"))
    kw = dict(host="127.0.0.1", port=0, rate_limit_per_minute=10000,
              cli_timeout=10, upstream_timeout=10)
    kw.update(overrides)
    return ToolGateConfig.from_env(tmp, **kw)


def start_server(config):
    server = build_server(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    return server, base
