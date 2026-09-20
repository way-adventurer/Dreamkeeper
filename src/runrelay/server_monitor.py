from __future__ import annotations

import base64
import csv
import os
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .models import GPUSnapshot, ProcessMonitor, ProcessSnapshot, ServerProfile, ServerSnapshot
from .monitor import ensure_daemon
from .notifications import FeishuCliNotifier, FeishuNotificationError, WebhookNotificationError
from .storage import Storage


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ServerMonitorError(RuntimeError):
    pass


def validate_profile(profile: ServerProfile) -> None:
    if not profile.host or profile.host.startswith("-") or any(ord(c) < 32 for c in profile.host):
        raise ValueError("SSH host/alias must be non-empty and must not contain control characters")
    if not 1 <= profile.port <= 65535:
        raise ValueError("SSH port must be between 1 and 65535")
    for label, value in (("username", profile.username), ("identity file", profile.identity_file)):
        if value and any(ord(c) < 32 for c in value):
            raise ValueError(f"SSH {label} must not contain control characters")


class SSHProbe:
    """Read-only SSH probe. It never accepts private-key contents."""

    def __init__(self, runner: Callable[..., subprocess.CompletedProcess[str]] | None = None):
        self.runner = runner or subprocess.run

    def _args(self, profile: ServerProfile) -> list[str]:
        validate_profile(profile)
        args = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-p", str(profile.port)]
        if profile.username:
            args.extend(["-l", profile.username])
        if profile.identity_file:
            args.extend(["-i", str(Path(profile.identity_file).expanduser())])
        args.extend(["--", profile.host, "bash", "-s"])
        return args

    def run(self, profile: ServerProfile, script: str) -> subprocess.CompletedProcess[str]:
        try:
            # SSH targets are commonly Linux even when RunRelay runs on Windows.
            # Do not let CRLF turn redirections and `set +e` into invalid Bash.
            script = script.replace("\r\n", "\n").replace("\r", "\n")
            options = {
                "input": script.encode("utf-8"),
                "text": False,
                "capture_output": True,
                "check": False,
                "timeout": 25,
            }
            if os.name == "nt":
                # OpenSSH is a console executable. Without CREATE_NO_WINDOW,
                # every dashboard refresh briefly flashes an ssh.exe window.
                options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = self.runner(self._args(profile), **options)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ServerMonitorError(f"SSH connection failed for {profile.host}: {exc}") from exc
        stdout = result.stdout.decode("utf-8", errors="replace") if isinstance(result.stdout, bytes) else (result.stdout or "")
        stderr = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else (result.stderr or "")
        if result.returncode != 0:
            detail = (stderr or stdout).strip()
            if "permission denied" in detail.lower() and "bash:" not in detail.lower():
                detail = f"SSH permission denied for {profile.host}: {detail}"
            raise ServerMonitorError(detail or f"SSH command failed for {profile.host}")
        return subprocess.CompletedProcess(result.args, result.returncode, stdout, stderr)


def _b64(value: str | None) -> str:
    return base64.b64encode((value or "").encode("utf-8")).decode("ascii")


def _number(value: str) -> float | None:
    value = value.strip().replace("[N/A]", "")
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _integer(value: str) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _csv_line(line: str) -> list[str]:
    return next(csv.reader([line], skipinitialspace=True), [])


