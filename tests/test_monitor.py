from pathlib import Path
import os
import sys

from runrelay.monitor import ensure_daemon


def test_ensure_daemon_reuses_live_pid(tmp_path: Path, monkeypatch):
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("123", encoding="ascii")
    monkeypatch.setattr("runrelay.monitor._pid_alive", lambda pid: pid == 123)
    assert ensure_daemon(tmp_path) == 123


def test_submit_records_monitor_start(tmp_path: Path, monkeypatch):
    from runrelay.service import RunRelayService

    monkeypatch.setattr("runrelay.service.ensure_daemon", lambda root: 456)
    service = RunRelayService(tmp_path)
    item = service.submit(host="local", workdir=str(tmp_path), command="echo ok")
    assert item.monitor_pid == 456
    assert item.monitor_status == "RUNNING"


def test_monitor_reconciles_completed_local_job(tmp_path: Path):
    from runrelay.service import RunRelayService

    service = RunRelayService(tmp_path)
    item = service.submit(
        host="local",
        workdir=str(tmp_path),
        command=f'"{sys.executable}" -c "print(987)"',
        wake_backend="noop",
    )
    try:
        completed = service.wait(item.id, interval=0.1, timeout=10)
        assert completed.status.value == "COMPLETED"
        assert completed.exit_code == 0
    finally:
        if item.monitor_pid:
            if os.name == "nt":
                import subprocess

                subprocess.run(
                    ["taskkill", "/PID", str(item.monitor_pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                os.kill(item.monitor_pid, 15)
