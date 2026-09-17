# RunRelay Codex plugin

This package connects Codex to the local RunRelay experiment sidecar. It provides the `runrelay-experiments` Skill and a local MCP server for submitting, listing, inspecting, waiting for, reading logs from, and cancelling experiments.

When a job is submitted through the Codex MCP adapter, RunRelay starts a detached local monitor automatically. The adapter's default `auto` wake mode records the current Codex thread/session ID and resumes that persisted local CLI thread after the remote job reaches a terminal state. No model-side polling is required.

## Human installation

From the repository root, run:

    python -m pip install -e .
    codex plugin marketplace add .
    codex plugin add runrelay --marketplace personal

Verify the installation:

    codex plugin list

Confirm that `runrelay@personal` is installed and enabled, then start a new Codex chat before testing the plugin.

## SSH host scope

For one local installation serving many experiment servers, keep the Codex chat on the local machine and let RunRelay use the server's SSH alias as `host`. For example:

    Use RunRelay to run `python train.py` on `gpu-183` in `/home/user/project`, then wait and read the logs.

A Codex SSH remote-project chat runs with the remote host's own skills, MCP servers, and local tools. It does not inherit plugins installed on the local machine. Using that mode requires a separate plugin installation on the remote Codex environment; this is a Codex host boundary, not a missing RunRelay executable in the local installation.

## Copy-paste installation prompt for Codex

The following prompt asks Codex to install and verify the plugin without starting an experiment:

    Install the RunRelay Codex plugin from the current repository.
    Confirm that the current directory is the repository root and that plugins/runrelay and .agents/plugins/marketplace.json exist.
    Run `python -m pip install -e .`, then run `codex plugin marketplace add .`, then run `codex plugin add runrelay --marketplace personal`.
    Run `codex plugin list` and confirm that runrelay@personal is installed and enabled.
    Do not submit, start, or cancel any experiment. Report the installation result and remind me to start a new Codex chat before testing.

## Test prompt

After opening a new Codex chat, try:

    Use RunRelay to run a local smoke test with `python -c "print('RunRelay works')"`, wait for it to finish, and read the logs. Do not use a remote GPU.

The Skill should not submit a job merely because RunRelay is mentioned. A real submission requires a concrete command, host, working directory, and explicit run intent.
