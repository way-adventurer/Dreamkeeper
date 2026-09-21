# 守梦 · Dreamkeeper

[![GitHub Stars](https://img.shields.io/github/stars/way-adventurer/Dreamkeeper?style=flat&logo=github)](https://github.com/way-adventurer/Dreamkeeper/stargazers)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-63e6be.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-f0b90b.svg)](CHANGELOG.md)

**[中文文档](README_ZH.md)**

> **Rest now. I’ll wake you when it’s time.**

Dreamkeeper is a local-first control room for long-running AI and GPU experiments. It detaches jobs
from the initiating terminal, watches remote processes and GPU servers in the background, and sends
one useful completion event when a run actually finishes.

## Why Dreamkeeper?

- **Local-first:** experiment metadata, SQLite state, SSH metadata, logs, and connector secrets stay on your machine.
- **Server-aware:** import VSCode/OpenSSH profiles and inspect GPU metrics and processes without installing an agent on the server.
- **Automation-friendly:** submit, list, inspect, wait for, cancel, and trigger a local file or command when a long-running job is complete.
- **Readable by default:** a dark developer-style dashboard makes active work and server health easy to scan.
- **Connector-ready:** native Feishu/Lark notifications plus a provider-neutral JSON Webhook for Slack, Discord, Teams, n8n, Make, or custom services.

## Quick start

```bash
python -m pip install -e .
dreamkeeper submit --host local --command "python -c \"import time; print('done'); time.sleep(2)\""
dreamkeeper list
dreamkeeper ui --host 127.0.0.1 --port 8765
```

Open <http://127.0.0.1:8765>. The Dreamkeeper home is available at `/`; SSH dreams, VSCode import, and message channels are managed at `/servers`.

### Windows desktop build

If you prefer not to use a terminal, double-click the prominent [`Dreamkeeper.exe`](Dreamkeeper.exe)
in the repository root, or download the same file from a project release. The launcher starts the
local dashboard and opens your browser automatically. It stores data under `~/.dreamkeeper` (or the
existing legacy `~/.runrelay` directory) and never needs an SSH server or GPU to start.

To build the executable locally:

```powershell
.\packaging\build_windows.ps1
```

The build also copies the executable to the repository root for one-click access. Set `DREAMKEEPER_HOME`, `DREAMKEEPER_HOST`, or
`DREAMKEEPER_PORT` before launching if you need a custom data directory or port.

For an existing SSH host:

```bash
dreamkeeper submit --host gpu-183 --workdir /home/user/project --command "python train.py --config configs/a.yaml"
dreamkeeper status <experiment-id>
dreamkeeper wait <experiment-id>
dreamkeeper logs <experiment-id>
```

## Dreamkeeper home and server activity

The home page is the quiet place for **Dream tasks**. It lists active tasks, completion state, logs, and experiment records without requiring a terminal tab to stay open. The server page manages SSH dreams, VSCode/OpenSSH import, connection tests, snapshots, and read-only live sampling.

The SSH probe collects hostname, system information, NVIDIA GPU metrics, GPU compute processes, and the remote process list. On the home page, **Dream activity** is grouped by server so you can see each GPU process and click **Add dream task** beside a PID. The PID field also accepts pasted text and keeps the numeric PID automatically. If `nvidia-smi` is unavailable, CPU/process information still works and the missing capability is reported clearly.

```bash
dreamkeeper server import-ssh --path ~/.ssh/config
dreamkeeper server list
dreamkeeper server test <server-id>
dreamkeeper monitor start --server-id <server-id> --command-filter train.py --interval 5
```

## Connectors

| Connector | Direction | Use case | Secret handling |
| --- | --- | --- | --- |
| Feishu / Lark | Inbound + outbound | Discover a chat and send completion messages | App Secret stays local and is never returned to the browser |
| Generic Webhook | Outbound | Slack, Discord, Teams, n8n, Make, or custom services | Optional bearer token stays local and is never returned |
| Telegram | Config + readiness test | BotFather token, polling, optional chat ID | The browser only sees whether the bot token is set |
| WhatsApp | Configuration | Local session, QR/pairing auth, Meta Cloud legacy fields | Session paths and access tokens stay local |
| QQ | Config + credential validation | Direct gateway, App ID/App Secret, discovered OpenID | App Secret is never returned to the browser |
| WeChat | Configuration | iLink base URL, local session directory, command prefix | Session paths remain local |
| Rokid Glasses | Configuration | Public base URL, SSE path, Agent AK/SK | AK/SK values are never returned to the browser |
| File / command | Outbound | Local scripts and automation hooks | Uses the local filesystem/process environment |

Configure connectors from **`/servers` → Connectors** or through the `/api/connectors/*` endpoints. Every connector detail page includes a **Setup guide** button with prerequisites, steps, and safety notes. WeChat stores an iLink profile locally; QR binding is completed by the connector runtime. Webhook completion events are ordinary JSON:

```json
{"event":"completed","text":"守梦任务已完成...","monitor_id":"mon_xxx","server":"Training GPU"}
```

## Project layout

```text
src/runrelay/       runtime, SSH/GPU monitor, SQLite storage, dashboard
tests/              local and simulated integration tests
docs/               architecture and protocol notes
integrations/       connector integration guidance
```

## Verification and security boundaries

```bash
.venv\Scripts\python.exe -m pytest -q
```

The test suite uses simulated SSH output for deterministic local checks. Real SSH authentication, remote process inspection, NVIDIA drivers, external Webhooks, and Feishu credentials remain environment-specific checks.

Dreamkeeper stores SSH host metadata and local private-key **paths**, never private-key contents. It is local-first by design and does not require an external AI account.

## Contributing and license

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). MIT License · see [LICENSE](LICENSE).
