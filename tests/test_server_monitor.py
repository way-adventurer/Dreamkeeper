import subprocess

from runrelay.models import ServerProfile
from runrelay.server_monitor import SSHProbe, ServerMonitorService, parse_probe, parse_ssh_config
from runrelay.storage import Storage


PROBE_WITH_PROCESS = """RR_HOST\tfake-gpu\nRR_SYSTEM\tLinux 6.8\nRR_GPU\t0, NVIDIA A100, 40960, 100, 25, 60, 250\nRR_GPUPROC\t4321, python, 100, GPU-UUID\nRR_PS\t4321\talice\tSl\t12\tpython train.py --epochs 1\n"""
PROBE_EMPTY = """RR_HOST\tfake-gpu\nRR_SYSTEM\tLinux 6.8\nRR_GPU\t0, NVIDIA A100, 40960, 0, 0, 41, 50\n"""


def test_parse_probe_extracts_gpu_and_process_fields():
    snapshot = parse_probe("srv_test", PROBE_WITH_PROCESS)
    assert snapshot.hostname == "fake-gpu"
    assert snapshot.gpus[0].name == "NVIDIA A100"
    assert snapshot.gpus[0].memory_total_mib == 40960
    assert snapshot.processes[0].pid == 4321
    assert snapshot.processes[0].gpu_index == "GPU-UUID"
    assert len(snapshot.gpu_processes) == 1
    assert snapshot.gpu_processes[0].pid == 4321


def test_simulated_monitor_persists_and_detects_process_end(tmp_path, monkeypatch):
    outputs = iter([PROBE_WITH_PROCESS, PROBE_EMPTY])
    calls = []

    def fake_runner(args, **kwargs):
        calls.append((args, kwargs["input"]))
        return subprocess.CompletedProcess(args, 0, next(outputs), "")

    storage = Storage(tmp_path)
    service = ServerMonitorService(tmp_path, storage, SSHProbe(fake_runner))
    profile = service.save_server(
        server_id=None, name="Fake GPU", host="gpu-test", port=2222,
        username="alice", identity_file="~/.ssh/id_ed25519",
    )
    monkeypatch.setattr("runrelay.server_monitor.ensure_daemon", lambda root, interval: 2468)

    monitor = service.start_monitor(server_id=profile.id, pid=4321, interval_seconds=1)
    assert monitor.status == "RUNNING"
    assert storage.get_server(profile.id).identity_file.endswith(".ssh\\id_ed25519") or storage.get_server(profile.id).identity_file.endswith(".ssh/id_ed25519")
    assert b"PRIVATE KEY" not in calls[0][1]
    assert calls[0][0][0] == "ssh"
    assert "-i" in calls[0][0] and "--" in calls[0][0]

    completed = service.refresh_monitor(monitor.id)
    assert completed.status == "COMPLETED"
    assert completed.ended_at
    assert completed.summary["target_processes"][0]["pid"] == 4321
    assert "identity_file" not in completed.summary
    assert storage.get_snapshot(profile.id).hostname == "fake-gpu"


def test_duplicate_active_pid_monitor_is_rejected(tmp_path, monkeypatch):
    calls = []

    def fake_runner(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, PROBE_WITH_PROCESS, "")

    storage = Storage(tmp_path)
    service = ServerMonitorService(tmp_path, storage, SSHProbe(fake_runner))
    profile = service.save_server(server_id=None, name="Fake GPU", host="gpu-test")
    monkeypatch.setattr("runrelay.server_monitor.ensure_daemon", lambda root, interval: 2468)
    service.start_monitor(server_id=profile.id, pid=4321, interval_seconds=1)
    try:
        service.start_monitor(server_id=profile.id, pid=4321, interval_seconds=1)
    except ValueError as exc:
        assert "already" in str(exc).lower()
    else:
        raise AssertionError("expected duplicate monitor rejection")
    assert len(calls) == 1


def test_refresh_watch_samples_profiles_without_pause_state(tmp_path):
    def fake_runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, PROBE_EMPTY.replace("fake-gpu", "always-sampled"), "")

    storage = Storage(tmp_path)
    service = ServerMonitorService(tmp_path, storage, SSHProbe(fake_runner))
    profile = service.save_server(server_id=None, name="Always sampled", host="gpu-test")
    service.refresh_watch(profile.id)
    assert storage.get_snapshot(profile.id).hostname == "always-sampled"


def test_simulated_connection_failure_is_saved_on_profile(tmp_path):
    def failed_runner(*_args, **_kwargs):
        return subprocess.CompletedProcess(["ssh"], 255, "", "Permission denied")

    storage = Storage(tmp_path)
    service = ServerMonitorService(tmp_path, storage, SSHProbe(failed_runner))
    profile = service.save_server(server_id=None, name="Broken", host="missing")
    try:
        service.test_connection(profile.id)
    except RuntimeError as exc:
        assert "permission denied" in str(exc).lower()
    else:
        raise AssertionError("expected connection failure")
    saved = storage.get_server(profile.id)
    assert saved.last_test_ok is False
    assert "permission denied" in (saved.last_error or "").lower()


def test_import_ssh_config_parses_vscode_remote_ssh_fields(tmp_path):
    config = tmp_path / "config"
    config.write_text(
        """Host gpu-134\n  HostName 192.0.2.134\n  User researcher\n  Port 22\n  RemoteForward 7897 127.0.0.1:7897\n\nHost *\n  ServerAliveInterval 30\n""",
        encoding="utf-8",
    )
    items = parse_ssh_config(config)
    assert items == [{
        "name": "gpu-134", "host": "192.0.2.134", "port": 22,
        "username": "researcher", "identity_file": None,
        "remote_forwards": ["7897 127.0.0.1:7897"], "aliases": ["gpu-134"],
    }]

    storage = Storage(tmp_path / "state")
    service = ServerMonitorService(tmp_path / "state", storage)
    imported = service.import_ssh_config(config)
    assert imported[0].name == "gpu-134"
    assert imported[0].host == "192.0.2.134"
    assert imported[0].remote_forwards == ["7897 127.0.0.1:7897"]


def test_ssh_probe_normalizes_windows_newlines_before_remote_bash():
    seen = {}

    def fake_runner(_args, **kwargs):
        seen["script"] = kwargs["input"]
        return subprocess.CompletedProcess(["ssh"], 0, "", "")

    profile = ServerProfile("srv", "Test", "gpu-test")
    SSHProbe(fake_runner).run(profile, "set +e\r\nprintf ok\r\n")
    assert b"\r" not in seen["script"]


def test_ssh_probe_hides_console_window_on_windows(monkeypatch):
    seen = {}

    def fake_runner(_args, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(["ssh"], 0, "", "")

    monkeypatch.setattr("runrelay.server_monitor.os.name", "nt")
    profile = ServerProfile("srv", "Test", "gpu-test")
    SSHProbe(fake_runner).run(profile, "printf ok\n")

    assert "creationflags" in seen
    assert seen["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_delete_server_removes_saved_configuration(tmp_path):
    storage = Storage(tmp_path)
    service = ServerMonitorService(tmp_path, storage)
    profile = service.save_server(server_id=None, name="To remove", host="gpu-test")
    assert service.delete_server(profile.id).id == profile.id
    assert storage.get_server(profile.id) is None
