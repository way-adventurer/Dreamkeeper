import sys

from runrelay.models import Status
from runrelay.service import RunRelayService


def test_local_submit_wait_and_logs(tmp_path):
    service = RunRelayService(tmp_path, auto_monitor=False)
    command = f'"{sys.executable}" -c "print(123)"'
    item = service.submit(
        host="local",
        workdir=str(tmp_path),
        command=command,
    )
    completed = service.wait(item.id, interval=0.1, timeout=10)
    assert completed.status is Status.COMPLETED
    assert completed.exit_code == 0
    stdout, stderr = service.logs(item.id)
    assert "123" in stdout
    assert stderr == ""


def test_file_wake(tmp_path):
    service = RunRelayService(tmp_path, auto_monitor=False)
    command = f'"{sys.executable}" -c "print(456)"'
    item = service.submit(
        host="local",
        workdir=str(tmp_path),
        command=command,
        wake_backend="file",
    )
    completed = service.wait(item.id, interval=0.1, timeout=10)
    assert completed.wake_status == "SENT"
    assert (tmp_path / "experiments" / item.id / "wake.json").exists()


def test_auto_wake_captures_codex_thread(monkeypatch, tmp_path):
    service = RunRelayService(tmp_path, auto_monitor=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-test")
    item = service.submit(
        host="local",
        workdir=str(tmp_path),
        command="echo 789",
        wake_backend="auto",
    )
    assert item.wake_backend == "codex-cli"
    assert item.session_id == "thread-test"
