from __future__ import annotations

import base64
import os
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import Experiment, Status


@dataclass
class RemoteState:
    status: Status
    exit_code: int | None = None
    pid: int | None = None
    detail: str | None = None


class ExecutorError(RuntimeError):
    pass


class LocalExecutor:
    def submit(self, experiment: Experiment) -> int:
        directory = Path(experiment.local_dir)
        directory.mkdir(parents=True, exist_ok=True)
        worker = Path(__file__).with_name("worker.py")
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0
            )
        process = subprocess.Popen(
            [
                sys.executable,
                str(worker),
                "--command",
                experiment.command,
                "--workdir",
                experiment.workdir,
                "--log-dir",
                str(directory),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
            creationflags=creationflags,
        )
        return process.pid

    def status(self, experiment: Experiment) -> RemoteState:
        directory = Path(experiment.local_dir)
        exit_file = directory / "exit_code"
        cancelled = directory / "cancelled"
        if exit_file.exists():
            try:
                code = int(exit_file.read_text(encoding="utf-8").strip())
            except ValueError:
                return RemoteState(Status.LOST, detail="Invalid local exit_code file")
            final = Status.CANCELLED if cancelled.exists() else (
                Status.COMPLETED if code == 0 else Status.FAILED
            )
            return RemoteState(final, code, experiment.pid)
        if cancelled.exists():
            return RemoteState(Status.CANCELLED, None, experiment.pid)
        if experiment.pid and _pid_alive(experiment.pid):
            return RemoteState(Status.RUNNING, None, experiment.pid)
        return RemoteState(Status.LOST, None, experiment.pid, "Local worker disappeared without exit_code")

    def cancel(self, experiment: Experiment) -> None:
        directory = Path(experiment.local_dir)
        (directory / "cancelled").write_text("1", encoding="utf-8")
        if experiment.pid:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(experiment.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    os.killpg(experiment.pid, signal.SIGTERM)
            except OSError:
                pass

    def logs(self, experiment: Experiment) -> tuple[str, str]:
        directory = Path(experiment.local_dir)
        return _read_file(directory / "stdout.log"), _read_file(directory / "stderr.log")


class SSHExecutor:
    def __init__(self, connect_timeout: int = 10):
        self.connect_timeout = connect_timeout

    def _ssh(
        self, experiment: Experiment, script: str, *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                [
                    "ssh",
                    "-o",
                    f"ConnectTimeout={self.connect_timeout}",
                    experiment.host,
                    "bash",
                    "-s",
                ],
                input=script,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.connect_timeout + 15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExecutorError(f"SSH failed for {experiment.host}: {exc}") from exc
        if check and result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "remote command failed"
            raise ExecutorError(message)
        return result

    def submit(self, experiment: Experiment) -> tuple[int, str]:
        command_b64 = base64.b64encode(experiment.command.encode()).decode()
        workdir_b64 = base64.b64encode(experiment.workdir.encode()).decode()
        job = f"$HOME/.dreamkeeper/jobs/{experiment.id}"
        script = f"""set -eu
job="{job}"
mkdir -p "$job"
printf '%s' {shlex.quote(command_b64)} | base64 -d > "$job/command.sh"
printf '%s' {shlex.quote(workdir_b64)} | base64 -d > "$job/workdir"
cat > "$job/runner.sh" <<'RUNRELAY_RUNNER'
#!/bin/sh
set +e
job="$HOME/.dreamkeeper/jobs/{experiment.id}"
workdir=$(cat "$job/workdir")
date -u +%Y-%m-%dT%H:%M:%SZ > "$job/start_time"
cd "$workdir" || {{
  printf '%s\n' "Unable to change to workdir: $workdir" > "$job/stderr.log"
  printf '%s' "1" > "$job/exit_code"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$job/end_time"
  exit 1
}}
bash "$job/command.sh" > "$job/stdout.log" 2> "$job/stderr.log"
rc=$?
printf '%s' "$rc" > "$job/exit_code"
date -u +%Y-%m-%dT%H:%M:%SZ > "$job/end_time"
exit "$rc"
RUNRELAY_RUNNER
chmod 700 "$job/runner.sh" "$job/command.sh"
nohup "$job/runner.sh" </dev/null >/dev/null 2>&1 &
pid=$!
printf '%s\n' "$pid" > "$job/pid"
printf '%s\n' "$pid"
"""
        result = self._ssh(experiment, script)
        try:
            pid = int(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise ExecutorError(f"Remote runner did not return a PID: {result.stdout!r}") from exc
        return pid, job

    def status(self, experiment: Experiment) -> RemoteState:
        job = f"$HOME/.dreamkeeper/jobs/{experiment.id}"
        script = f"""set -eu
job="{job}"
if [ -f "$job/cancelled" ]; then echo CANCELLED; exit 0; fi
if [ -f "$job/exit_code" ]; then printf 'EXIT:%s\n' "$(cat "$job/exit_code")"; exit 0; fi
if [ -f "$job/pid" ] && kill -0 "$(cat "$job/pid")" 2>/dev/null; then printf 'RUNNING:%s\n' "$(cat "$job/pid")"; exit 0; fi
echo LOST
"""
        result = self._ssh(experiment, script, check=False)
        if result.returncode != 0:
            return RemoteState(
                Status.RUNNING,
                pid=experiment.pid,
                detail=result.stderr.strip() or "Unable to reconcile remote job; will retry",
            )
        line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "LOST"
        if line == "CANCELLED":
            return RemoteState(Status.CANCELLED, pid=experiment.pid)
        if line.startswith("EXIT:"):
            code = int(line.split(":", 1)[1])
            return RemoteState(Status.COMPLETED if code == 0 else Status.FAILED, code, experiment.pid)
        if line.startswith("RUNNING:"):
            return RemoteState(Status.RUNNING, pid=int(line.split(":", 1)[1]))
        return RemoteState(Status.LOST, pid=experiment.pid, detail="Remote job disappeared without exit_code")

    def cancel(self, experiment: Experiment) -> None:
        job = f"$HOME/.dreamkeeper/jobs/{experiment.id}"
        script = f"""set -eu
job="{job}"
touch "$job/cancelled"
if [ -f "$job/pid" ]; then kill -TERM "$(cat "$job/pid")" 2>/dev/null || true; fi
"""
        self._ssh(experiment, script)

    def logs(self, experiment: Experiment) -> tuple[str, str]:
        job = f"$HOME/.dreamkeeper/jobs/{experiment.id}"
        script = f"""set +e
job="{job}"
printf 'STDOUT\\0'
cat "$job/stdout.log" 2>/dev/null || true
printf '\\0STDERR\\0'
cat "$job/stderr.log" 2>/dev/null || true
"""
        result = self._ssh(experiment, script, check=False)
        if result.returncode != 0:
            raise ExecutorError(result.stderr.strip() or "Unable to read remote logs")
        raw = result.stdout.split("\0")
        stdout = raw[1] if len(raw) > 1 else ""
        stderr = raw[3] if len(raw) > 3 else ""
        return stdout, stderr


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
