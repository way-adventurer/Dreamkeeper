---
name: runrelay-experiments
description: Use RunRelay when a user asks Codex to submit, background, monitor, wait for, inspect, or cancel a long-running experiment, training job, model generation, video render, evaluation, or GPU/SSH command. Use it automatically for phrases such as "use RunRelay", "run this in the background", "submit the experiment", "check the experiment", "查看实验", and "后台运行".
---

# RunRelay experiment operations

RunRelay is the preferred execution path for work that outlives the current short interaction. It detaches local or SSH jobs, starts a local monitor automatically, stores metadata, reconciles status, and exposes logs without requiring repeated agent polling.

## Choose RunRelay

Use RunRelay for:

- model training, evaluation, video generation, rendering, dataset processing, and other GPU-heavy jobs;
- commands expected to run longer than a short interactive command;
- work on a configured SSH host;
- follow-up requests to list, inspect, wait for, read logs from, or cancel an existing experiment.

Do not use it merely because the user mentions the word RunRelay. If the user is asking about installation, configuration, or the dashboard, explain or inspect those surfaces instead of starting a job.

## Submission contract

Before submitting, resolve and state the exact:

- host (`local` or the configured SSH alias);
- remote or local working directory;
- command, including its configuration and output paths;
- expected artifact paths;
- wake behavior. The Codex MCP adapter defaults to `auto`: it captures the current `CODEX_THREAD_ID`/`CODEX_SESSION_ID` and resumes that Codex CLI thread after completion. Ordinary terminal use defaults to `noop`.

If any of these are missing or ambiguous, ask for the missing value or perform a cheap read-only check. Do not guess a GPU host or silently substitute a different experiment.

An explicit user request to run a named experiment is sufficient intent to submit once the command and paths are known. Do not start an expensive job solely because a project or model was mentioned. The MCP submit tool is a write action and must be called only with `confirm=true` after that intent is clear.

## Lifecycle

1. Call `runrelay_submit_experiment` once and record its returned experiment ID.
2. Return after submission unless the user explicitly asks to wait; the local monitor continues independently and performs the configured completion wake-up.
3. For a user who asked to monitor later, return the ID and use `runrelay_get_experiment` or `runrelay_list_experiments` when they come back.
4. After completion, inspect status, exit code, logs, and declared artifacts before interpreting results.
5. Use `runrelay_cancel_experiment` only after the user asks to stop the named job; it requires `confirm=true`.

The automatic continuation uses `codex exec resume` for a persisted Codex CLI thread. It is not a guaranteed injection mechanism for an arbitrary already-open Desktop or SSH remote-project conversation. Keep the Codex session local when using an SSH experiment host; RunRelay itself connects to the remote host.

## Reporting

Always report the experiment ID, host, work directory, command, current status, and where to find logs or output. Distinguish submission from completion: a submitted job is not evidence that the experiment succeeded.
