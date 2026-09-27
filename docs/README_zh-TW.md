<div align="center">

# 🚪 ToolGate

### 一個閘道，呼叫所有工具 · One Gateway, Every Tool

**專為 AI Agent 打造的自託管工具統一閘道 —— 一組 Base URL、一支閘道權杖，安全呼叫團隊的所有 HTTP API 與命令列工具。**

🌐 語言 / Language：
[简体中文](../README.md) · [繁體中文](README_zh-TW.md) · [English](README_en.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-teal.svg)](../LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Release](https://img.shields.io/badge/release-v1.0.0-brightgreen.svg)](https://github.com/gitstq/ToolGate/releases)
[![Downloads](https://img.shields.io/github/downloads/gitstq/ToolGate/total.svg)](https://github.com/gitstq/ToolGate/releases)

⬇️ **[立即下載最新版本（wheel / sdist / Linux 單檔案）](https://github.com/gitstq/ToolGate/releases)**

</div>

---

## 🎉 專案介紹

AI Agent 要真正完成工作，就得呼叫各式外部工具：查天氣、讀取 GitHub、寄送郵件、擷取資料、執行團隊內部指令……但現實往往令人頭痛：

- 🔑 **憑證四處散佈**：每接入一個 Agent，就得複製一次各家 API Key，外洩風險不斷放大；
- 🧩 **工具協定百百種**：有的要帶 Header、有的要帶 Query、有的只提供命令列，Agent 整合成本高昂；
- 🧾 **缺乏統一稽核機制**：誰在什麼時候用了哪個工具呼叫了什麼，無從追溯。

**ToolGate 把所有工具收攏到單一閘道後方。** Agent 只需要記住一組 Base URL、持有一支閘道權杖；所有真實憑證都以加密形式存放在伺服器端，在請求送出的當下才進行注入，**永遠不會下發給 Agent**。

> 🦞 **差異化亮點（自研）**
> - 🔒 **憑證零明文**：採用 Fernet 認證加密（AES-128-CBC + HMAC-SHA256），主金鑰可透過環境變數注入；
> - 🔌 **兩類工具統一治理**：HTTP 工具走**透明反向代理**（method / body / query / 回應原樣傳遞），命令列工具則被**安全地 HTTP 化**；
> - 🛡️ **命令列零注入風險**：`shell=False`＋參數白名單＋憑證走環境變數；
> - 🎫 **權杖治理**：權杖只儲存雜湊值、可命名、可撤銷、可單獨限流；
> - 🔍 **內建 TF-IDF 工具搜尋**（含中文單字斷詞），讓 Agent「描述任務」而不是「死記工具名稱」；
> - 🖥️ **三種使用方式**：內建零相依網頁主控台、跨平台 CLI、可嵌入的 Python 函式庫；
> - 🪶 **極度輕量**：執行階段僅相依於 `cryptography`，其餘皆使用 Python 標準函式庫。

💡 **靈感來源**：本專案受到近期 GitHub 熱門的「工具界 OpenRouter」理念啟發，但 ToolGate 為 **100% 獨立自研**，聚焦**完全自託管、本機優先、無雲端依賴、無遙測**，不包含任何第三方目錄資料，程式碼與資料結構皆為原創。

---

## ✨ 核心特性

- 🔐 **伺服器端憑證注入**：支援 `Header`、`Query`、`HTTP Basic Auth` 三種 HTTP 注入位置，以及 CLI 的環境變數注入，並支援 `Bearer {value}` 等自訂範本。
- 🌐 **透明反向代理**：閘道**只轉發、不建模**，請求方法、路徑、查詢字串、請求主體、絕大多數請求標頭都會原樣抵達上游，上游狀態碼與回應主體也原樣回傳。
- ⌨️ **CLI 工具 HTTP 化**：將任意命令列工具註冊為 HTTP 端點，內建逾時控制、輸出截斷與結束碼回報。
- 🛡️ **縱深防禦設計**：加密儲存、權杖雜湊、參數白名單、無 shell 執行、依權杖限流（Token Bucket）以及完整稽核日誌。
- 🔍 **語意化目錄搜尋**：零相依 TF-IDF，支援英文斷詞與中文單字，工具名稱命中額外加權。
- 🖥️ **內建網頁主控台**：瀏覽工具目錄、搜尋、線上發起呼叫、檢視稽核紀錄，單一 HTML 檔案、免建置。
- 📦 **開箱即用的工程化設定**：`pip` 安裝、Docker / docker-compose、一鍵冒煙腳本，單元測試一應俱全。
- 🌍 **跨平台**：Windows / macOS / Linux 皆適用，支援 Python 3.9 以上版本。

---

## 🚀 快速開始

### 📋 環境需求

| 需求 | 版本 |
| --- | --- |
| Python | **3.9+**（建議 3.11 / 3.12） |
| cryptography | 42.0.0+（安裝時自動取得） |

### 1️⃣ 安裝

```bash
# 從原始碼安裝（建議，會自動註冊 toolgate 指令）
pip install .

# 免安裝，直接以模組方式執行
python -m toolgate --version

# Docker（詳見下方「打包與部署」）
docker compose up -d
```

### 2️⃣ 啟動閘道

```bash
toolgate serve --host 127.0.0.1 --port 8848
```

啟動後可開啟：

- 健康檢查：`http://127.0.0.1:8848/healthz`
- 網頁主控台：`http://127.0.0.1:8848/ui/`

### 3️⃣ 建立管理員權杖（僅需一次）

```bash
toolgate tokens create my-admin --scope admin
# ⚠️ 權杖明文只會顯示一次，請立即妥善保存
```

> CLI 本機管理指令（`creds` / `tools` / `tokens`）會直接讀寫本機資料庫，無需攜帶權杖；
> 下方的 HTTP 管理範例，請在請求標頭中帶入管理員權杖。

### 4️⃣ 存入一組憑證

```bash
# 結尾加上 - 可從標準輸入讀取，避免金鑰進入 shell 歷史紀錄
toolgate creds set github_pat "ghp_your_token_here" --description "GitHub PAT"
```

### 5️⃣ 註冊工具

```bash
# HTTP 工具：GitHub API，憑證以 Bearer 方式注入 Authorization 標頭
toolgate tools add-endpoint github \
  --base-url https://api.github.com \
  --auth-bearer github_pat

# 命令列工具：gh CLI，憑證透過環境變數 GH_TOKEN 注入
toolgate tools add-cli ghcli \
  --argv "gh" \
  --env-bind "github_pat:GH_TOKEN" \
  --named "repo:--repo" \
  --free-args
```

### 6️⃣ 建立呼叫權杖並交給 Agent

```bash
toolgate tokens create agent1 --scope call
```

Agent 現在只要一支權杖就能呼叫所有工具：

```bash
# 列出工具
curl -H "Authorization: Bearer <CALL_TOKEN>" \
  http://127.0.0.1:8848/v1/tools

# 透明代理：等同於請求 https://api.github.com/user（憑證自動注入）
curl -H "Authorization: Bearer <CALL_TOKEN>" \
  http://127.0.0.1:8848/v1/tool/github/user

# 呼叫命令列工具
curl -X POST -H "Authorization: Bearer <CALL_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"params":{"repo":"octocat/hello-world"},"args":["issue","list"]}' \
  http://127.0.0.1:8848/v1/call/ghcli
```

🎉 大功告成！Agent 全程都接觸不到任何真實的 API Key。

---

## 📖 詳細使用指南

### 🔧 命令列一覽

```text
toolgate keygen                      # 產生一組主金鑰
toolgate serve [--host --port]       # 啟動閘道
toolgate search "查詢天氣" [--kind]   # 搜尋工具目錄
toolgate tools ls|show|rm|enable|disable
toolgate tools add-endpoint NAME ... # 註冊 HTTP 工具
toolgate tools add-cli NAME ...      # 註冊 CLI 工具
toolgate creds ls|set|rm             # 管理憑證
toolgate tokens ls|create|revoke     # 管理閘道權杖
toolgate call NAME ...               # 不經 HTTP，直接在本機呼叫工具
toolgate audit [--tool --limit]      # 檢視稽核日誌
toolgate stats                       # 檢視執行個體統計
```

### 🌐 HTTP API 一覽

| 方法 | 路徑 | 所需作用域 | 說明 |
| --- | --- | --- | --- |
| GET | `/healthz` | 無 | 健康檢查 |
| GET | `/v1/tools` | call | 列出工具（可 `?kind=endpoint`） |
| GET | `/v1/tools/{name}` | call | 工具詳情 |
| GET | `/v1/search?q=&kind=&limit=` | call | TF-IDF 搜尋 |
| POST | `/v1/call/{name}` | call | 統一呼叫（HTTP / CLI） |
| ANY | `/v1/tool/{name}/{path}` | call | HTTP 工具透明代理 |
| GET | `/v1/admin/stats` | admin | 執行個體統計 |
| GET/POST | `/v1/admin/credentials` | admin | 憑證列表 / 新建 |
| DELETE | `/v1/admin/credentials/{name}` | admin | 刪除憑證 |
| POST | `/v1/admin/tools` | admin | 新建工具 |
| PUT/DELETE | `/v1/admin/tools/{name}` | admin | 更新 / 刪除工具 |
| POST | `/v1/admin/tools/{name}/enabled` | admin | 啟停工具 |
| GET/POST | `/v1/admin/tokens` | admin | 權杖列表 / 新建 |
| DELETE | `/v1/admin/tokens/{name}` | admin | 撤銷權杖 |
| GET | `/v1/admin/audit` | admin | 稽核日誌 |

### 📮 統一呼叫：POST `/v1/call/{name}`

**呼叫 CLI 工具**：

```json
{
  "params": { "repo": "octocat/hello-world" },
  "args": ["issue", "list"],
  "stdin": null
}
```

**呼叫 HTTP 工具（JSON 封包）**：

```json
{
  "method": "POST",
  "path": "users/123",
  "query": "verbose=true",
  "headers": { "X-Custom": "yes" },
  "body": { "hello": "world" }
}
```

> 當 `body` 傳入物件時，會自動序列化為 JSON 並加上 `Content-Type: application/json`；
> 也可以直接傳入字串。回應統一以 JSON 封包回傳，內含上游的 `status`、`headers` 與 `body`。

### 🧩 憑證繫結的四種快捷方式（註冊 endpoint 時）

```bash
--header-bind "cred:X-Api-Key"            # 注入請求標頭，值為金鑰原文
--auth-bearer cred                        # 注入 Authorization: Bearer <金鑰>
--query-bind  "cred:api_key"              # 注入查詢參數
--basic-bind  "cred:username"             # HTTP Basic Auth
--bind-json   '{"credential":"cred","location":"header","name":"Authorization","template":"Token {value}"}'
```

### 🐍 作為 Python 函式庫嵌入

```python
from toolgate.config import ToolGateConfig
from toolgate.server import build_server

config = ToolGateConfig.from_env("./data", host="127.0.0.1", port=8848)
server = build_server(config)
server.serve_forever()
```

### 🖼️ 執行擷圖（預留位置）

> 擷圖／展示動畫將於後續版本補上：
>
> - 📸 網頁主控台工具目錄：`docs/asset-screenshot-catalog.png`
> - 📸 透明代理呼叫：`docs/asset-screenshot-proxy.png`
> - 🎬 端到端展示動畫：`docs/asset-demo.gif`

### 🧪 典型使用情境

- 🤖 為多個 AI Agent 提供**統一工具出口**，集中管理與回收憑證；
- 🏢 把團隊內部僅提供 CLI 的指令**快速變成 HTTP 服務**，供 Agent 呼叫；
- 🔍 讓 Agent 以自然語言描述「想要做什麼」，再由閘道搜尋可用工具；
- 🧾 在合規情境下提供**不可否認的呼叫稽核紀錄**。

---

## 💡 設計思路與迭代規劃

### 🧠 設計理念

1. **閘道只轉發、不建模（Relay, don't model）**：不解析、不快取上游的業務語意，因此上游 API 變動時閘道幾乎不需修改。
2. **憑證最小暴露**：憑證加密落庫、於呼叫點注入，Agent 只持有低權限的閘道權杖；CLI 憑證優先走環境變數而非命令列參數。
3. **預設即安全**：`shell=False`、參數白名單、限流、稽核皆開箱即用。
4. **標準函式庫優先**：在不犧牲安全的前提下（加密使用專業的 `cryptography`），把相依項目與環境陷阱降到最低。

### 🗺️ 後續迭代計畫

- [ ] 🔄 增量式搜尋索引與可選的向量檢索後端；
- [ ] 🧾 OpenAPI 自動產生與工具呼叫 Schema 匯出；
- [ ] 🤝 與 MCP（Model Context Protocol）生態系的雙向介接；
- [ ] 👥 多使用者／多專案空間，以及更細緻的權杖權限（依工具授權）；
- [ ] 📊 網頁主控台的呼叫統計圖表；
- [ ] 🪵 結構化日誌匯出（JSON Lines）與外部 SIEM 整合。

### 🌱 社群貢獻方向

安全審查、更多語言的說明文件、針對真實工具的註冊範本、邊界測試案例，都是絕佳的 PR 方向，詳見 [CONTRIBUTING.md](../CONTRIBUTING.md)。

---

## 📦 打包與部署指南

ToolGate 屬於**自託管服務 / CLI / 工具函式庫**，與平台無關，推薦以下任一方式部署。

### 🐳 Docker 部署（適合用於伺服器）

```bash
# 一鍵啟動
docker compose up -d

# 或手動建置
docker build -t toolgate .
docker run -d -p 8848:8848 \
  -v toolgate-data:/data \
  -e TOOLGATE_MASTER_KEY="$(toolgate keygen)" \
  toolgate
```

資料（SQLite 資料庫、稽核日誌）會保存在 `/data` 磁碟區中。

### 📁 從 Release 安裝

請前往 [Releases 頁面](https://github.com/gitstq/ToolGate/releases)：

- `toolgate-1.0.0-py3-none-any.whl`：與平台無關，使用 `pip install toolgate-1.0.0-py3-none-any.whl`；
- `toolgate-1.0.0.tar.gz`：原始碼封包；
- `toolgate-linux-x86_64`：Linux x86_64 單檔案可執行檔（已於 Linux 實測）。

> ⚠️ Windows / macOS 使用者建議使用 **wheel（pip 安裝）或 Docker**，兩者皆與平台無關、零風險；
> 單檔案可執行檔受限於「無法跨平台編譯」，僅提供已實測可用的 Linux 版本。

### 🔨 本機建置

```bash
# 建置 wheel 與 sdist
python -m pip install build
python -m build

# 執行測試與冒煙
python -m unittest discover -s tests
bash scripts/smoke.sh
```

### 🔑 關於主金鑰

- 設定環境變數 `TOOLGATE_MASTER_KEY`（以 `toolgate keygen` 產生）最適合容器環境；
- 若未設定，閘道會在資料目錄建立權限為 `0600` 的 `master.key`；
- **請妥善備份主金鑰**：一旦遺失，已儲存的憑證將無法解密。

---

## 🤝 貢獻指南

歡迎提交 Issue 與 Pull Request！請遵循 [Conventional Commits（約定式提交）](https://www.conventionalcommits.org/) 規範：

```text
feat: 新增功能
fix: 修復問題
docs: 更新說明文件
test: 測試相關
refactor: 程式重構
```

完整流程（分支、測試、安全注意事項）請閱讀 👉 **[CONTRIBUTING.md](../CONTRIBUTING.md)**。

---

## 📄 開源授權

本專案採用 **[MIT License](../LICENSE)** 開源，可自由使用、修改與散布。

<div align="center">

如果 ToolGate 幫上了忙，請給它一顆 ⭐️ Star，這對我們是最大的鼓勵！

**🐝 ToolGate —— 讓 Agent 安全地呼叫整個世界。**

</div>
