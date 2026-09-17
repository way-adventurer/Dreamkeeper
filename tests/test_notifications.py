from pathlib import Path

from runrelay.models import ProcessMonitor, ServerProfile
from runrelay.notifications import FeishuCliNotifier, _FeishuEventHandler


def test_feishu_connector_sends_completed_monitor_message(tmp_path: Path):
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return __import__("subprocess").CompletedProcess(args, 0, '{"ok":true}', "")

    cli = tmp_path / "lark-cli.cmd"
    cli.write_text("@echo off", encoding="utf-8")
    notifier = FeishuCliNotifier(tmp_path, runner=runner)
    notifier.save_config({
        "enabled": True,
        "cli_path": str(cli),
        "identity": "bot",
        "target_type": "user_id",
        "target_id": "ou_test",
    })
    monitor = ProcessMonitor(
        id="mon_test", server_id="srv_test", pid=4321, status="COMPLETED",
        ended_at="2026-09-17T08:00:00+00:00",
        summary={"target_processes": [{"command": "python train.py"}], "final_gpu_summary": [{"index": "0"}]},
    )
    profile = ServerProfile(id="srv_test", name="gpu-134", host="192.0.2.134")

    result = notifier.notify_completed(monitor, profile)

    assert result["ok"] is True
    args = calls[0][0]
    assert args[:5] == [str(cli), "im", "+messages-send", "--as", "bot"]
    assert "--user-id" in args and "ou_test" in args
    assert "守梦任务已完成" in args[args.index("--text") + 1]


def test_disabled_feishu_connector_does_not_send(tmp_path: Path):
    calls = []
    notifier = FeishuCliNotifier(tmp_path, runner=lambda *args, **kwargs: calls.append(args))
    monitor = ProcessMonitor(id="mon_test", server_id="srv_test", pid=1, status="COMPLETED")
    profile = ServerProfile(id="srv_test", name="server", host="host")

    assert notifier.notify_completed(monitor, profile) is None
    assert calls == []


def test_feishu_connector_can_discover_current_user(tmp_path: Path):
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        if args[1:3] == ["auth", "status"]:
            return __import__("subprocess").CompletedProcess(args, 0, '{"identities":{"user":{"openId":"ou_current"}}}', "")
        return __import__("subprocess").CompletedProcess(args, 0, '{"ok":true}', "")

    cli = tmp_path / "lark-cli.cmd"
    cli.write_text("@echo off", encoding="utf-8")
    notifier = FeishuCliNotifier(tmp_path, runner=runner)
    notifier.save_config({"enabled": True, "cli_path": str(cli), "identity": "bot", "target_type": "user_id"})
    monitor = ProcessMonitor(id="mon_test", server_id="srv_test", pid=1, status="COMPLETED")
    profile = ServerProfile(id="srv_test", name="server", host="host")

    notifier.notify_completed(monitor, profile)

    assert "ou_current" in calls[-1]


def test_native_feishu_connector_discovers_chat_and_hides_secret(tmp_path: Path):
    notifier = FeishuCliNotifier(tmp_path)
    notifier.save_config({
        "enabled": True,
        "transport": "long_connection",
        "bot_name": "守梦",
        "app_id": "cli_example_app",
        "app_secret": "example-secret",
    })

    notifier.long_connection.handle_payload(
        b'{"event":{"message":{"chat_id":"oc_test_chat","chat_type":"p2p","content":"{\\"text\\":\\"hello\\"}"}}}'
    )

    public = notifier.public_config()
    assert public["app_secret_set"] is True
    assert "app_secret" not in public
    assert public["discovered_chat_id"] == "oc_test_chat"
    assert public["runtime"]["last_message_preview"] == "hello"


def test_native_feishu_event_handler_uses_current_sdk_callback_name(tmp_path: Path):
    notifier = FeishuCliNotifier(tmp_path)
    handler = _FeishuEventHandler(notifier.long_connection)

    handler._do_without_validation(
        b'{"event":{"message":{"chat_id":"oc_sdk_chat","chat_type":"p2p",'
        b'"content":"{\\"text\\":\\"hello from sdk\\"}"}}}'
    )

    assert notifier.public_config()["discovered_chat_id"] == "oc_sdk_chat"


def test_native_feishu_connector_sends_to_discovered_chat(tmp_path: Path):
    notifier = FeishuCliNotifier(tmp_path)
    notifier.save_config({
        "enabled": True,
        "transport": "long_connection",
        "app_id": "cli_example_app",
        "app_secret": "example-secret",
    })
    notifier.record_inbound_target("oc_test_chat", "direct", text="hello")
    requests = []

    def fake_post(url, body, *, headers=None):
        requests.append((url, body, headers))
        if "tenant_access_token" in url:
            return {"tenant_access_token": "example-tenant-token"}
        return {"code": 0, "msg": "success"}

    notifier._post_json = fake_post
    result = notifier.send_test()

    assert result["ok"] is True
    assert requests[0][1]["app_secret"] == "example-secret"
    assert requests[1][1]["receive_id"] == "oc_test_chat"
