# RunRelay + Codex

The repository now contains an installable Codex plugin at `plugins/runrelay`.
It bundles:

- `runrelay-experiments` — automatic guidance for choosing RunRelay for long-running jobs;
- a local MCP server exposing submit, list, status, wait, logs, and cancel tools;
- a repo marketplace entry at `.agents/plugins/marketplace.json`.

## 人工安装

在仓库根目录打开终端，依次执行：

    python -m pip install -e .
    codex plugin marketplace add .
    codex plugin add runrelay --marketplace personal

执行 `codex plugin list` 确认 `runrelay@personal` 已安装并启用，然后新开一个 Codex 会话。

如果只想在本机安装一次并把任务发到远程服务器，请保持 Codex 会话运行在本机，把服务器 SSH 别名作为 RunRelay 的 `host`。不要在 Codex SSH 远程项目会话中期待本机插件自动出现：该会话使用远程主机自己的 Skill、MCP 和工具配置；远程模式需要单独安装。

## 直接交给 Codex

下面的内容可以直接复制给 Codex：

    请安装当前仓库里的 RunRelay Codex 插件并验证安装结果：
    1. 确认当前目录是本机仓库根目录，并存在 plugins/runrelay 和 .agents/plugins/marketplace.json
    2. 执行 python -m pip install -e .
    3. 执行 codex plugin marketplace add .
    4. 执行 codex plugin add runrelay --marketplace personal
    5. 执行 codex plugin list，确认 runrelay@personal 已安装且启用
    6. 不要启动、提交或取消实验，只验证安装；完成后提醒我新开本机 Codex 会话测试

Start a new Codex chat after installation so the bundled Skill and MCP tools are available. You can also explicitly invoke the plugin or skill with `@`.

Use RunRelay when a command is expected to run long enough that repeated polling would waste agent turns. For SSH targets, keep the Codex session local and pass the configured SSH alias as the RunRelay host.

    runrelay submit --host gpu-183 --workdir /home/user/project --command "python train.py"
    runrelay wait <id>

If the local Codex CLI session should continue after completion, opt in explicitly:

    runrelay submit \
      --host gpu-183 \
      --workdir /home/user/project \
      --command "python train.py" \
      --wake-backend codex-cli \
      --session <session-id> \
      --continuation-prompt "Inspect the completed experiment and continue the plan."

This integration starts a local Codex CLI process. It is not a claim that an arbitrary open Desktop conversation can be remotely poked.
