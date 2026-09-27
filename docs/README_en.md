<div align="center">

# 🚪 ToolGate

### One Gateway, Every Tool

**The self-hosted tool gateway for AI agents — one base URL, one gateway token, and secure access to every HTTP API and command-line tool your team owns.**

🌐 Language：
[简体中文](../README.md) · [繁體中文](README_zh-TW.md) · [English](README_en.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-teal.svg)](../LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Release](https://img.shields.io/badge/release-v1.0.0-brightgreen.svg)](https://github.com/gitstq/ToolGate/releases)
[![Downloads](https://img.shields.io/github/downloads/gitstq/ToolGate/total.svg)](https://github.com/gitstq/ToolGate/releases)

⬇️ **[Download the latest release (wheel / sdist / Linux binary)](https://github.com/gitstq/ToolGate/releases)**

</div>

---

## 🎉 Introduction

For an AI agent to do real work, it needs to call external tools: check the weather, read GitHub, send email, pull data, run internal scripts. In practice this is painful:

- 🔑 **Credentials are scattered** — every new agent gets another copy of each API key, multiplying the leak surface;
- 🧩 **Tool protocols differ wildly** — some want a header, some a query parameter, others only ship a CLI, so integration is expensive;
- 🧾 **There is no unified audit trail** — nobody can tell who called which tool and when.

**ToolGate puts every tool behind a single gateway.** The agent only needs one base URL and one gateway token. Real credentials are stored encrypted on the server and injected at the moment a request goes out — **they are never handed to the agent**.

> 🦞 **What makes ToolGate different**
> - 🔒 **No plaintext credentials** — authenticated Fernet encryption (AES-128-CBC + HMAC-SHA256), with the master key injectable via environment variable;
> - 🔌 **Two tool kinds, one gateway** — HTTP tools go through a **transparent reverse proxy** (method / body / query / response forwarded untouched); command-line tools are **safely exposed over HTTP**;
> - 🛡️ **Zero command injection** — `shell=False`, an argument whitelist, and credentials delivered through environment variables;
> - 🎫 **Token governance** — only token hashes are stored; tokens are named, revocable and individually rate-limited;
> - 🔍 **Built-in TF-IDF tool search** (including CJK tokenization) so agents describe the task instead of memorizing tool names;
> - 🖥️ **Three ways to use it** — a dependency-free web console, a cross-platform CLI, and an embeddable Python library;
> - 🪶 **Tiny footprint** — the only runtime dependency is `cryptography`; everything else is the Python standard library.

💡 **Inspiration**: ToolGate is inspired by the recently trending "OpenRouter for tools" idea, but it is **100% independently developed**, focused on being **fully self-hosted, local-first, cloud-free and telemetry-free**. It ships no third-party catalog data, and all code and data structures are original.

---

## ✨ Features

- 🔐 **Server-side credential injection** — three HTTP injection points (`Header`, `Query`, `HTTP Basic Auth`), environment-variable injection for CLIs, and custom templates such as `Bearer {value}`.
- 🌐 **Transparent reverse proxy** — the gateway **relays, it does not model**: method, path, query string, body and almost all headers reach the upstream untouched, and the upstream status and body come back verbatim.
- ⌨️ **CLIs over HTTP** — register any command-line tool as an HTTP endpoint with built-in timeouts, output truncation and exit-code reporting.
- 🛡️ **Defense in depth** — encrypted storage, hashed tokens, argument whitelisting, shell-free execution, per-token token-bucket rate limiting and a full audit log.
- 🔍 **Catalog search** — dependency-free TF-IDF with English tokenization and per-ideograph CJK support; name matches are boosted.
- 🖥️ **Bundled web console** — browse, search, call tools and inspect the audit trail in a single build-free HTML file.
- 📦 **Batteries included** — `pip` install, Docker / docker-compose, a one-command smoke script and a full test suite.
- 🌍 **Cross-platform** — Windows, macOS and Linux on Python 3.9+.

---

## 🚀 Quick Start

### 📋 Requirements

| Requirement | Version |
| --- | --- |
| Python | **3.9+** (3.11 / 3.12 recommended) |
| cryptography | 42.0.0+ (installed automatically) |

### 1️⃣ Install

```bash
# From source (registers the `toolgate` command)
pip install .

# Without installing, run as a module
python -m toolgate --version

# Docker (see "Packaging & Deployment" below)
docker compose up -d
```

### 2️⃣ Start the gateway

```bash
toolgate serve --host 127.0.0.1 --port 8848
```

Then open:

- Health check: `http://127.0.0.1:8848/healthz`
- Web console: `http://127.0.0.1:8848/ui/`

### 3️⃣ Create an admin token (once)

```bash
toolgate tokens create my-admin --scope admin
# ⚠️ The plaintext token is shown only once — store it safely now.
```

> Local CLI management (`creds` / `tools` / `tokens`) reads and writes the local database directly and needs no token.
> The HTTP management examples below require the admin token in the request header.

### 4️⃣ Store a credential

```bash
# Use a trailing - to read the secret from stdin and keep it out of shell history
toolgate creds set github_pat "ghp_your_token_here" --description "GitHub PAT"
```

### 5️⃣ Register tools

```bash
# HTTP tool: the GitHub API, credential injected as a Bearer Authorization header
toolgate tools add-endpoint github \
  --base-url https://api.github.com \
  --auth-bearer github_pat

# Command-line tool: the gh CLI, credential injected via the GH_TOKEN env var
toolgate tools add-cli ghcli \
  --argv "gh" \
  --env-bind "github_pat:GH_TOKEN" \
  --named "repo:--repo" \
  --free-args
```

### 6️⃣ Create a call token and give it to the agent

```bash
toolgate tokens create agent1 --scope call
```

The agent now calls every tool with that single token:

```bash
# List tools
curl -H "Authorization: Bearer <CALL_TOKEN>" \
  http://127.0.0.1:8848/v1/tools

# Transparent proxy: equivalent to https://api.github.com/user (credential auto-injected)
curl -H "Authorization: Bearer <CALL_TOKEN>" \
  http://127.0.0.1:8848/v1/tool/github/user

# Call a command-line tool
curl -X POST -H "Authorization: Bearer <CALL_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"params":{"repo":"octocat/hello-world"},"args":["issue","list"]}' \
  http://127.0.0.1:8848/v1/call/ghcli
```

🎉 Done — the agent never touches a real API key.

---

## 📖 Usage Guide

### 🔧 CLI reference

```text
toolgate keygen                      # generate a master key
toolgate serve [--host --port]       # start the gateway
toolgate search "weather query"      # search the catalog
toolgate tools ls|show|rm|enable|disable
toolgate tools add-endpoint NAME ... # register an HTTP tool
toolgate tools add-cli NAME ...      # register a CLI tool
toolgate creds ls|set|rm             # manage credentials
toolgate tokens ls|create|revoke     # manage gateway tokens
toolgate call NAME ...               # invoke a tool locally (no HTTP)
toolgate audit [--tool --limit]      # view the audit trail
toolgate stats                       # instance statistics
```

### 🌐 HTTP API reference

| Method | Path | Scope | Description |
| --- | --- | --- | --- |
| GET | `/healthz` | none | Health check |
| GET | `/v1/tools` | call | List tools (optional `?kind=endpoint`) |
| GET | `/v1/tools/{name}` | call | Tool details |
| GET | `/v1/search?q=&kind=&limit=` | call | TF-IDF search |
| POST | `/v1/call/{name}` | call | Unified call (HTTP / CLI) |
| ANY | `/v1/tool/{name}/{path}` | call | Transparent proxy for HTTP tools |
| GET | `/v1/admin/stats` | admin | Instance statistics |
| GET/POST | `/v1/admin/credentials` | admin | List / create credentials |
| DELETE | `/v1/admin/credentials/{name}` | admin | Delete a credential |
| POST | `/v1/admin/tools` | admin | Create a tool |
| PUT/DELETE | `/v1/admin/tools/{name}` | admin | Update / delete a tool |
| POST | `/v1/admin/tools/{name}/enabled` | admin | Enable or disable a tool |
| GET/POST | `/v1/admin/tokens` | admin | List / create tokens |
| DELETE | `/v1/admin/tokens/{name}` | admin | Revoke a token |
| GET | `/v1/admin/audit` | admin | Audit log |

### 📮 Unified call: POST `/v1/call/{name}`

**Calling a CLI tool**:

```json
{
  "params": { "repo": "octocat/hello-world" },
  "args": ["issue", "list"],
  "stdin": null
}
```

**Calling an HTTP tool (JSON envelope)**:

```json
{
  "method": "POST",
  "path": "users/123",
  "query": "verbose=true",
  "headers": { "X-Custom": "yes" },
  "body": { "hello": "world" }
}
```

> When `body` is an object it is serialized to JSON automatically with
> `Content-Type: application/json`; you can also pass a raw string. Responses
> come back in a JSON envelope containing the upstream `status`, `headers`
> and `body`.

### 🧩 Credential-binding shortcuts (when registering an endpoint)

```bash
--header-bind "cred:X-Api-Key"            # inject a header with the raw secret
--auth-bearer cred                        # inject Authorization: Bearer <secret>
--query-bind  "cred:api_key"              # inject a query parameter
--basic-bind  "cred:username"             # HTTP Basic Auth
--bind-json   '{"credential":"cred","location":"header","name":"Authorization","template":"Token {value}"}'
```

### 🐍 Embedding as a Python library

```python
from toolgate.config import ToolGateConfig
from toolgate.server import build_server

config = ToolGateConfig.from_env("./data", host="127.0.0.1", port=8848)
server = build_server(config)
server.serve_forever()
```

### 🖼️ Screenshots (placeholders)

> Screenshots and a demo GIF will ship with future releases:
>
> - 📸 Web console catalog: `docs/asset-screenshot-catalog.png`
> - 📸 Transparent-proxy call: `docs/asset-screenshot-proxy.png`
> - 🎬 End-to-end demo: `docs/asset-demo.gif`

### 🧪 Typical use cases

- 🤖 Give multiple agents a **single tool egress** with centralized credential management and revocation;
- 🏢 Turn internal CLI-only scripts into **HTTP services** for agents in seconds;
- 🔍 Let agents describe what they want in natural language and let the gateway find the tool;
- 🧾 Provide a **non-repudiable call audit** in compliance-sensitive settings.

---

## 💡 Design & Roadmap

### 🧠 Design philosophy

1. **Relay, don't model** — the gateway does not parse or cache upstream business semantics, so it barely changes when upstream APIs evolve.
2. **Minimum credential exposure** — credentials are encrypted at rest, injected at the call site, and agents only hold low-privilege gateway tokens; CLI credentials prefer environment variables over argv.
3. **Secure by default** — `shell=False`, argument whitelisting, rate limiting and auditing work out of the box.
4. **Standard library first** — dependencies and environment traps are minimized, without compromising security (encryption uses the dedicated `cryptography` package).

### 🗺️ Roadmap

- [ ] 🔄 Incremental search index and an optional vector-retrieval backend;
- [ ] 🧾 Automatic OpenAPI generation and tool-schema export;
- [ ] 🤝 Two-way integration with the Model Context Protocol (MCP) ecosystem;
- [ ] 👥 Multi-user / multi-project spaces and finer-grained token permissions (per-tool authorization);
- [ ] 📊 Call analytics in the web console;
- [ ] 🪵 Structured log export (JSON Lines) and external SIEM integration.

### 🌱 How to contribute

Security reviews, documentation in more languages, registration templates for real tools and edge-case tests make excellent PRs. See [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## 📦 Packaging & Deployment

ToolGate is a **self-hosted service / CLI / library** and is platform-independent. Use whichever method you prefer.

### 🐳 Docker (recommended for servers)

```bash
# One command
docker compose up -d

# Or build manually
docker build -t toolgate .
docker run -d -p 8848:8848 \
  -v toolgate-data:/data \
  -e TOOLGATE_MASTER_KEY="$(toolgate keygen)" \
  toolgate
```

State (the SQLite database and audit log) lives in the `/data` volume.

### 📁 Install from a release

Head to the [Releases page](https://github.com/gitstq/ToolGate/releases):

- `toolgate-1.0.0-py3-none-any.whl` — platform-independent; install with `pip install toolgate-1.0.0-py3-none-any.whl`;
- `toolgate-1.0.0.tar.gz` — source distribution;
- `toolgate-linux-x86_64` — a standalone Linux x86_64 binary (tested on Linux).

> ⚠️ On Windows / macOS we recommend the **wheel (pip) or Docker** — both are platform-independent and risk-free. Standalone binaries cannot be cross-compiled, so only the tested Linux binary is provided.

### 🔨 Build locally

```bash
python -m pip install build
python -m build

python -m unittest discover -s tests
bash scripts/smoke.sh
```

### 🔑 About the master key

- Setting `TOOLGATE_MASTER_KEY` (generate with `toolgate keygen`) is ideal for containers;
- Otherwise the gateway creates a `master.key` file with `0600` permissions in the data directory;
- **Back up the master key** — if it is lost, stored credentials cannot be decrypted.

---

## 🤝 Contributing

Issues and pull requests are welcome! Please follow [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat: add a feature
fix: fix a bug
docs: update documentation
test: add or update tests
refactor: refactor code
```

For the full workflow (branching, tests, security notes), see 👉 **[CONTRIBUTING.md](../CONTRIBUTING.md)**.

---

## 📄 License

Released under the **[MIT License](../LICENSE)** — free to use, modify and distribute.

<div align="center">

If ToolGate helps you, please leave a ⭐️ — it means a lot!

**🐝 ToolGate — let agents safely call the whole world.**

</div>
