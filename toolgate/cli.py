"""Command-line interface for ToolGate.

Provides server control plus local management of tools, credentials, tokens
and the audit log.  Every command prints JSON or plain text and exits with a
non-zero status on failure so it can be used in scripts.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys

from . import __version__
from .config import ToolGateConfig
from .crypto import Cipher, generate_master_key, generate_token, hash_token, load_or_create_master_key
from .errors import ToolGateError
from .models import (
    ArgSchema, Binding, CliConfig, EndpointConfig, EnvBinding, GatewayToken,
    NamedArg, Tool,
)
from .proxy import call_endpoint
from .registry import Registry
from .runner import run_cli
from .server import build_server
from .storage import Storage


# ------------------------------------------------------------- service wiring
def _services(home: str | None):
    config = ToolGateConfig.from_env(home)
    config.ensure_dirs()
    master_key = load_or_create_master_key(config.master_key_path)
    cipher = Cipher(master_key)
    storage = Storage(config.db_path)
    registry = Registry(storage, cipher)
    return config, storage, registry


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ------------------------------------------------------------- binding parsing
def _parse_kv(text: str) -> tuple[str, str]:
    if ":" not in text:
        raise SystemExit(f"Expected 'credential:value', got {text!r}")
    cred, _, value = text.partition(":")
    return cred.strip(), value.strip()


# ------------------------------------------------------------------- commands
def cmd_keygen(args) -> int:
    print(generate_master_key().decode("ascii"))
    return 0


def cmd_serve(args) -> int:
    config = ToolGateConfig.from_env(args.home, host=args.host, port=args.port)
    server = build_server(config)
    banner = (
        f"ToolGate v{__version__} serving on {config.host}:{config.port}\n"
        f"  Web UI      : {server.base_url()}/ui/\n"
        f"  Health      : {server.base_url()}/healthz\n"
        f"  Tools API   : {server.base_url()}/v1/tools\n"
        f"Create an admin token : toolgate tokens create my-admin --scope admin\n"
        f"Press Ctrl+C to stop."
    )
    print(banner)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down ...")
    finally:
        server.storage.close()
    return 0


def cmd_search(args) -> int:
    _, storage, registry = _services(args.home)
    try:
        hits = registry.search(args.query, kind=args.kind, limit=args.limit)
        _print({"query": args.query, "hits": [h.public_dict() for h in hits]})
    finally:
        storage.close()
    return 0


# ------------------------------------------------------------------ tools
def _build_endpoint_tool(args) -> Tool:
    bindings: list[Binding] = []
    for text in args.header_bind or []:
        cred, header = _parse_kv(text)
        bindings.append(Binding(cred, "header", header, "{value}"))
    for text in args.auth_bearer or []:
        cred = text.strip()
        bindings.append(Binding(cred, "header", "Authorization", "Bearer {value}"))
    for text in args.query_bind or []:
        cred, param = _parse_kv(text)
        bindings.append(Binding(cred, "query", param, "{value}"))
    for text in args.basic_bind or []:
        cred, username = _parse_kv(text)
        bindings.append(Binding(cred, "basic_auth", username, "{value}"))
    for raw in args.bind_json or []:
        bindings.append(Binding(**json.loads(raw)))
    endpoint = EndpointConfig(base_url=args.base_url, bindings=bindings,
                              forward_query=not args.no_forward_query)
    return Tool(name=args.name, kind="endpoint", description=args.description or "",
                tags=args.tags or [], endpoint=endpoint)


def _build_cli_tool(args) -> Tool:
    env = [EnvBinding(credential=cred, env=envvar)
           for cred, envvar in (_parse_kv(x) for x in (args.env_bind or []))]
    repeatable = set(args.repeatable or [])
    named = []
    for raw in args.named or []:
        if ":" not in raw:
            raise SystemExit(f"--named expects 'name:--flag', got {raw!r}")
        nm, _, flag = raw.partition(":")
        named.append(NamedArg(name=nm.strip(), flag=flag.strip(),
                              repeatable=nm.strip() in repeatable))
    schema = ArgSchema(named=named, free_args=bool(args.free_args),
                       free_args_flag=args.free_args_flag or "")
    argv = shlex.split(args.argv_string)
    cli = CliConfig(argv=argv, env=env, arg_schema=schema)
    return Tool(name=args.name, kind="cli", description=args.description or "",
                tags=args.tags or [], cli=cli)


def cmd_tools(args) -> int:
    _, storage, registry = _services(args.home)
    try:
        if args.tools_action == "ls":
            tools = registry.list_tools(kind=args.kind, include_disabled=True)
            _print({"tools": [t.public_dict() for t in tools], "count": len(tools)})
        elif args.tools_action == "show":
            _print(registry.get_tool(args.name).public_dict())
        elif args.tools_action == "rm":
            registry.delete_tool(args.name)
            _print({"deleted": args.name})
        elif args.tools_action in ("enable", "disable"):
            registry.set_tool_enabled(args.name, args.tools_action == "enable")
            _print({"name": args.name, "enabled": args.tools_action == "enable"})
        elif args.tools_action == "add-endpoint":
            tool = registry.add_tool(_build_endpoint_tool(args))
            _print(tool.public_dict())
        elif args.tools_action == "add-cli":
            tool = registry.add_tool(_build_cli_tool(args))
            _print(tool.public_dict())
    finally:
        storage.close()
    return 0


# ---------------------------------------------------------------- credentials
def cmd_creds(args) -> int:
    _, storage, registry = _services(args.home)
    try:
        if args.creds_action == "ls":
            creds = registry.list_credentials()
            _print({"credentials": [
                {"name": c.name, "description": c.description,
                 "created_at": c.created_at, "updated_at": c.updated_at}
                for c in creds]})
        elif args.creds_action == "set":
            secret = args.secret
            if secret is None or secret == "-":
                secret = sys.stdin.read().rstrip("\n")
            cred = registry.add_credential(args.name, secret, args.description or "")
            _print({"name": cred.name, "stored": True})
        elif args.creds_action == "rm":
            registry.delete_credential(args.name)
            _print({"deleted": args.name})
    finally:
        storage.close()
    return 0


# ------------------------------------------------------------------- tokens
def cmd_tokens(args) -> int:
    _, storage, registry = _services(args.home)
    try:
        if args.tokens_action == "ls":
            _print({"tokens": [t.public_dict() for t in storage.list_tokens()]})
        elif args.tokens_action == "create":
            plaintext = generate_token()
            token = GatewayToken(
                name=args.name, scope=args.scope, token_hash=hash_token(plaintext),
                prefix=plaintext[:8], rate_limit=args.rate_limit,
            )
            storage.create_token(token)
            _print({"name": args.name, "scope": args.scope, "token": plaintext,
                    "warning": "Store this now; it is shown only once."})
        elif args.tokens_action == "revoke":
            storage.delete_token(args.name)
            _print({"revoked": args.name})
    finally:
        storage.close()
    return 0


# --------------------------------------------------------------------- call
def cmd_call(args) -> int:
    config, storage, registry = _services(args.home)
    try:
        tool = registry.get_tool(args.name)
        if tool.kind == "cli":
            params = json.loads(args.params) if args.params else {}
            result = run_cli(
                tool, params=params, free_args=args.arguments or [],
                stdin=args.stdin, env_secrets=registry.cli_env(tool),
                timeout=config.cli_timeout, output_cap=config.cli_output_cap,
            )
            _print(result.public_dict())
            return 0 if result.ok() else 1
        resolved = registry.endpoint_bindings(tool)
        body = args.body.encode("utf-8") if args.body else b""
        headers = {}
        if body:
            headers["Content-Type"] = args.content_type
        response = call_endpoint(
            tool, args.method, args.path, args.query, headers, body, resolved,
            config.upstream_timeout,
        )
        _print({"status": response.status, "headers": response.header_dict(),
                "body": response.body.decode("utf-8", errors="replace")})
        return 0 if response.status < 400 else 1
    finally:
        storage.close()


def cmd_audit(args) -> int:
    _, storage, _ = _services(args.home)
    try:
        events = storage.list_audit(limit=args.limit, tool=args.tool)
        _print({"events": events, "count": len(events)})
    finally:
        storage.close()
    return 0


def cmd_stats(args) -> int:
    _, storage, _ = _services(args.home)
    try:
        _print({"version": __version__, "counts": storage.counts()})
    finally:
        storage.close()
    return 0


# ------------------------------------------------------------------ argparse
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolgate",
        description="ToolGate — one gateway, every tool for your AI agents.",
    )
    parser.add_argument("--version", action="version", version=f"ToolGate {__version__}")
    parser.add_argument("--home", help="state directory (default: TOOLGATE_HOME or ~/.toolgate)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen", help="print a fresh master key").set_defaults(func=cmd_keygen)

    p_serve = sub.add_parser("serve", help="start the HTTP gateway")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8848)
    p_serve.set_defaults(func=cmd_serve)

    p_search = sub.add_parser("search", help="search the tool catalog")
    p_search.add_argument("query")
    p_search.add_argument("--kind", choices=["endpoint", "cli"])
    p_search.add_argument("--limit", type=int, default=10)
    p_search.set_defaults(func=cmd_search)

    # tools
    p_tools = sub.add_parser("tools", help="manage tools")
    t_sub = p_tools.add_subparsers(dest="tools_action", required=True)

    t_ls = t_sub.add_parser("ls")
    t_ls.add_argument("--kind", choices=["endpoint", "cli"])

    t_show = t_sub.add_parser("show"); t_show.add_argument("name")
    t_rm = t_sub.add_parser("rm"); t_rm.add_argument("name")
    t_en = t_sub.add_parser("enable"); t_en.add_argument("name")
    t_dis = t_sub.add_parser("disable"); t_dis.add_argument("name")

    t_ep = t_sub.add_parser("add-endpoint")
    t_ep.add_argument("name")
    t_ep.add_argument("--base-url", required=True)
    t_ep.add_argument("--description")
    t_ep.add_argument("--tags", nargs="*")
    t_ep.add_argument("--header-bind", action="append", metavar="CRED:HEADER")
    t_ep.add_argument("--auth-bearer", action="append", metavar="CRED")
    t_ep.add_argument("--query-bind", action="append", metavar="CRED:PARAM")
    t_ep.add_argument("--basic-bind", action="append", metavar="CRED:USERNAME")
    t_ep.add_argument("--bind-json", action="append", metavar="JSON")
    t_ep.add_argument("--no-forward-query", action="store_true")

    t_cli = t_sub.add_parser("add-cli")
    t_cli.add_argument("name")
    t_cli.add_argument("--argv", dest="argv_string", required=True,
                       help="full command, quoted (e.g. \"mytool --verbose\")")
    t_cli.add_argument("--description")
    t_cli.add_argument("--tags", nargs="*")
    t_cli.add_argument("--env-bind", action="append", metavar="CRED:ENV_VAR")
    t_cli.add_argument("--named", action="append", metavar="NAME:--FLAG")
    t_cli.add_argument("--repeatable", action="append", metavar="NAME")
    t_cli.add_argument("--free-args", action="store_true")
    t_cli.add_argument("--free-args-flag")
    p_tools.set_defaults(func=cmd_tools)

    # credentials
    p_creds = sub.add_parser("creds", help="manage encrypted credentials")
    c_sub = p_creds.add_subparsers(dest="creds_action", required=True)
    c_sub.add_parser("ls")
    c_set = c_sub.add_parser("set")
    c_set.add_argument("name")
    c_set.add_argument("secret", nargs="?", default=None,
                       help="secret value, or '-' to read from stdin")
    c_set.add_argument("--description")
    c_rm = c_sub.add_parser("rm"); c_rm.add_argument("name")
    p_creds.set_defaults(func=cmd_creds)

    # tokens
    p_tokens = sub.add_parser("tokens", help="manage gateway tokens")
    g_sub = p_tokens.add_subparsers(dest="tokens_action", required=True)
    g_sub.add_parser("ls")
    g_create = g_sub.add_parser("create")
    g_create.add_argument("name")
    g_create.add_argument("--scope", choices=["call", "admin"], default="call")
    g_create.add_argument("--rate-limit", type=int, default=0)
    g_rev = g_sub.add_parser("revoke"); g_rev.add_argument("name")
    p_tokens.set_defaults(func=cmd_tokens)

    # call
    p_call = sub.add_parser("call", help="invoke a tool locally (no HTTP server needed)")
    p_call.add_argument("name")
    p_call.add_argument("--params", help="CLI tool: JSON object of named params")
    p_call.add_argument("--arguments", nargs="*", help="CLI tool: free arguments")
    p_call.add_argument("--stdin", help="CLI tool: stdin text")
    p_call.add_argument("--method", default="GET", help="endpoint: HTTP method")
    p_call.add_argument("--path", default="", help="endpoint: sub path")
    p_call.add_argument("--query", default="", help="endpoint: raw query string")
    p_call.add_argument("--body", help="endpoint: request body text")
    p_call.add_argument("--content-type", default="application/json")
    p_call.set_defaults(func=cmd_call)

    # audit & stats
    p_audit = sub.add_parser("audit", help="show the audit trail")
    p_audit.add_argument("--limit", type=int, default=50)
    p_audit.add_argument("--tool")
    p_audit.set_defaults(func=cmd_audit)
    sub.add_parser("stats", help="show instance statistics").set_defaults(func=cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ToolGateError as exc:
        _print(exc.to_dict())
        return 1
    except BrokenPipeError:  # pragma: no cover
        return 1


if __name__ == "__main__":
    sys.exit(main())
