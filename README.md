# 守梦 / Dreamkeeper

Dreamkeeper means “守梦”: AI does not need to repeatedly wake up and check whether an experiment has finished. Dreamkeeper watches the experiment and wakes AI only when it is truly needed. The GitHub project slug and primary command are `dreamkeeper`; `runrelay` remains as a compatibility alias.

Slogan: “Rest now. I’ll wake you when it’s time.” / “你先歇着，时候到了，我叫你。”

> Agents should reason when decisions are needed, not while experiments are running.

Dreamkeeper is a local-first experiment sidecar for coding and research agents. It launches a command locally or over SSH, detaches it from the initiating terminal, starts an independent local monitor, persists metadata in SQLite, and can resume a Codex CLI thread after completion without repeated model polling.

The project is intentionally agent-neutral. Codex integration is included, but the runtime does not require an OpenAI account or send commands and logs to a third party.

## MVP

    dreamkeeper submit -> detached process -> SQLite metadata -> status/logs/wait

The first release supports:

- local detached jobs and remote Linux jobs through the user's existing ssh configuration;
- persistent experiment metadata and state reconciliation after a CLI restart;
- submit, list, status, logs, wait, cancel, daemon run, and a small local dashboard;
- completion notifications through noop, auto, file, command, and codex-cli wake backends;
- local Git commit, branch, and dirty-tree capture at submission time.

## Server GPU monitor MVP

The dashboard also provides a small, unattended SSH monitor for existing servers. It saves
only the SSH host/alias, port, username, and local private-key path in SQLite; private-key
contents are never read into Dreamkeeper state or logs. The read-only probe collects hostname,
system, NVIDIA GPU model, memory, utilization, temperature, power, and GPU processes, plus
the remote `ps` process list. If `nvidia-smi` is unavailable, the snapshot remains usable for
CPU/process monitoring and reports `nvidia-smi not found` clearly.

Start the local dashboard:

    dreamkeeper ui --host 127.0.0.1 --port 8765

Then open http://127.0.0.1:8765. The dashboard supports Chinese/English switching. The monitor
page is at `/`; the dedicated server configuration page is at `/servers`. Save a server there,
use “Test SSH connection and fetch snapshot”, and start a monitor with a PID or command/user
filter. The page refreshes saved SQLite state; the local daemon performs the SSH polls
independently after a monitor is started.

On the monitor page, “Start live sampling” starts an independent read-only sampler (default
2 seconds). GPU cards then update from saved snapshots with memory/utilization bars, and the
process table shows only GPU compute processes reported by `nvidia-smi`, rather than every
kernel/system process returned by `ps`. Stop live sampling when it is no longer needed.

### Import VSCode Remote-SSH configuration

On the `/servers` page, enter the local SSH config path (normally `~/.ssh/config`) and click
“Import and parse Host blocks”. This imports concrete `Host` blocks such as:

    Host gpu-134
        HostName 192.0.2.134
        User researcher
        RemoteForward 7897 127.0.0.1:7897

The alias, HostName, User, Port, IdentityFile, and RemoteForward values are parsed and saved as
server profile fields. Wildcard blocks such as `Host *` are skipped. RemoteForward is retained
as configuration metadata; the read-only GPU probe does not automatically open a port forward.
The equivalent CLI command is:

    dreamkeeper server import-ssh --path ~/.ssh/config

The equivalent CLI commands are:

    dreamkeeper server add --name "Training GPU" --host gpu-183 --port 22 --user alice --identity-file ~/.ssh/id_ed25519
    dreamkeeper server list
    dreamkeeper server test <server-id>
    dreamkeeper server refresh <server-id>
    dreamkeeper monitor start --server-id <server-id> --pid 12345 --interval 5
    dreamkeeper monitor start --server-id <server-id> --command-filter train.py --user-filter alice
    dreamkeeper monitor list
    dreamkeeper monitor status <monitor-id>

When a target process disappears after being observed, the monitor records completion time,
the last GPU/process summary, and optional tails from the configured stdout/stderr paths. A
generic remote process exit code cannot be recovered after it exits; it is therefore reported
as null unless an integration provides an exit record. Connection errors are retained for
retry and PID/filter misses fail immediately with a clear message.

### Feishu completion connector

The dashboard no longer uses a browser alert when a monitored process finishes. On `/servers`,
open 配置 → 通知 and use the native Feishu connector. It follows the same local long-connection
flow as DeepScientist: enter the Feishu app `App ID` and `App Secret`, enable notifications,
save, then send one message to the bot. Dreamkeeper discovers that conversation automatically
and sends completion messages back through the Feishu Open Platform API. No public webhook is
required.

The connector stores the app secret locally and never returns it to the browser after saving.
For an older installation that already uses an authenticated `lark-cli`, the legacy path remains
available and can still send one text message through:

    lark-cli im +messages-send --as bot --user-id ou_xxx --text "..."

Authenticate and verify the CLI before enabling notifications:

    lark-cli auth status

If delivery fails, the monitor still remains `COMPLETED` and the failure is recorded in its local
monitor log. The page's test button sends one explicit test message.

## Quick start

    python -m pip install -e .

    # Local smoke test
    dreamkeeper submit --host local --command "python -c \"import time; print('done'); time.sleep(2)\""
    dreamkeeper list
    dreamkeeper wait <experiment-id>
    dreamkeeper logs <experiment-id>