class ServerMonitorService:
    def __init__(
        self,
        root: Path,
        storage: Storage,
        probe: SSHProbe | None = None,
        notifier: FeishuCliNotifier | None = None,
    ):
        self.root = root
        self.storage = storage
        self.probe = probe or SSHProbe()
        self.notifier = notifier or FeishuCliNotifier(root)

    def save_server(
        self, *, server_id: str | None, name: str, host: str, port: int = 22,
        username: str | None = None, identity_file: str | None = None,
        remote_forwards: list[str] | None = None,
    ) -> ServerProfile:
        if not name.strip():
            raise ValueError("Server name is required")
        profile = ServerProfile(
            id=server_id or f"srv_{uuid.uuid4().hex[:10]}", name=name.strip(), host=host.strip(),
            port=int(port), username=username.strip() if username else None,
            identity_file=str(Path(identity_file).expanduser()) if identity_file else None,
            remote_forwards=list(remote_forwards or []),
            created_at=now(), updated_at=now(),
        )
        existing = self.storage.get_server(profile.id)
        if existing:
            profile.created_at = existing.created_at
        validate_profile(profile)
        self.storage.put_server(profile)
        return profile

    def import_ssh_config(self, path: str | Path) -> list[ServerProfile]:
        profiles = []
        for item in parse_ssh_config(path):
            profiles.append(self.save_server(
                server_id=None, name=str(item["name"]), host=str(item["host"]),
                port=int(item["port"]), username=item.get("username"),
                identity_file=item.get("identity_file"),
                remote_forwards=list(item.get("remote_forwards", [])),
            ))
        return profiles

    def test_connection(self, server_id: str) -> ServerSnapshot:
        profile = self._server(server_id)
        try:
            snapshot = self.collect(profile)
        except ServerMonitorError as exc:
            profile.last_test_at, profile.last_test_ok, profile.last_error = now(), False, str(exc)
            profile.updated_at = now()
            self.storage.put_server(profile)
            raise
        profile.last_test_at, profile.last_test_ok, profile.last_error = now(), True, snapshot.error
        profile.updated_at = now()
        self.storage.put_server(profile)
        self.storage.put_snapshot(snapshot)
        return snapshot

    def refresh_server(self, server_id: str) -> ServerSnapshot:
        profile = self._server(server_id)
        snapshot = self.collect(profile)
        self.storage.put_snapshot(snapshot)
        return snapshot

    def start_watch(self, server_id: str, interval_seconds: float = 2.0) -> ServerProfile:
        if interval_seconds < 1.0:
            raise ValueError("Live sampling interval must be at least 1 second")
        profile = self._server(server_id)
        snapshot = self.collect(profile)
        self.storage.put_snapshot(snapshot)
        profile.watch_status = "RUNNING"
        profile.watch_interval = float(interval_seconds)
        profile.last_error = snapshot.error
        profile.updated_at = now()
        self.storage.put_server(profile)
        ensure_daemon(self.root, interval=profile.watch_interval)
        return profile

    def stop_watch(self, server_id: str) -> ServerProfile:
        profile = self._server(server_id)
        profile.watch_status = "OFF"
        profile.updated_at = now()
        self.storage.put_server(profile)
        return profile

    def refresh_watch(self, server_id: str) -> None:
        profile = self._server(server_id)
        try:
            snapshot = self.collect(profile)
            self.storage.put_snapshot(snapshot)
            profile.last_error = snapshot.error
        except ServerMonitorError as exc:
            profile.last_error = str(exc)
        profile.updated_at = now()
        self.storage.put_server(profile)

    def delete_server(self, server_id: str) -> ServerProfile:
        profile = self._server(server_id)
        active = [item for item in self.storage.list_monitors(active_only=True) if item.server_id == server_id]
        if active:
            raise ValueError("Stop active monitors before deleting this server configuration")
        self.storage.delete_server(server_id)
        return profile

    def collect(self, profile: ServerProfile) -> ServerSnapshot:
        result = self.probe.run(profile, _PROBE_SCRIPT)
        return parse_probe(profile.id, result.stdout)

    def start_monitor(
        self, *, server_id: str, pid: int | None = None, command_filter: str | None = None,
        user_filter: str | None = None, stdout_path: str | None = None, stderr_path: str | None = None,
        interval_seconds: float = 5.0,
    ) -> ProcessMonitor:
        if pid is None and not command_filter and not user_filter:
            raise ValueError("Provide a PID, command filter, or user filter")
        if pid is not None and pid <= 0:
            raise ValueError("PID must be a positive integer")
        if interval_seconds < 0.5:
            raise ValueError("Polling interval must be at least 0.5 seconds")
        profile = self._server(server_id)
        active = [item for item in self.storage.list_monitors(active_only=True) if item.server_id == server_id]
        if any(
            item.pid == pid
            and item.command_filter == command_filter
            and item.user_filter == user_filter
            for item in active
        ):
            raise ValueError("This task is already being monitored")
        snapshot = self.collect(profile)
        self.storage.put_snapshot(snapshot)
        targets = matching_processes(snapshot.processes, pid, command_filter, user_filter)
        if not targets:
            selector = f"PID {pid}" if pid is not None else "the supplied process filter"
            raise ValueError(f"No matching process found for {selector}")
        monitor_id = f"mon_{uuid.uuid4().hex[:10]}"
        monitor = ProcessMonitor(
            id=monitor_id, server_id=server_id, pid=pid,
            command_filter=command_filter, user_filter=user_filter,
            stdout_path=stdout_path, stderr_path=stderr_path,
            interval_seconds=float(interval_seconds), status="RUNNING", created_at=now(),
            started_at=now(), last_seen_at=now(), summary=self._summary(snapshot, targets),
            log_path=str(self.root / "monitor_logs" / f"{monitor_id}.log"),
        )
        self.storage.put_monitor(monitor)
        ensure_daemon(self.root, interval=monitor.interval_seconds)
        self._write_log(monitor, f"started {monitor.started_at}; target_count={len(targets)}")
        return monitor

    def refresh_monitor(self, monitor_id: str) -> ProcessMonitor:
        monitor = self._monitor(monitor_id)
        if monitor.status != "RUNNING":
            return monitor
        profile = self._server(monitor.server_id)
        try:
            snapshot = self.collect(profile)
            self.storage.put_snapshot(snapshot)
        except ServerMonitorError as exc:
            monitor.last_error = str(exc)
            self.storage.put_monitor(monitor)
            self._write_log(monitor, f"poll failed: {exc}")
            return monitor
        targets = matching_processes(snapshot.processes, monitor.pid, monitor.command_filter, monitor.user_filter)
        if targets:
            monitor.last_seen_at = now()
            monitor.summary = self._summary(snapshot, targets)
        else:
            monitor.status = "COMPLETED"
            monitor.ended_at = now()
            monitor.summary["completed_at"] = monitor.ended_at
            monitor.summary["final_gpu_summary"] = [item.to_dict() for item in snapshot.gpus]
            monitor.summary["stdout_tail"] = self._tail(profile, monitor.stdout_path)
            monitor.summary["stderr_tail"] = self._tail(profile, monitor.stderr_path)
            monitor.last_error = None
            self._write_log(monitor, f"completed {monitor.ended_at}; target process ended")
            try:
                self.notifier.notify_completed(monitor, profile)
            except (FeishuNotificationError, WebhookNotificationError) as exc:
                # Completion must remain recorded even if an optional notification fails.
                self._write_log(monitor, f"Connector notification failed: {exc}")
        self.storage.put_monitor(monitor)
        return monitor

    def stop_monitor(self, monitor_id: str) -> ProcessMonitor:
        monitor = self._monitor(monitor_id)
        if monitor.status == "RUNNING":
            monitor.status, monitor.ended_at = "CANCELLED", now()
            self._write_log(monitor, f"cancelled {monitor.ended_at}")
            self.storage.put_monitor(monitor)
        return monitor

    def _tail(self, profile: ServerProfile, path: str | None) -> str:
        if not path:
            return ""
        script = f"tail -c 4000 -- {shlex.quote(path)} 2>/dev/null || true\n"
        try:
            return self.probe.run(profile, script).stdout[-4000:]
        except ServerMonitorError:
            return ""

    def _summary(self, snapshot: ServerSnapshot, targets: list[ProcessSnapshot]) -> dict:
        return {
            "hostname": snapshot.hostname, "target_processes": [item.to_dict() for item in targets],
            "gpu_summary": [item.to_dict() for item in snapshot.gpus], "observed_at": snapshot.fetched_at,
        }

    def _server(self, server_id: str) -> ServerProfile:
        item = self.storage.get_server(server_id)
        if not item:
            raise KeyError(f"Unknown server: {server_id}")
        return item

    def _monitor(self, monitor_id: str) -> ProcessMonitor:
        item = self.storage.get_monitor(monitor_id)
        if not item:
            raise KeyError(f"Unknown monitor: {monitor_id}")
        return item

    def _write_log(self, monitor: ProcessMonitor, message: str) -> None:
        if not monitor.log_path:
            return
        path = Path(monitor.log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{now()} {message}\n")


def matching_processes(
    processes: list[ProcessSnapshot], pid: int | None, command_filter: str | None, user_filter: str | None,
) -> list[ProcessSnapshot]:
    return [
        item for item in processes
        if (pid is None or item.pid == pid)
        and (not command_filter or command_filter.lower() in item.command.lower())
        and (not user_filter or item.user == user_filter)
    ]


def parse_probe(server_id: str, output: str) -> ServerSnapshot:
    hostname = ""
    system = ""
    gpus: list[GPUSnapshot] = []
    processes: list[ProcessSnapshot] = []
    gpu_processes: dict[int, tuple[str | None, float | None, str | None]] = {}
    no_nvidia = False
    for line in output.splitlines():
        if line.startswith("RR_HOST\t"):
            hostname = line.split("\t", 1)[1]
        elif line.startswith("RR_SYSTEM\t"):
            system = line.split("\t", 1)[1]
        elif line.startswith("RR_NO_NVIDIA"):
            no_nvidia = True
        elif line.startswith("RR_GPU\t"):
            values = _csv_line(line.split("\t", 1)[1])
            if len(values) >= 7:
                gpus.append(GPUSnapshot(values[0], values[1], _number(values[2]), _number(values[3]), _number(values[4]), _number(values[5]), _number(values[6]), values[7] if len(values) > 7 else None))
        elif line.startswith("RR_GPUPROC\t"):
            values = _csv_line(line.split("\t", 1)[1])
            if values and _integer(values[0]) is not None:
                gpu_processes[_integer(values[0])] = (values[3] if len(values) > 3 else None, _number(values[2]) if len(values) > 2 else None, values[1] if len(values) > 1 else None)
        elif line.startswith("RR_PS\t"):
            values = line.split("\t", 5)
            if len(values) == 6 and values[0] == "RR_PS":
                process_pid = _integer(values[1])
                if process_pid is not None:
                    gpu_index, gpu_memory, _gpu_process_name = gpu_processes.get(process_pid, (None, None, None))
                    gpu_index = next((gpu.index for gpu in gpus if gpu.uuid == gpu_index), gpu_index)
                    processes.append(ProcessSnapshot(process_pid, values[2], values[3], _integer(values[4]), values[5], gpu_index, gpu_memory))
    gpu_process_list = [item for item in processes if item.pid in gpu_processes]
    known_pids = {item.pid for item in gpu_process_list}
    for process_pid, (gpu_index, gpu_memory, process_name) in gpu_processes.items():
        if process_pid not in known_pids:
            gpu_index = next((gpu.index for gpu in gpus if gpu.uuid == gpu_index), gpu_index)
            gpu_process_list.append(ProcessSnapshot(process_pid, "?", "?", None, process_name or "", gpu_index, gpu_memory))
    return ServerSnapshot(server_id, now(), hostname, system, gpus, processes, "nvidia-smi not found; NVIDIA GPU metrics unavailable" if no_nvidia else None, gpu_process_list)


_PROBE_SCRIPT = r'''set +e
printf 'RR_HOST\t'; hostname 2>/dev/null
printf 'RR_SYSTEM\t'; uname -sr 2>/dev/null
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw,uuid --format=csv,noheader,nounits 2>/dev/null | while IFS= read -r line; do printf 'RR_GPU\t%s\n' "$line"; done
  nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid --format=csv,noheader,nounits 2>/dev/null | while IFS= read -r line; do printf 'RR_GPUPROC\t%s\n' "$line"; done
else
  echo RR_NO_NVIDIA
fi
ps -eo pid=,user=,stat=,etimes=,args= 2>/dev/null | while read -r pid user stat elapsed args; do printf 'RR_PS\t%s\t%s\t%s\t%s\t%s\n' "$pid" "$user" "$stat" "$elapsed" "$args"; done
'''


def parse_ssh_config(path: str | Path) -> list[dict[str, object]]:
    """Parse importable Host blocks without storing the source or key contents."""
    config_path = Path(path).expanduser()
    if not config_path.is_file():
        raise ValueError(f"SSH config file not found: {config_path}")
    if config_path.stat().st_size > 1_000_000:
        raise ValueError("SSH config file is larger than 1 MiB")
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("SSH config must be UTF-8 text") from exc

    imported: list[dict[str, object]] = []
    aliases: list[str] = []
    values: dict[str, object] = {}

    def flush() -> None:
        if not aliases or any(any(mark in alias for mark in "*?!") for alias in aliases):
            return
        host = str(values.get("hostname") or aliases[0])
        imported.append({
            "name": aliases[0], "host": host, "port": int(values.get("port") or 22),
            "username": values.get("user"), "identity_file": values.get("identityfile"),
            "remote_forwards": list(values.get("remoteforward", [])), "aliases": aliases,
        })

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(" ")
        if not separator:
            key, separator, value = line.partition("\t")
        if not separator:
            continue
        key, value = key.lower(), value.strip()
        if key == "host":
            flush()
            aliases = shlex.split(value) if value else []
            values = {}
        elif aliases:
            if key in {"hostname", "user", "port", "identityfile"}:
                values.setdefault(key, value)
            elif key == "remoteforward":
                values.setdefault(key, [])
                values[key].append(value)
    flush()
    return imported
