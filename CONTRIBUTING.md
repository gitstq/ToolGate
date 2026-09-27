# Contributing to ToolGate / 贡献指南

[English](#english) · [简体中文](#简体中文)

---

## English

Thanks for taking the time to contribute! ToolGate is small on purpose —
bug reports, security reviews, documentation improvements and new tests are
all very welcome.

### Reporting issues

- Use the issue tracker and pick the right template.
- Include the ToolGate version (`toolgate --version`), OS, Python version
  and the steps to reproduce the problem.
- **Never paste real credentials or gateway tokens** in an issue.

### Pull requests

1. Fork the repository and create a branch from `main`.
2. Follow the existing code style; the runtime should stay on the standard
   library plus `cryptography`.
3. Add or update tests for what you change, then run:

   ```bash
   python -m unittest discover -s tests
   bash scripts/smoke.sh
   ```

4. Keep commits focused and use [Conventional Commits](https://www.conventionalcommits.org/):

   ```text
   feat: add per-token daily quota
   fix: preserve query strings in transparent proxy
   docs: clarify Docker master-key handling
   test: cover CLI timeout
   refactor: split header building out of proxy
   ```

5. Open the pull request against `main` and describe what and why.

### Security

If you discover a vulnerability involving credential handling, please open a
private security advisory rather than a public issue.

---

## 简体中文

感谢你愿意为 ToolGate 做贡献！本项目刻意保持轻量，我们非常欢迎缺陷
反馈、安全审查、文档改进和测试补充。

### 提交 Issue

- 请在 Issue 区选择对应模板。
- 附上 ToolGate 版本（`toolgate --version`）、操作系统、Python 版本以及
  复现步骤。
- **绝对不要**在 Issue 中粘贴真实凭证或网关令牌。

### 提交 Pull Request

1. Fork 仓库，从 `main` 分支创建你的分支。
2. 遵循现有代码风格；运行时请保持“标准库 + cryptography”的范围。
3. 为改动补充或更新测试，并运行：

   ```bash
   python -m unittest discover -s tests
   bash scripts/smoke.sh
   ```

4. 提交信息请遵循 [Conventional Commits（约定式提交）](https://www.conventionalcommits.org/zh-hans/)
   规范：

   ```text
   feat: 新增每令牌每日配额
   fix: 修复透明代理丢失查询串的问题
   docs: 补充 Docker 主密钥说明
   test: 补充 CLI 超时测试
   refactor: 从代理模块拆出请求头构建
   ```

5. 向 `main` 分支发起 Pull Request，并说明改动内容与原因。

### 安全问题

如果你发现涉及凭证处理的安全漏洞，请通过私密安全公告（Private Security
Advisory）联系我们，而不是提交公开 Issue。