For a remote host already configured in ~/.ssh/config:

    dreamkeeper submit \
      --host gpu-183 \
      --workdir /home/user/project \
      --command "python train.py --config configs/a.yaml"

    dreamkeeper status <experiment-id>
    dreamkeeper wait <experiment-id>

The remote job is stored below ~/.dreamkeeper/jobs/<experiment-id> on the remote host. SSH passwords and private keys are never stored by Dreamkeeper.

## Codex completion wake-up

The terminal CLI keeps `noop` as its safe default. The Codex MCP adapter uses `auto`: it captures the current Codex thread/session ID and resumes that persisted local CLI thread when the experiment completes. The monitor is started automatically at submission time:

    dreamkeeper submit \
      --host gpu-183 \
      --workdir /home/user/project \
      --command "python train.py" \
      --wake-backend auto \
      --session <codex-thread-id> \
      --continuation-prompt "Experiment completed. Inspect the results and continue the research plan."

Read docs/codex-integration.md before enabling automated wake-up. This resumes a local Codex CLI thread; it does not claim to inject a message into an arbitrary open Desktop or SSH remote-project conversation.

## Codex plugin

Dreamkeeper includes an installable Codex plugin under `plugins/runrelay` for compatibility. It adds a Skill and a local MCP server with structured tools for submit, list, status, wait, logs, and cancel.

### 人工安装

在仓库根目录打开终端，依次执行：

    python -m pip install -e .
    codex plugin marketplace add .
    codex plugin add runrelay --marketplace personal

然后执行 `codex plugin list`，确认 `runrelay@personal` 已安装并启用。安装完成后请新开一个 Codex 会话；插件提供的 Skill 和 MCP 工具会在新会话中生效。

可以用下面这句话测试：

    使用 RunRelay 提交一个本地 smoke test：执行 python -c "print('RunRelay works')"，等待完成并读取日志；不要使用远程 GPU。

### SSH 远程服务器的使用方式

如果目标是“本机只安装一次，任务在远程服务器运行”，请在本机 Codex 会话中使用 RunRelay，并把远程 SSH 别名写入 `host`；RunRelay 会通过本机已有的 SSH 配置提交远程任务：

    使用 RunRelay 在 gpu-183 上后台运行 python train.py，工作目录是 /home/user/project；返回实验 ID，并等待完成后读取日志。

不要把这个测试放在 Codex 的“SSH 远程项目会话”里。SSH 远程项目会话由远程主机提供 Skill、MCP 和本地工具，本机安装的插件不会自动继承；若坚持使用该模式，就必须在对应远程 Codex 环境单独安装插件。这个限制来自 Codex 的远程宿主机隔离，不是 RunRelay 的命令路径问题。

### 直接交给 Codex 的安装内容

如果希望让另一个 Codex 会话代为安装，可以直接复制下面整段内容发送给它：

    请把当前仓库里的 RunRelay Codex 插件安装到本机 Codex，并完成安装验证。

    1. 确认当前目录是本机 RunRelay 仓库根目录，并且存在 plugins/runrelay 和 .agents/plugins/marketplace.json。
    2. 执行：python -m pip install -e .
    3. 执行：codex plugin marketplace add .
    4. 执行：codex plugin add runrelay --marketplace personal
    5. 执行：codex plugin list，确认 runrelay@personal 的 installed=true 且 enabled=true。
    6. 只验证插件安装、Skill 和 MCP 入口，不要提交、启动或取消任何实验。
    7. 返回安装结果；如果安装成功，提醒我新开一个“本机 Codex 会话”，再用 host 参数测试远程任务。

安装后的使用边界：当用户明确要求后台运行、提交或监控长时间实验、训练、视频生成、评测、渲染、GPU 或 SSH 任务时，Codex 应优先使用 RunRelay；仅仅提到“RunRelay”不会自动启动任务。提交任务仍需要明确的命令、主机、工作目录和运行意图。

## Verification and boundaries

Run the test suite with the repository-managed environment:

    uv pip install --python .venv\\Scripts\\python.exe pytest
    .venv\\Scripts\\python.exe -m pytest -q

The included simulated monitor test uses fake SSH output, so it verifies persistence, safe
SSH argument construction, GPU/process parsing, and process-end state flow without a real
GPU or SSH server. A local UI/API smoke test should use a temporary `--home` directory and
localhost only. Real SSH authentication, remote `ps`, NVIDIA driver/nvidia-smi output, and
remote stdout/stderr tail access remain user-environment checks and have not been claimed as
verified until a user supplies an SSH alias/configuration and an appropriate test server.

The early MVP still stages artifact transfer, retries, and richer OS service installation.
See docs/architecture.md and CHANGELOG.md.

### Copy-ready Codex test prompt

    In this RunRelay checkout, run the local-only validation for the server GPU monitor.
    Use a temporary RUNRELAY_HOME, do not connect to any SSH host, do not start a GPU
    experiment, and do not submit/cancel a real job. Run the simulated pytest tests and
    exercise the localhost UI/API if possible. Report exact commands, pass/fail results,
    and clearly separate simulated/local verification from checks requiring my SSH config
    and a real NVIDIA server.

## License

MIT. See LICENSE.
