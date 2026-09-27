"""HTTP server: routing, authentication, rate limiting, audit and the web UI.

The server is built entirely on :mod:`http.server` so that a ToolGate
deployment has no required runtime dependency beyond ``cryptography``.
Run it with ``toolgate serve`` or attach :class:`GatewayServer` directly.
"""
from __future__ import annotations

import json
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

from . import __version__
from .crypto import Cipher, generate_token, hash_token
from .errors import (
    AuthError, ConflictError, NotFoundError, PermissionError, RateLimitError,
    ToolGateError, UpstreamError, ValidationError,
)
from .models import (
    Binding, CliConfig, EndpointConfig, EnvBinding, GatewayToken, NamedArg,
    ArgSchema, Tool, utcnow,
)
from .ratelimit import RateLimiter
from .registry import Registry
from .storage import Storage
from .proxy import call_endpoint
from .runner import run_cli


# ------------------------------------------------------------- tool parsing
def parse_tool(data: dict) -> Tool:
    """Build a :class:`Tool` from an admin API JSON payload."""
    if not isinstance(data, dict):
        raise ValidationError("Tool definition must be a JSON object")
    name = data.get("name")
    kind = data.get("kind")
    if kind not in {"endpoint", "cli"}:
        raise ValidationError("Field 'kind' must be 'endpoint' or 'cli'")
    common = dict(
        name=name,
        kind=kind,
        description=data.get("description", ""),
        tags=data.get("tags", []),
        enabled=bool(data.get("enabled", True)),
    )
    if kind == "endpoint":
        ep = data.get("endpoint") or {}
        endpoint = EndpointConfig(
            base_url=ep.get("base_url", ""),
            bindings=[Binding(**b) for b in ep.get("bindings", [])],
            forward_query=ep.get("forward_query", True),
        )
        return Tool(endpoint=endpoint, **common)
    cli_data = data.get("cli") or {}
    schema = cli_data.get("arg_schema", {})
    cli = CliConfig(
        argv=cli_data.get("argv", []),
        env=[EnvBinding(**e) for e in cli_data.get("env", [])],
        arg_schema=ArgSchema(
            named=[NamedArg(**n) for n in schema.get("named", [])],
            free_args=schema.get("free_args", False),
            free_args_flag=schema.get("free_args_flag", ""),
        ),
    )
    return Tool(cli=cli, **common)


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, config, storage: Storage,
                 cipher: Cipher, registry: Registry):
        super().__init__(address, handler)
        self.config = config
        self.storage = storage
        self.cipher = cipher
        self.registry = registry
        self.limiter = RateLimiter()

    def base_url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        shown_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
        return f"http://{shown_host}:{port}"


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = f"ToolGate/{__version__}"
    protocol_version = "HTTP/1.1"

    # silence the noisy default stderr logging; audit trail replaces it
    def log_message(self, fmt, *args):  # noqa: D401
        return

    # ------------------------------------------------------------- helpers
    @property
    def gw(self) -> GatewayServer:
        return self.server  # type: ignore[return-value]

    def _send_json(self, payload, status: int = 200, extra_headers: dict | None = None) -> int:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)
        return status

    def _send_bytes(self, body: bytes, status: int = 200, content_type: str = "application/octet-stream",
                    extra_headers: dict | None = None) -> int:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        return status

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _read_json(self) -> dict:
        raw = self._read_body()
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValidationError("Request body must be valid JSON") from exc
        if not isinstance(data, dict):
            raise ValidationError("Request body must be a JSON object")
        return data

    def _authenticate(self) -> GatewayToken:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise AuthError("Missing bearer token: use 'Authorization: Bearer <gateway token>'")
        token = header[len("Bearer "):].strip()
        record = self.gw.storage.get_token_by_hash(hash_token(token))
        if record is None:
            raise AuthError("Invalid token")
        if not record.enabled:
            raise AuthError("Token has been revoked")
        self.gw.storage.touch_token(record.token_hash, utcnow())
        return record

    def _require_admin(self, record: GatewayToken) -> None:
        if record.scope != "admin":
            raise PermissionError("This endpoint requires an admin-scoped token")

    def _apply_rate_limit(self, record: GatewayToken) -> None:
        per_minute = record.rate_limit or self.gw.config.rate_limit_per_minute
        allowed, retry_after = self.gw.limiter.check(f"token:{record.id}", per_minute)
        if not allowed:
            raise RateLimitError(
                f"Rate limit exceeded ({per_minute} requests/minute); retry later"
            )

    # ------------------------------------------------------------- dispatch
    def _split(self):
        parts = urlsplit(self.path)
        return parts.path, parts.query

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_PATCH(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    def do_HEAD(self):
        self._handle()

    def _handle(self) -> None:
        path, query = self._split()
        start = time.monotonic()
        record: GatewayToken | None = None
        status = 500
        tool_name = self._audit_tool_name(path)
        try:
            # ---- public endpoints (no auth) ----
            if path == "/healthz":
                status = self._send_json({"status": "ok", "version": __version__})
                return
            if path == "/" or path == "/ui" or path == "/ui/" or path.startswith("/ui/"):
                status = self._serve_ui(path)
                return

            # ---- everything under /v1 requires authentication ----
            if path.startswith("/v1/"):
                record = self._authenticate()
                self._apply_rate_limit(record)
                status = self._route_api(path, query, record)
                return
            status = self._send_json({"error": "not_found", "message": f"No route for {path}"}, 404)
        except ToolGateError as exc:
            status = exc.http_status
            headers = {}
            if isinstance(exc, RateLimitError):
                headers["Retry-After"] = "5"
            self._send_json(exc.to_dict(), exc.http_status, headers)
        except Exception as exc:  # pragma: no cover - last-resort guard
            status = 500
            self._send_json({"error": "internal_error", "message": f"Unexpected error: {exc}"}, 500)
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            if path.startswith("/v1/") or path == "/healthz":
                self.gw.storage.record_audit({
                    "ts": utcnow(),
                    "token_name": record.name if record else None,
                    "tool": tool_name,
                    "op": f"{self.command} {path}",
                    "target": path,
                    "status": status,
                    "duration_ms": duration_ms,
                    "ip": self.client_address[0] if self.client_address else None,
                })

    @staticmethod
    def _audit_tool_name(path: str) -> str | None:
        for prefix in ("/v1/call/", "/v1/tool/"):
            if path.startswith(prefix):
                rest = path[len(prefix):]
                return rest.split("/")[0] or None
        if "/v1/admin/tools/" in path:
            rest = path.split("/v1/admin/tools/", 1)[1]
            return rest.split("/")[0] or None
        return None

    # ----------------------------------------------------------------- UI
    def _serve_ui(self, path: str) -> int:
        if path in ("/",):
            self.send_response(302)
            self.send_header("Location", "/ui/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return 302
        index = self.gw.config.web_dir / "index.html"
        try:
            body = index.read_bytes()
        except OSError:
            return self._send_json({"error": "not_found", "message": "Web UI assets missing"}, 404)
        return self._send_bytes(body, 200, "text/html; charset=utf-8")

    # ------------------------------------------------------------ API routes
    def _route_api(self, path: str, query: str, record: GatewayToken) -> int:
        # ---- catalog & search (call scope) ----
        if path == "/v1/tools" and self.command == "GET":
            kind = parse_qs(query).get("kind", [None])[0]
            tools = self.gw.registry.list_tools(kind=kind, include_disabled=False)
            return self._send_json({"tools": [t.public_dict() for t in tools], "count": len(tools)})
        if path.startswith("/v1/tools/") and self.command == "GET":
            name = path[len("/v1/tools/"):]
            return self._send_json(self.gw.registry.get_tool(name).public_dict())
        if path == "/v1/search" and self.command == "GET":
            params = parse_qs(query)
            q = params.get("q", [""])[0]
            kind = params.get("kind", [None])[0]
            limit = int(params.get("limit", ["10"])[0])
            hits = self.gw.registry.search(q, kind=kind, limit=limit)
            return self._send_json({"query": q, "hits": [h.public_dict() for h in hits], "count": len(hits)})

        # ---- unified call ----
        if path.startswith("/v1/call/") and self.command == "POST":
            name = path[len("/v1/call/"):]
            return self._unified_call(name)

        # ---- transparent proxy for endpoint tools ----
        if path.startswith("/v1/tool/"):
            return self._proxy_call(path)

        # ---- admin area ----
        if path.startswith("/v1/admin/"):
            self._require_admin(record)
            return self._route_admin(path, query)

        raise NotFoundError(f"No API route for {path}")

    def _unified_call(self, name: str) -> int:
        tool = self.gw.registry.get_tool(name)
        if not tool.enabled:
            raise PermissionError(f"Tool '{name}' is disabled")
        data = self._read_json()
        if tool.kind == "cli":
            result = run_cli(
                tool,
                params=data.get("params", {}),
                free_args=data.get("args", []),
                stdin=data.get("stdin"),
                env_secrets=self.gw.registry.cli_env(tool),
                timeout=self.gw.config.cli_timeout,
                output_cap=self.gw.config.cli_output_cap,
            )
            return self._send_json(result.public_dict(), 200)

        # endpoint via JSON envelope
        method = data.get("method", "POST")
        subpath = (data.get("path") or "").lstrip("/")
        upstream_query = data.get("query", "")
        headers = data.get("headers", {}) or {}
        req_body = data.get("body", b"")
        if isinstance(req_body, dict):
            req_body = json.dumps(req_body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(req_body, str):
            req_body = req_body.encode("utf-8")
        else:
            req_body = req_body if isinstance(req_body, bytes) else b""
        resolved = self.gw.registry.endpoint_bindings(tool)
        response = call_endpoint(
            tool, method, subpath, upstream_query, headers, req_body, resolved,
            self.gw.config.upstream_timeout,
        )
        content_type = response.header_dict().get("Content-Type", "application/octet-stream")
        text_body = response.body.decode("utf-8", errors="replace")
        return self._send_json({
            "tool": tool.name,
            "status": response.status,
            "headers": response.header_dict(),
            "content_type": content_type,
            "body": text_body,
        }, 200)

    def _proxy_call(self, path: str) -> int:
        rest = path[len("/v1/tool/"):]
        name, _, subpath = rest.partition("/")
        tool = self.gw.registry.get_tool(name)
        if tool.kind != "endpoint":
            raise ValidationError(f"Tool '{name}' is a CLI tool; call it via /v1/call/{name}")
        if not tool.enabled:
            raise PermissionError(f"Tool '{name}' is disabled")
        body = self._read_body()
        _, query = self._split()
        resolved = self.gw.registry.endpoint_bindings(tool)
        response = call_endpoint(
            tool, self.command, subpath, query, dict(self.headers), body, resolved,
            self.gw.config.upstream_timeout,
        )
        content_type = response.header_dict().get("Content-Type", "application/octet-stream")
        return self._send_bytes(response.body, response.status, content_type, response.header_dict())

    # ------------------------------------------------------------- admin
    def _route_admin(self, path: str, query: str) -> int:
        # stats
        if path == "/v1/admin/stats" and self.command == "GET":
            return self._send_json({"counts": self.gw.storage.counts(), "version": __version__})

        # credentials
        if path == "/v1/admin/credentials" and self.command == "GET":
            creds = self.gw.registry.list_credentials()
            return self._send_json({
                "credentials": [
                    {"name": c.name, "description": c.description,
                     "created_at": c.created_at, "updated_at": c.updated_at}
                    for c in creds
                ],
                "count": len(creds),
            })
        if path == "/v1/admin/credentials" and self.command == "POST":
            data = self._read_json()
            if not data.get("name") or "secret" not in data:
                raise ValidationError("Fields 'name' and 'secret' are required")
            cred = self.gw.registry.add_credential(
                data["name"], data["secret"], data.get("description", ""), create_only=True
            )
            return self._send_json({"name": cred.name, "description": cred.description}, 201)
        if path.startswith("/v1/admin/credentials/") and self.command == "DELETE":
            name = path[len("/v1/admin/credentials/"):]
            self.gw.registry.delete_credential(name)
            return self._send_json({"deleted": name})

        # tools
        if path == "/v1/admin/tools" and self.command == "POST":
            tool = parse_tool(self._read_json())
            self.gw.registry.add_tool(tool)
            return self._send_json(tool.public_dict(), 201)
        if path.startswith("/v1/admin/tools/"):
            rest = path[len("/v1/admin/tools/"):]
            name, _, sub = rest.partition("/")
            if sub == "enabled" and self.command == "POST":
                enabled = self._read_json().get("enabled", True)
                self.gw.registry.set_tool_enabled(name, enabled)
                return self._send_json({"name": name, "enabled": enabled})
            if not sub and self.command == "PUT":
                data = self._read_json()
                data["name"] = name
                self.gw.registry.update_tool(parse_tool(data))
                return self._send_json(self.gw.registry.get_tool(name).public_dict())
            if not sub and self.command == "DELETE":
                self.gw.registry.delete_tool(name)
                return self._send_json({"deleted": name})

        # tokens
        if path == "/v1/admin/tokens" and self.command == "GET":
            tokens = self.gw.storage.list_tokens()
            return self._send_json({"tokens": [t.public_dict() for t in tokens], "count": len(tokens)})
        if path == "/v1/admin/tokens" and self.command == "POST":
            return self._create_token()
        if path.startswith("/v1/admin/tokens/") and self.command == "DELETE":
            name = path[len("/v1/admin/tokens/"):]
            self.gw.storage.delete_token(name)
            return self._send_json({"revoked": name})

        # audit
        if path == "/v1/admin/audit" and self.command == "GET":
            params = parse_qs(query)
            limit = int(params.get("limit", ["100"])[0])
            tool = params.get("tool", [None])[0]
            events = self.gw.storage.list_audit(limit=limit, tool=tool)
            return self._send_json({"events": events, "count": len(events)})

        raise NotFoundError(f"No admin route for {path}")

    def _create_token(self) -> int:
        data = self._read_json()
        name = data.get("name")
        scope = data.get("scope", "call")
        if not name:
            raise ValidationError("Field 'name' is required")
        if scope not in {"call", "admin"}:
            raise ValidationError("Scope must be 'call' or 'admin'")
        plaintext = generate_token()
        token = GatewayToken(
            name=name,
            scope=scope,
            token_hash=hash_token(plaintext),
            prefix=plaintext[:8],
            rate_limit=int(data.get("rate_limit", 0)),
        )
        try:
            self.gw.storage.create_token(token)
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"A token named '{name}' already exists") from exc
        return self._send_json(
            {"name": name, "scope": scope, "token": plaintext,
             "warning": "Store this token now; it is shown only once."},
            201,
        )


def build_server(config) -> GatewayServer:
    """Wire together config, storage, crypto, registry and the HTTP server."""
    config.ensure_dirs()
    from .crypto import load_or_create_master_key
    master_key = load_or_create_master_key(config.master_key_path)
    cipher = Cipher(master_key)
    storage = Storage(config.db_path)
    registry = Registry(storage, cipher)
    return GatewayServer((config.host, config.port), GatewayHandler, config, storage, cipher, registry)
