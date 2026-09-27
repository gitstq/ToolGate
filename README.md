<div align="center">

# 🚪 ToolGate

### 一个网关，调用所有工具 · One Gateway, Every Tool

**面向 AI Agent 的自托管工具统一网关 —— 一个 Base URL、一个网关令牌，安全调用团队的全部 HTTP API 与命令行工具。**

🌐 语言 / Language：
[简体中文](README.md) · [繁體中文](docs/README_zh-TW.md) · [English](docs/README_en.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-teal.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Release](https://img.shields.io/badge/release-v1.0.0-brightgreen.svg)](https://github.com/gitstq/ToolGate/releases)
[![Downloads](https://img.shields.io/github/downloads/gitstq/ToolGate/total.svg)](https://github.com/gitstq/ToolGate/releases)

⬇️ **[立即下载 Release（wheel / sdist / Linux 单文件）](https://github.com/gitstq/ToolGate/releases)**

</div>

---

## 🎉 项目介绍

AI Agent 要真正干活，就需要调用一堆外部工具：查天气、读 GitHub、发邮件、抓数据、跑团队内部脚本……但现实很骨感：

- 🔑 **凭证到处分发**：每接入一个 Agent，就要把各家 API Key 复制一遍，泄露面无限扩大；
- 🧩 **工具协议五花八门**：有的要 Header、有的要 Query、有的只提供命令行，Agent 集成成本高；
- 🧾 **缺乏统一审计**：谁、在什么时候、用哪个工具调了什么，无从追溯。

**ToolGate 把所有工具收敛到一个网关后面。** Agent 只需要记住一个 Base URL、持有一个网关令牌；所有真实凭证都以加密形式保存在服务端，在请求发出的那一刻才被注入，**永远不会下发给 Agent**。

> 🦞 **差异化亮点（自研）**
> - 🔒 **凭证零明文**：Fernet 认证加密（AES-128-CBC + HMAC-SHA256），主密钥可由环境变量注入；
> - 🔌 **两类工具统一治理**：HTTP 工具走**透明反向代理**（原样透传 method / body / query / 响应），命令行工具被**安全地 HTTP 化**；
> - 🛡️ **命令行零命令注入**：`shell=False` + 参数白名单 + 凭证走环境变量；
> - 🎫 **令牌治理**：令牌只存哈希、可命名、可吊销、可单独限流；
> - 🔍 **内置 TF-IDF 工具搜索**（含中文单字切分），让 Agent“描述任务”而不是“记住工具名”；
> - 🖥️ **三种用法**：自带零依赖 Web 控制台、跨平台 CLI、可嵌入的 Python 库；
> - 🪶 **极轻量**：运行时仅依赖 `cryptography`，其余全部使用 Python 标准库。

💡 **灵感来源**：本项目受到近期 GitHub 热门的“工具界 OpenRouter”理念启发，但 ToolGate 为 **100% 独立自研**，聚焦**完全自托管、本地优先、无云依赖、无遥测**，不包含任何第三方目录数据，代码与数据结构均为原创。

---

## ✨ 核心特性

- 🔐 **服务端凭证注入**：支持 `Header`、`Query`、`HTTP Basic Auth` 三种 HTTP 注入位置，以及 CLI 的环境变量注入，支持 `Bearer {value}` 等自定义模板。
- 🌐 **透明反向代理**：网关**只转发、不建模**，请求方法、路径、查询串、请求体、绝大多数请求头原样到达上游，上游状态码与响应体原样返回。
- ⌨️ **CLI 工具 HTTP 化**：把任意命令行工具注册成 HTTP 端点，内置超时控制、输出截断、退出码回传。
- 🛡️ **纵深安全设计**：加密存储、令牌哈希、参数白名单、无 shell 执行、按令牌限流（Token Bucket）、完整审计日志。
- 🔍 **语义化目录搜索**：零依赖 TF-IDF，支持英文分词与中文单字，工具名命中额外加权。
- 🖥️ **内置 Web 控制台**：浏览工具目录、搜索、在线发起调用、查看审计，单文件 HTML、无需构建。
- 📦 **开箱即用的工程化**：`pip` 安装、Docker / docker-compose、一键冒烟脚本、单元测试齐全。
- 🌍 **跨平台**：Windows / macOS / Linux 通用，Python 3.9 及以上。

---

## 🚀 快速开始

### 📋 环境要求

| 依赖 | 版本 |
| --- | --- |
| Python | **3.9+**（推荐 3.11 / 3.12） |
| cryptography | 42.0.0+（安装时自动拉取） |

### 1️⃣ 安装

```bash
# 方式一：从源码安装（推荐，自动注册 toolgate 命令）
pip install .

# 方式二：免安装，直接用模块方式运行
python -m toolgate --version

# 方式三：Docker（详见下方“打包与部署”）
docker compose up -d
```

### 2️⃣ 启动网关

```bash
toolgate serve --host 127.0.0.1 --port 8848
```

启动后可访问：

- 健康检查：`http://127.0.0.1:8848/healthz`
- Web 控制台：`http://127.0.0.1:8848/ui/`

### 3️⃣ 创建管理员令牌（只需一次）

```bash
toolgate tokens create my-admin --scope admin
# ⚠️ 令牌明文仅显示一次，请立即安全保存
```

> CLI 本地管理命令（`creds` / `tools` / `tokens`）直接读写本地数据库，无需携带令牌；
> 下方 HTTP 管理示例请在请求头中带上管理员令牌。

### 4️⃣ 存入一个凭证

```bash
# 末尾使用 - 可从标准输入读取，避免密钥进入 shell 历史
toolgate creds set github_pat "ghp_your_token_here" --description "GitHub PAT"
```

### 5️⃣ 注册工具

```bash
# HTTP 工具：GitHub API，凭证以 Bearer 方式注入 Authorization 头
toolgate tools add-endpoint github \
  --base-url https://api.github.com \
  --auth-bearer github_pat

# 命令行工具：gh CLI，凭证通过环境变量 GH_TOKEN 注入
toolgate tools add-cli ghcli \
  --argv "gh" \
  --env-bind "github_pat:GH_TOKEN" \
  --named "repo:--repo" \
  --free-args
```

### 6️⃣ 创建调用令牌并交给 Agent

```bash
toolgate tokens create agent1 --scope call
```

Agent 现在只需一个令牌即可调用所有工具：

```bash
# 列出工具
curl -H "Authorization: Bearer <CALL_TOKEN>" \
  http://127.0.0.1:8848/v1/tools

# 透明代理：等价于请求 https://api.github.com/user（凭证自动注入）
curl -H "Authorization: Bearer <CALL_TOKEN>" \
  http://127.0.0.1:8848/v1/tool/github/user

# 调用命令行工具
curl -X POST -H "Authorization: Bearer <CALL_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"params":{"repo":"octocat/hello-world"},"args":["issue","list"]}' \
  http://127.0.0.1:8848/v1/call/ghcli
```

🎉 大功告成！Agent 全程接触不到任何真实 API Key。

---

## 📖 详细使用指南

### 🔧 命令行总览

```text
toolgate keygen                      # 生成一个主密钥
toolgate serve [--host --port]       # 启动网关
toolgate search "查询天气" [--kind]   # 搜索工具目录
toolgate tools ls|show|rm|enable|disable
toolgate tools add-endpoint NAME ... # 注册 HTTP 工具
toolgate tools add-cli NAME ...      # 注册 CLI 工具
toolgate creds ls|set|rm             # 管理凭证
toolgate tokens ls|create|revoke     # 管理网关令牌
toolgate call NAME ...               # 不经 HTTP，本地直接调用工具
toolgate audit [--tool --limit]      # 查看审计日志
toolgate stats                       # 查看实例统计
```

### 🌐 HTTP API 一览

| 方法 | 路径 | 所需作用域 | 说明 |
| --- | --- | --- | --- |
| GET | `/healthz` | 无 | 健康检查 |
| GET | `/v1/tools` | call | 列出工具（可 `?kind=endpoint`） |
| GET | `/v1/tools/{name}` | call | 工具详情 |
| GET | `/v1/search?q=&kind=&limit=` | call | TF-IDF 搜索 |
| POST | `/v1/call/{name}` | call | 统一调用（HTTP / CLI） |
| ANY | `/v1/tool/{name}/{path}` | call | HTTP 工具透明代理 |
| GET | `/v1/admin/stats` | admin | 实例统计 |
| GET/POST | `/v1/admin/credentials` | admin | 凭证列表 / 新建 |
| DELETE | `/v1/admin/credentials/{name}` | admin | 删除凭证 |
| POST | `/v1/admin/tools` | admin | 新建工具 |
| PUT/DELETE | `/v1/admin/tools/{name}` | admin | 更新 / 删除工具 |
| POST | `/v1/admin/tools/{name}/enabled` | admin | 启停工具 |
| GET/POST | `/v1/admin/tokens` | admin | 令牌列表 / 新建 |
| DELETE | `/v1/admin/tokens/{name}` | admin | 吊销令牌 |
| GET | `/v1/admin/audit` | admin | 审计日志 |

### 📮 统一调用：POST `/v1/call/{name}`

**调用 CLI 工具**：

```json
{
  "params": { "repo": "octocat/hello-world" },
  "args": ["issue", "list"],
  "stdin": null
}
```

**调用 HTTP 工具（JSON 信封）**：

```json
{
  "method": "POST",
  "path": "users/123",
  "query": "verbose=true",
  "headers": { "X-Custom": "yes" },
  "body": { "hello": "world" }
}
```

> `body` 传对象时会自动序列化为 JSON 并加上 `Content-Type: application/json`；
> 也可直接传字符串。响应统一以 JSON 信封返回，包含上游 `status`、`headers`、`body`。

### 🧩 凭证绑定的四种快捷方式（注册 endpoint 时）

```bash
--header-bind "cred:X-Api-Key"            # 注入请求头，值为密钥原文
--auth-bearer cred                        # 注入 Authorization: Bearer <密钥>
--query-bind  "cred:api_key"              # 注入查询参数
--basic-bind  "cred:username"             # HTTP Basic Auth
--bind-json   '{"credential":"cred","location":"header","name":"Authorization","template":"Token {value}"}'
```

### 🐍 作为 Python 库嵌入

```python
from toolgate.config import ToolGateConfig
from toolgate.server import build_server

config = ToolGateConfig.from_env("./data", host="127.0.0.1", port=8848)
server = build_server(config)
server.serve_forever()
```

### 🖼️ 运行截图（占位）

> 截图 / 演示动图将随版本补充：
>
> - 📸 Web 控制台工具目录：`docs/asset-screenshot-catalog.png`
> - 📸 透明代理调用：`docs/asset-screenshot-proxy.png`
> - 🎬 端到端演示动图：`docs/asset-demo.gif`

### 🧪 典型使用场景

- 🤖 为多个 AI Agent 提供**统一工具出口**，集中管理与回收凭证；
- 🏢 把团队内部只提供 CLI 的脚本**快速变成 HTTP 服务**，供 Agent 调用；
- 🔍 让 Agent 通过自然语言描述“我想做什么”，由网关搜索可用工具；
- 🧾 在合规场景下提供**不可抵赖的调用审计**。

---

## 💡 设计思路与迭代规划

### 🧠 设计理念

1. **网关只转发、不建模（Relay, don't model）**：不解析、不缓存上游业务语义，因此上游 API 变化时网关几乎无需改动。
2. **凭证最小暴露**：凭证加密落库、调用点注入、Agent 只持有低权限网关令牌；CLI 凭证优先走环境变量而非命令行参数。
3. **默认安全**：`shell=False`、参数白名单、限流、审计全部开箱即用。
4. **标准库优先**：在不牺牲安全（加密使用专业的 `cryptography`）的前提下，把依赖和环境陷阱降到最低。

### 🗺️ 后续迭代计划

- [ ] 🔄 增量式搜索索引与可选的向量检索后端；
- [ ] 🧾 OpenAPI 自动生成与工具调用 Schema 导出；
- [ ] 🤝 与 MCP（Model Context Protocol）生态的双向适配；
- [ ] 👥 多用户 / 多项目空间与更细粒度的令牌权限（按工具授权）；
- [ ] 📊 Web 控制台的调用统计图表；
- [ ] 🪵 结构化日志导出（JSON Lines）与外部 SIEM 集成。

### 🌱 社区贡献方向

安全审查、更多语言的文档、针对真实工具的注册模板、边界测试用例都是绝佳的 PR 方向，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 📦 打包与部署指南

ToolGate 属于**自托管服务 / CLI / 工具库**，平台无关，推荐以下任一方式部署。

### 🐳 Docker 部署（推荐用于服务器）

```bash
# 一键启动
docker compose up -d

# 或手动构建
docker build -t toolgate .
docker run -d -p 8848:8848 \
  -v toolgate-data:/data \
  -e TOOLGATE_MASTER_KEY="$(toolgate keygen)" \
  toolgate
```

数据（SQLite 数据库、审计日志）保存在 `/data` 卷中。

### 📁 从 Release 安装

前往 [Releases 页面](https://github.com/gitstq/ToolGate/releases)：

- `toolgate-1.0.0-py3-none-any.whl`：平台无关，`pip install toolgate-1.0.0-py3-none-any.whl`；
- `toolgate-1.0.0.tar.gz`：源码包；
- `toolgate-linux-x86_64`：Linux x86_64 单文件可执行（已在 Linux 实测）。

> ⚠️ Windows / macOS 用户推荐使用 **wheel（pip 安装）或 Docker**，二者平台无关、零风险；
> 单文件可执行程序受限于“无法跨平台编译”，仅提供实测可用的 Linux 版本。

### 🔨 本地构建

```bash
# 构建 wheel 与 sdist
python -m pip install build
python -m build

# 运行测试与冒烟
python -m unittest discover -s tests
bash scripts/smoke.sh
```

### 🔑 关于主密钥

- 设置环境变量 `TOOLGATE_MASTER_KEY`（用 `toolgate keygen` 生成）最适合容器；
- 不设置时，网关会在数据目录创建权限为 `0600` 的 `master.key`；
- **请妥善备份主密钥**：丢失后已存凭证将无法解密。

---

## 🤝 贡献指南

欢迎提交 Issue 与 Pull Request！请遵循 [Conventional Commits（约定式提交）](https://www.conventionalcommits.org/zh-hans/) 规范：

```text
feat: 新增功能
fix: 修复问题
docs: 文档更新
test: 测试相关
refactor: 代码重构
```

完整流程（分支、测试、安全注意事项）请阅读 👉 **[CONTRIBUTING.md](CONTRIBUTING.md)**。

---

## 📄 开源协议

本项目基于 **[MIT License](LICENSE)** 开源，可自由使用、修改与分发。

<div align="center">

如果 ToolGate 帮到了你，请给它一个 ⭐️ Star，这对我们是最大的鼓励！

**🐝 ToolGate —— 让 Agent 安全地调用整个世界。**

</div>
