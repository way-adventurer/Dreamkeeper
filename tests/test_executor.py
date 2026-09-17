import base64
import subprocess

from runrelay.executor import SSHExecutor
from runrelay.models import Experiment, Status


def _experiment():
    return Experiment(
        id="exp_remote",
        host="gpu-test",
        workdir="/home/user/project",
        command="echo remote hello",
        local_dir=".",
    )


def test_ssh_submit_bootstraps_detached_runner(monkeypatch):
    executor = SSHExecutor()
    captured = {}

    def fake_ssh(experiment, script, *, check=True):
        captured["script"] = script
        return subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="12345\n",
            stderr="",
        )

    monkeypatch.setattr(executor, "_ssh", fake_ssh)
    pid, remote_dir = executor.submit(_experiment())
    assert pid == 12345
    assert remote_dir.endswith("/exp_remote")
    assert "nohup" in captured["script"]
    assert "runner.sh" in captured["script"]
    assert base64.b64encode(b"echo remote hello").decode() in captured["script"]


def test_ssh_disconnect_keeps_job_reconcilable(monkeypatch):
    executor = SSHExecutor()

    def fake_ssh(experiment, script, *, check=True):
        return subprocess.CompletedProcess(
            args=["ssh"],
            returncode=255,
            stdout="",
            stderr="Connection timed out",
        )

    monkeypatch.setattr(executor, "_ssh", fake_ssh)
    experiment = _experiment()
    experiment.pid = 12345
    state = executor.status(experiment)
    assert state.status is Status.RUNNING
    assert "timed out" in (state.detail or "")

