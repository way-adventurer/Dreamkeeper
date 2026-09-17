from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def ensure_daemon(root: Path, interval: float = 5.0) -> int:
    """Start one detached local monitor unless a live monitor already exists."""
    root.mkdir(parents=True, exist_ok=True)
    pid_file = root / "daemon.pid"
    existing = _read_pid(pid_file)
    if existing and _pid_alive(existing):
        return existing
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)

    command = [
        sys.executable,
        "-m",
        "runrelay.cli",
        "--home",
        str(root),
        "daemon",
        "run",
        "--interval",
        str(interval),
    ]
    options: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": os.name != "nt",
    }
    if os.name == "nt":
        options["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(command, **options)
    return process.pid


def write_daemon_pid(root: Path) -> Path:
    pid_file = root / "daemon.pid"
    pid_file.write_text(str(os.getpid()), encoding="ascii")
    return pid_file


def remove_daemon_pid(pid_file: Path) -> None:
    try:
        if pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
            pid_file.unlink(missing_ok=True)
    except FileNotFoundError:
        pass


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (FileNotFoundError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
