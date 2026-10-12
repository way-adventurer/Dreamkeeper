import subprocess

import pytest

from runrelay.server_monitor import SSHProbe, ServerMonitorService
from runrelay.storage import Storage


def probe_output(*pids: int) -> str:
    lines = ["RR_HOST\ttest-gpu", "RR_SYSTEM\tLinux 6.8"]
    lines.extend(f"RR_PS\t{pid}\tresearcher\tSl\t1\tpython train.py --rank {index}" for index, pid in enumerate(pids))
    return "\n".join(lines) + "\n"


class RecordingNotifier:
    def __init__(self):
        self.individual = []
        self.groups = []

    def notify_completed(self, monitor, profile):
        self.individual.append(monitor.id)

    def notify_group_completed(self, group, monitors, profiles):
        self.groups.append((group.id, [monitor.id for monitor in monitors]))
        return {"ok": True}


def make_service(tmp_path, monkeypatch, snapshots):
    outputs = iter(snapshots)

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, next(outputs), "")

    storage = Storage(tmp_path)
    notifier = RecordingNotifier()
    service = ServerMonitorService(tmp_path, storage, SSHProbe(runner), notifier)
    monkeypatch.setattr("runrelay.server_monitor.ensure_daemon", lambda *_args, **_kwargs: 1)
    profile = service.save_server(server_id=None, name="Test GPU", host="gpu.example.test")
    return service, storage, notifier, profile


def test_group_waits_for_every_process_and_notifies_once(tmp_path, monkeypatch):
    service, storage, notifier, profile = make_service(
        tmp_path, monkeypatch,
        [probe_output(101, 202), probe_output(101, 202), probe_output(202), probe_output()],
    )
    first = service.start_monitor(server_id=profile.id, pid=101)
    second = service.start_monitor(server_id=profile.id, pid=202)
    group = service.create_watch_group("双卡训练")
    service.add_monitor_to_group(group.id, first.id)
    service.add_monitor_to_group(group.id, second.id)
    service.rename_monitor(first.id, "GPU 0")
    assert storage.get_monitor(first.id).name == "GPU 0"
    assert storage.get_watch_group(group.id).status == "DRAFT"
    service.start_watch_group(group.id)

    assert service.refresh_monitor(first.id).status == "COMPLETED"
    assert storage.get_watch_group(group.id).status == "RUNNING"
    assert notifier.individual == []
    assert notifier.groups == []

    assert service.refresh_monitor(second.id).status == "COMPLETED"
    saved = Storage(tmp_path).get_watch_group(group.id)
    assert saved.status == "COMPLETED"
    assert saved.notification_status == "SENT"
    assert len(notifier.groups) == 1
    assert set(notifier.groups[0][1]) == {first.id, second.id}
    service.refresh_monitor(first.id)
    assert len(notifier.groups) == 1


def test_draft_requires_two_processes_and_cancelled_member_prevents_success(tmp_path, monkeypatch):
    service, storage, notifier, profile = make_service(
        tmp_path, monkeypatch, [probe_output(101, 202), probe_output(101, 202), probe_output()],
    )
    first = service.start_monitor(server_id=profile.id, pid=101)
    second = service.start_monitor(server_id=profile.id, pid=202)
    group = service.create_watch_group()
    service.add_monitor_to_group(group.id, first.id)
    with pytest.raises(ValueError, match="两个进程"):
        service.start_watch_group(group.id)
    service.add_monitor_to_group(group.id, second.id)
    service.start_watch_group(group.id)
    service.stop_monitor(first.id)
    assert storage.get_watch_group(group.id).status == "RUNNING"
    service.refresh_monitor(second.id)
    assert storage.get_watch_group(group.id).status == "CANCELLED"
    assert notifier.individual == []
    assert notifier.groups == []
