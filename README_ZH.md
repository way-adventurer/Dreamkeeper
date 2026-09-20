# 守梦 · Dreamkeeper

[![GitHub Stars](https://img.shields.io/github/stars/way-adventurer/Dreamkeeper?style=flat&logo=github)](https://github.com/way-adventurer/Dreamkeeper/stargazers)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-63e6be.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-f0b90b.svg)](CHANGELOG.md)

**[English README](README.md)**

> **歇会吧，到我了。**

Dreamkeeper（守梦）是一个本地优先的 AI 与 GPU 实验监视台。它会将实验从当前终端中独立出来，持续监视远程进程和服务器状态，并且只在任务真正结束时发送一次有用的完成通知。

## 为什么使用守梦？

- **本地优先：** 实验元数据、SQLite 状态、SSH 信息、日志和连接器密钥都保存在本机。
- **服务器感知：** 可导入 VSCode/OpenSSH 配置，查看 GPU 显存、利用率、温度、功耗和 GPU 进程，不需要在服务器上安装守护程序。
- **适合 Agent：** 支持提交、列表、状态、日志、等待、取消实验，并可在完成时唤醒 Codex CLI。
- **清晰的开发者界面：** 深色控制台风格，方便快速判断实验和服务器是否正常。
- **连接器友好：** 原生支持飞书/Lark，同时提供可接入 Slack、Discord、Teams、n8n、Make 或自建服务的通用 Webhook。

## 快速开始

```bash
python -m pip install -e .
dreamkeeper submit --host local --command "python -c \"import time; print('done'); time.sleep(2)\""
dreamkeeper list
dreamkeeper ui --host 127.0.0.1 --port 8765
```

打开 <http://127.0.0.1:8765>。监视首页是 `/`，SSH 服务器配置和连接器位于 `/servers`。

### Windows 桌面版

如果不想使用终端，直接双击仓库根目录醒目的 [`Dreamkeeper.exe`](Dreamkeeper.exe)，或从项目
Release 下载同一文件即可运行。启动器会自动启动本地仪表盘并打开浏览器。数据默认保存在
`~/.dreamkeeper`（如果已有旧版 `~/.runrelay` 则继续复用），启动时不需要 SSH 服务器或 GPU。

本地构建 exe：

```powershell
.\packaging\build_windows.ps1
```

构建完成后会同时把 exe 复制到仓库根目录，便于一键启动。如需自定义数据目录、监听地址或端口，可设置
`DREAMKEEPER_HOME`、`DREAMKEEPER_HOST`、`DREAMKEEPER_PORT`。

已有 SSH 主机时：

```bash
dreamkeeper submit --host gpu-183 --workdir /home/user/project --command "python train.py --config configs/a.yaml"
dreamkeeper status <experiment-id>
dreamkeeper wait <experiment-id>
dreamkeeper logs <experiment-id>
```

## 仪表盘与服务器监视

仪表盘包含监视页和服务器页：前者用于查看运行中的进程、完成状态、日志和实验任务；后者用于保存 SSH 配置、导入 VSCode/OpenSSH 配置、测试连接、刷新快照和启动只读实时采样。

SSH 探针会读取主机名、系统信息、NVIDIA GPU 指标、GPU 计算进程和远程进程列表。如果服务器没有 `nvidia-smi`，CPU 和进程监视仍然可用，页面会明确显示 GPU 指标不可用。

```bash
dreamkeeper server import-ssh --path ~/.ssh/config
dreamkeeper server list
dreamkeeper server test <server-id>
dreamkeeper monitor start --server-id <server-id> --command-filter train.py --interval 5
```

## 连接器

| 连接器 | 方向 | 适用场景 | 密钥处理 |
| --- | --- | --- | --- |
| 飞书 / Lark | 入站 + 出站 | 发现会话并发送任务完成消息 | App Secret 只保存在本机，不返回浏览器 |
| 通用 Webhook | 出站 | Slack、Discord、Teams、n8n、Make 或自建服务 | 可选 Bearer Token 只保存在本机，不返回浏览器 |
| Telegram | 配置 + 就绪测试 | BotFather Token、Polling、可选 Chat ID | Bot Token 只保存摘要，浏览器只看到是否已设置 |
| WhatsApp | 配置 | 本地会话、二维码/配对码，兼容 Meta Cloud 字段 | 会话目录和访问令牌留在本机 |
| QQ | 配置 + 凭据校验 | Gateway 直连、App ID/App Secret、自动发现 OpenID | App Secret 不返回浏览器 |
| 微信 | 配置 | iLink 地址、本地会话目录和命令前缀 | 本地会话路径保存在本机 |
| Rokid Glasses | 配置 | 公网地址、SSE 路径、Agent AK/SK | AK/SK 不返回浏览器 |
| 文件 / 命令 / Codex CLI | 出站 | 本地脚本和 Agent 唤醒 | 使用本地文件系统和进程环境 |

可在 **`/servers` → 连接器** 中配置，也可以调用 `/api/connectors/*` 接口。每个连接器详情页都提供 **配置教程** 按钮，展示准备事项、配置步骤和安全提示。微信页面保存 iLink 配置和本地会话目录，二维码绑定由连接器运行时完成。Webhook 完成事件使用普通 JSON：

```json
{"event":"completed","text":"守梦任务已完成...","monitor_id":"mon_xxx","server":"Training GPU"}
```

## Codex 集成

项目在 `plugins/runrelay` 中提供可选的 Codex Skill 和 MCP 适配器。默认后端是安全的 `noop`，自动唤醒需要显式启用。启用前请阅读 [docs/codex-integration.md](docs/codex-integration.md)。

## 项目结构

```text
src/runrelay/       运行时、SSH/GPU 监视、SQLite 存储、仪表盘
tests/              本地与模拟集成测试
docs/               架构、协议和 Codex 集成文档
plugins/runrelay/   可选 Codex Skill 与 MCP 适配器
integrations/       连接器和 Agent 集成说明
```

## 验证与安全边界

```bash
.venv\Scripts\python.exe -m pytest -q
```

测试使用模拟 SSH 输出进行确定性的本地验证。真实 SSH 认证、远程进程检查、NVIDIA 驱动、外部 Webhook 以及飞书凭据仍需要在你的环境中单独验证。

守梦只保存 SSH 主机元数据和本地私钥**路径**，不会读取或保存私钥内容；项目本地优先运行，不要求 OpenAI 账号。

## 贡献与许可证

欢迎提交 Issue 和 Pull Request。提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [SECURITY.md](SECURITY.md)。MIT License，详见 [LICENSE](LICENSE)。
