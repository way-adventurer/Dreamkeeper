# Architecture

Dreamkeeper has three deliberately separable layers:

    CLI / dashboard
          |
          v
    DreamkeeperService ---- SQLite state
          |
          +---- LocalExecutor
          +---- SSHExecutor
          +---- ServerMonitorService ---- SSHProbe (read-only)
          |
          +---- WakeBackend

## Lifecycle

    PENDING -> STARTING -> RUNNING -> COMPLETED
                                  \-> FAILED
                                  \-> CANCELLED
                                  \-> LOST

The remote runner owns the durable process lifecycle. It writes pid, stdout.log, stderr.log, and exit_code below ~/.dreamkeeper/jobs/<id>. A broken SSH connection therefore does not imply that the experiment stopped. Dreamkeeper reconciles the local SQLite row whenever status, list, wait, or daemon run is called.

The MVP uses a foreground daemon run loop instead of installing an operating-system service. This keeps installation portable and makes failure behavior inspectable. A future release can add launchd/systemd/Windows service adapters without changing the storage or executor interfaces.

## Server monitoring

Server profiles, the latest server snapshot, and process monitors use separate SQLite tables
from experiment rows. `ServerMonitorService` runs a fixed, read-only remote probe over the
user's local SSH configuration. The probe asks for hostname, system, `ps`, and NVIDIA
`nvidia-smi` CSV data; user selectors are applied locally after parsing, while optional
stdout/stderr tail paths are shell-quoted before a separate tail request.

Starting a process monitor performs one synchronous probe to prove that the PID or filter
matches. It then starts the existing detached local daemon. The optional server live sampler
uses the same daemon and a default two-second interval to persist dynamic GPU cards and the
GPU-only `nvidia-smi` process list. Each daemon iteration reads active monitor rows, polls
SSH, and persists the latest snapshot. A target that was observed and later disappears
becomes `COMPLETED`; connection failures remain visible as retryable `last_error` values.
Dashboard GET endpoints do not poll SSH, so browser refreshes cannot be mistaken for the
unattended monitor.

## Why wait is a first-class operation

dreamkeeper wait is intentionally a blocking local process. It can wait for hours without making model requests. A Codex tool call may still have host-side timeout limits, so the CLI also supports detached monitoring through daemon run and later inspection through status/logs.
