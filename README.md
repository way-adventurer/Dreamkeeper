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
- **Agent-friendly:** submit, list, inspect, wait for, cancel, and wake a Codex CLI session when a long-running job is complete.
- **Readable by default:** a dark developer-style dashboard makes active work and server health easy to scan.
- **Connector-ready:** native Feishu/Lark notifications plus a provider-neutral JSON Webhook for Slack, Discord, Teams, n8n, Make, or custom services.

## Quick start

```bash
python -m pip install -e .
dreamkeeper submit --host local --command "python -c \"import time; print('done'); time.sleep(2)\""
dreamkeeper list
dreamkeeper ui --host 127.0.0.1 --port 8765
```

Open <http://127.0.0.1:8765>. The monitor is available at `/`; SSH profiles and connectors are managed at `/servers`.

For an existing SSH host:

```bash
dreamkeeper submit --host gpu-183 --workdir /home/user/project --command "python train.py --config configs/a.yaml"
dreamkeeper status <experiment-id>
dreamkeeper wait <experiment-id>
dreamkeeper logs <experiment-id>
```

## Dashboard and server monitoring

The dashboard provides a monitor page for active processes, completion state, logs, and experiment jobs, plus a server page for SSH profiles, VSCode/OpenSSH import, connection tests, snapshots, and read-only live sampling.

The SSH probe collects hostname, system information, NVIDIA GPU metrics, GPU compute processes, and the remote process list. If `nvidia-smi` is unavailable, CPU/process monitoring still works and the missing capability is reported clearly.

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
| File / command / Codex CLI | Outbound | Local scripts and agent wake-ups | Uses the local filesystem/process environment |

Configure connectors from **`/servers` → Connectors** or through the `/api/connectors/*` endpoints. Webhook completion events are ordinary JSON:

```json
{"event":"completed","text":"守梦任务已完成...","monitor_id":"mon_xxx","server":"Training GPU"}
```

## Codex integration

Dreamkeeper includes an optional Codex Skill and MCP adapter under `plugins/runrelay`. The safe default is `noop`; automated wake-up is opt-in. Read [docs/codex-integration.md](docs/codex-integration.md) before enabling it.

## Project layout

```text
src/runrelay/       runtime, SSH/GPU monitor, SQLite storage, dashboard
tests/              local and simulated integration tests
docs/               architecture, protocol, and Codex integration notes
plugins/runrelay/   optional Codex Skill + MCP adapter
integrations/       connector and agent integration guidance
```

## Verification and security boundaries

```bash
.venv\Scripts\python.exe -m pytest -q
```

The test suite uses simulated SSH output for deterministic local checks. Real SSH authentication, remote process inspection, NVIDIA drivers, external Webhooks, and Feishu credentials remain environment-specific checks.

Dreamkeeper stores SSH host metadata and local private-key **paths**, never private-key contents. It is local-first by design and does not require an OpenAI account.

## Contributing and license

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). MIT License · see [LICENSE](LICENSE).
