from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import ProcessMonitor, ServerProfile


class FeishuNotificationError(RuntimeError):
    pass


class WebhookNotificationError(RuntimeError):
    pass


@dataclass
class WebhookConfig:
    """A small, provider-neutral outbound connector.

    It intentionally speaks ordinary JSON so the same connector works with
    Slack/Discord/Teams/n8n/Make and a user's own tiny HTTP endpoint.
    """

    enabled: bool = False
    url: str = ""
    secret: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, object] | None) -> "WebhookConfig":
        value = value or {}
        return cls(bool(value.get("enabled", False)), str(value.get("url", "") or "").strip(), str(value.get("secret", "") or "").strip())

    def validate(self) -> None:
        if self.enabled and not self.url.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must use http:// or https://")


@dataclass
class FeishuConfig:
    enabled: bool = False
    transport: str = "long_connection"
    bot_name: str = "守梦"
    app_id: str = ""
    app_secret: str = ""
    app_secret_env: str = ""
    api_base_url: str = "https://open.feishu.cn"
    discovered_chat_id: str = ""
    discovered_chat_type: str = "direct"
    # Legacy lark-cli fields remain readable for existing local configurations.
    cli_path: str = ""
    identity: str = "bot"
    target_type: str = "user_id"
    target_id: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, object] | None) -> "FeishuConfig":
        value = value or {}
        return cls(
            enabled=bool(value.get("enabled", False)),
            transport=str(value.get("transport", "long_connection") or "long_connection").strip().lower(),
            bot_name=str(value.get("bot_name", "守梦") or "守梦").strip(),
            app_id=str(value.get("app_id", "") or "").strip(),
            app_secret=str(value.get("app_secret", "") or "").strip(),
            app_secret_env=str(value.get("app_secret_env", "") or "").strip(),
            api_base_url=str(value.get("api_base_url", "https://open.feishu.cn") or "https://open.feishu.cn").strip().rstrip("/"),
            discovered_chat_id=str(value.get("discovered_chat_id", "") or "").strip(),
            discovered_chat_type=str(value.get("discovered_chat_type", "direct") or "direct").strip().lower(),
            cli_path=str(value.get("cli_path", "") or "").strip(),
            identity=str(value.get("identity", "bot") or "bot").strip().lower(),
            target_type=str(value.get("target_type", "user_id") or "user_id").strip().lower(),
            target_id=str(value.get("target_id", "") or "").strip(),
        )

    def validate(self) -> None:
        if self.transport not in {"long_connection", "cli"}:
            raise ValueError("Feishu transport must be long_connection or cli")
        if not self.api_base_url.startswith(("http://", "https://")):
            raise ValueError("Feishu API base URL must use http:// or https://")
        if self.identity not in {"bot", "user"}:
            raise ValueError("Feishu identity must be bot or user")
        if self.target_type not in {"user_id", "chat_id"}:
            raise ValueError("Feishu target type must be user_id or chat_id")

    def secret(self) -> str:
        if self.app_secret:
            return self.app_secret
        return os.environ.get(self.app_secret_env, "").strip() if self.app_secret_env else ""

    def uses_native_connection(self) -> bool:
        return bool(self.app_id or self.app_secret or self.transport == "long_connection")

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "transport": self.transport,
            "bot_name": self.bot_name,
            "app_id": self.app_id,
            "app_secret": self.app_secret,
            "app_secret_env": self.app_secret_env,
            "api_base_url": self.api_base_url,
            "discovered_chat_id": self.discovered_chat_id,
            "discovered_chat_type": self.discovered_chat_type,
            "cli_path": self.cli_path,
            "identity": self.identity,
            "target_type": self.target_type,
            "target_id": self.target_id,
        }


class _ThreadLoopProxy:
    """Make lark-oapi's module-level asyncio loop safe for the local connector."""

    def __init__(self) -> None:
        self._loops: dict[int, asyncio.AbstractEventLoop] = {}

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loops[threading.get_ident()] = loop

    def _loop(self) -> asyncio.AbstractEventLoop:
        loop = self._loops.get(threading.get_ident())
        return loop or asyncio.get_event_loop()

    def create_task(self, coro: Any) -> asyncio.Task:
        return self._loop().create_task(coro)

    def run_until_complete(self, future: Any) -> Any:
        return self._loop().run_until_complete(future)


_feishu_loop_proxy = _ThreadLoopProxy()


class _FeishuEventHandler:
    def __init__(self, service: "FeishuLongConnection") -> None:
        self.service = service

    def _do_without_validation(self, payload: bytes) -> None:
        self.service.handle_payload(payload)

    # Keep compatibility with older lark-oapi releases.
    def do_without_validation(self, payload: bytes) -> None:
        self._do_without_validation(payload)


class FeishuLongConnection:
    """Inbound Feishu bridge following DeepScientist's long-connection flow."""

    def __init__(self, notifier: "FeishuNotifier") -> None:
        self.notifier = notifier
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_stop: asyncio.Event | None = None
        self._client: Any = None

    def start(self) -> bool:
        config = self.notifier.get_config()
        if not config.enabled or not config.uses_native_connection():
            self.notifier.write_runtime(enabled=config.enabled, connected=False, connection_state="disabled")
            return False
        if not config.app_id or not config.secret():
            self.notifier.write_runtime(enabled=True, connected=False, connection_state="needs_credentials", auth_state="missing_credentials")
            return False
        sdk = self._sdk_bundle()
        if sdk is None:
            self.notifier.write_runtime(enabled=True, connected=False, connection_state="needs_dependency", auth_state="missing_dependency")
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="dreamkeeper-feishu-long-connection")
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._loop is not None and self._async_stop is not None:
            self._loop.call_soon_threadsafe(self._async_stop.set)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._loop = None
        self._async_stop = None
        self._client = None

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def _run(self) -> None:
        sdk = self._sdk_bundle()
        if sdk is None:
            return
        client_cls, log_level = sdk
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        _feishu_loop_proxy.set_loop(loop)
        stop_signal = asyncio.Event()
        self._async_stop = stop_signal
        handler = _FeishuEventHandler(self)

        async def runner() -> None:
            backoff = 1.0
            self.notifier.write_runtime(enabled=True, connected=False, connection_state="starting", auth_state="ready")
            while not stop_signal.is_set():
                ping_task = None
                try:
                    config = self.notifier.get_config()
                    client = client_cls(
                        app_id=config.app_id,
                        app_secret=config.secret(),
                        log_level=log_level.INFO,
                        event_handler=handler,
                        domain=config.api_base_url,
                        auto_reconnect=False,
                    )
                    self._client = client
                    await client._connect()
                    ping_task = loop.create_task(client._ping_loop())
                    self.notifier.write_runtime(connected=True, connection_state="connected", auth_state="ready", last_error=None)
                    backoff = 1.0
                    while not stop_signal.is_set():
                        await asyncio.sleep(0.5)
                        if getattr(client, "_conn", None) is None:
                            raise ConnectionError("Feishu long connection closed")
                    break
                except Exception as exc:  # pragma: no cover - depends on remote SDK/network
                    if stop_signal.is_set():
                        break
                    self.notifier.write_runtime(connected=False, connection_state="error", auth_state="ready", last_error=str(exc))
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, 30.0)
                finally:
                    if ping_task is not None:
                        ping_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await ping_task
                    client = self._client
                    if client is not None and getattr(client, "_conn", None) is not None:
                        with contextlib.suppress(Exception):
                            await client._disconnect()
                    self._client = None
            self.notifier.write_runtime(connected=False, connection_state="stopped")

        try:
            loop.run_until_complete(runner())
        finally:
            loop.close()

    @staticmethod
    def _sdk_bundle() -> tuple[Any, Any] | None:
        try:
            client_module = import_module("lark_oapi.ws.client")
            enum_module = import_module("lark_oapi.core.enum")
        except ImportError:
            return None
        if not isinstance(client_module.loop, _ThreadLoopProxy):
            client_module.loop = _feishu_loop_proxy
        return getattr(client_module, "Client"), getattr(enum_module, "LogLevel")

    def handle_payload(self, payload: bytes) -> None:
        try:
            packet = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        event = packet.get("event") if isinstance(packet.get("event"), dict) else {}
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        chat_id = str(message.get("chat_id") or "").strip()
        if not chat_id:
            return
        chat_type = "direct" if str(message.get("chat_type") or "p2p").lower() == "p2p" else "group"
        content = message.get("content")
        text = ""
        if isinstance(content, str):
            with contextlib.suppress(json.JSONDecodeError):
                content = json.loads(content)
        if isinstance(content, dict):
            text = str(content.get("text") or "").strip()
        self.notifier.record_inbound_target(chat_id, chat_type, text=text)


class FeishuNotifier:
    """Native Feishu connector with a legacy lark-cli fallback."""

    def __init__(self, root: Path, runner: Callable[..., subprocess.CompletedProcess[str]] | None = None):
        self.root = root
        self.config_path = root / "feishu-connector.json"
        self.runtime_path = root / "feishu-runtime.json"
        self.webhook_config_path = root / "webhook-connector.json"
        self.runner = runner or subprocess.run
        self.long_connection = FeishuLongConnection(self)

    def get_config(self) -> FeishuConfig:
        config = FeishuConfig.from_dict(self._read_config())
        config.validate()
        return config

    def _read_config(self) -> dict[str, object]:
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            raise FeishuNotificationError(f"Cannot read Feishu connector configuration: {exc}") from exc
        if not isinstance(value, dict):
            raise FeishuNotificationError("Feishu connector configuration must be a JSON object")
        return value

    def save_config(self, value: dict[str, object]) -> FeishuConfig:
        current = self._read_config()
        merged = dict(current)
        merged.update(value)
        # The UI sends an empty secret when the existing secret should remain unchanged.
        if not str(value.get("app_secret") or "").strip() and current.get("app_secret"):
            merged["app_secret"] = current["app_secret"]
        config = FeishuConfig.from_dict(merged)
        config.validate()
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self._temporary_path(self.config_path)
        temporary.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.config_path)
        self.long_connection.restart()
        return config

    def public_config(self) -> dict[str, object]:
        config = self.get_config()
        runtime = self._read_runtime()
        return {
            "enabled": config.enabled,
            "transport": config.transport,
            "bot_name": config.bot_name,
            "app_id": config.app_id,
            "api_base_url": config.api_base_url,
            "app_secret_set": bool(config.secret()),
            "discovered_chat_id": config.discovered_chat_id or runtime.get("discovered_chat_id", ""),
            "discovered_chat_type": config.discovered_chat_type or runtime.get("discovered_chat_type", "direct"),
            "dependency_available": FeishuLongConnection._sdk_bundle() is not None,
            "runtime": runtime,
            "available": bool(runtime.get("connected")),
        }

    def start(self) -> bool:
        return self.long_connection.start()

    def stop(self) -> None:
        self.long_connection.stop()

    def send_test(self) -> dict[str, object]:
        config = self.get_config()
        if not config.enabled:
            raise FeishuNotificationError("请先启用飞书完成通知")
        return self._send(config, "守梦连接测试\n飞书连接器已准备好接收任务完成通知。", "test")

    def get_webhook_config(self) -> WebhookConfig:
        try:
            value = json.loads(self.webhook_config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            value = {}
        config = WebhookConfig.from_dict(value if isinstance(value, dict) else {})
        config.validate()
        return config

    def save_webhook_config(self, value: dict[str, object]) -> WebhookConfig:
        current = self.get_webhook_config()
        merged = {"enabled": current.enabled, "url": current.url, "secret": current.secret}
        merged.update(value)
        if not str(value.get("secret") or "").strip():
            merged["secret"] = current.secret
        config = WebhookConfig.from_dict(merged)
        config.validate()
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self._temporary_path(self.webhook_config_path)
        temporary.write_text(json.dumps({"enabled": config.enabled, "url": config.url, "secret": config.secret}, indent=2), encoding="utf-8")
        temporary.replace(self.webhook_config_path)
        return config

    def public_webhook_config(self) -> dict[str, object]:
        config = self.get_webhook_config()
        return {"enabled": config.enabled, "url": config.url, "secret_set": bool(config.secret)}

    def send_webhook_test(self) -> dict[str, object]:
        config = self.get_webhook_config()
        if not config.enabled:
            raise WebhookNotificationError("请先启用 Webhook 连接器")
        return self._send_webhook(config, {"event": "test", "text": "守梦连接测试\nWebhook 连接器已准备好接收任务完成通知。"})

    def notify_completed(self, monitor: ProcessMonitor, profile: ServerProfile) -> dict[str, object] | None:
        config = self.get_config()
        webhook = self.get_webhook_config()
        if not config.enabled and not webhook.enabled:
            return None
        process = monitor.summary.get("target_processes", [{}])[0] if monitor.summary else {}
        command = str(process.get("command") or f"PID {monitor.pid or '—'}")
        gpu_count = len(monitor.summary.get("final_gpu_summary", []))
        text = (
            "守梦任务已完成\n"
            f"梦境：{profile.name} ({profile.host})\n"
            f"PID：{monitor.pid or '—'}\n"
            f"命令：{command}\n"
            f"结束时间：{monitor.ended_at or '—'}\n"
            f"GPU：{gpu_count} 张"
        )
        result = self._send(config, text, monitor.id) if config.enabled else None
        if webhook.enabled:
            result = {"feishu": result, "webhook": self._send_webhook(webhook, {"event": "completed", "text": text, "monitor_id": monitor.id, "server": profile.name})}
        return result

    def _send_webhook(self, config: WebhookConfig, payload: dict[str, object]) -> dict[str, object]:
        request = Request(config.url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json; charset=utf-8")
        if config.secret:
            request.add_header("Authorization", f"Bearer {config.secret}")
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310
                status = getattr(response, "status", 200)
                response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise WebhookNotificationError(f"Webhook request failed: {exc}") from exc
        return {"ok": True, "transport": "webhook", "status": status}

    def record_inbound_target(self, chat_id: str, chat_type: str, *, text: str = "") -> None:
        config = self.get_config()
        config.discovered_chat_id = chat_id
        config.discovered_chat_type = chat_type
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self._temporary_path(self.config_path)
        temporary.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.config_path)
        self.write_runtime(
            connected=True,
            connection_state="connected",
            auth_state="ready",
            discovered_chat_id=chat_id,
            discovered_chat_type=chat_type,
            last_event_at=_utc_now(),
            last_message_preview=text[:80] if text else None,
        )

    def write_runtime(self, **patch: object) -> None:
        state = self._read_runtime()
        state.update(patch)
        state["updated_at"] = _utc_now()
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self._temporary_path(self.runtime_path)
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.runtime_path)

    @staticmethod
    def _temporary_path(path: Path) -> Path:
        return path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")

    def _read_runtime(self) -> dict[str, object]:
        try:
            value = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _send(self, config: FeishuConfig, text: str, key_suffix: str) -> dict[str, object]:
        if config.uses_native_connection() and config.app_id:
            return self._send_native(config, text)
        return self._send_cli(config, text, key_suffix)

    def _send_native(self, config: FeishuConfig, text: str) -> dict[str, object]:
        app_secret = config.secret()
        if not app_secret:
            raise FeishuNotificationError("请填写 Feishu App Secret，或配置 App Secret 环境变量")
        runtime = self._read_runtime()
        target = config.discovered_chat_id or str(runtime.get("discovered_chat_id") or "")
        if not target:
            raise FeishuNotificationError("请先向守梦飞书智能体发送一条消息，以发现会话")
        base = config.api_base_url.rstrip("/")
        token = self._post_json(
            f"{base}/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": config.app_id, "app_secret": app_secret},
        )
        tenant_access_token = str(token.get("tenant_access_token") or "").strip()
        if not tenant_access_token:
            raise FeishuNotificationError(str(token.get("msg") or "Feishu tenant access token was not returned"))
        response = self._post_json(
            f"{base}/open-apis/im/v1/messages?receive_id_type=chat_id",
            {"receive_id": target, "msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)},
            headers={"Authorization": f"Bearer {tenant_access_token}"},
        )
        if str(response.get("code", "0")) not in {"0", "None"}:
            raise FeishuNotificationError(str(response.get("msg") or "Feishu message send failed"))
        return {"ok": True, "transport": "feishu-http", "discovered_chat_id": target}

    def _post_json(self, url: str, body: dict[str, object], *, headers: dict[str, str] | None = None) -> dict[str, object]:
        request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json; charset=utf-8")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise FeishuNotificationError(f"Feishu API request failed: {exc}") from exc
        return payload if isinstance(payload, dict) else {}

    def resolve_cli(self, config: FeishuConfig | None = None) -> str | None:
        config = config or self.get_config()
        candidates = [config.cli_path, os.environ.get("DREAMKEEPER_LARK_CLI", ""), "lark-cli", "lark"]
        if os.name == "nt":
            candidates.extend([str(Path(os.environ.get("APPDATA", "")) / "npm" / "lark-cli.cmd"), r"C:\Program Files\nodejs\lark-cli.cmd"])
        for candidate in candidates:
            candidate = str(candidate or "").strip()
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if path.is_file() or shutil.which(candidate):
                return str(path) if path.is_file() else candidate
        return None

    def _send_cli(self, config: FeishuConfig, text: str, key_suffix: str) -> dict[str, object]:
        cli = self.resolve_cli(config)
        if not cli:
            raise FeishuNotificationError("lark-cli was not found; configure the native Feishu connector or set its executable path")
        target_id = config.target_id
        if not target_id and config.target_type == "user_id":
            try:
                result = self.runner([cli, "auth", "status"], capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
                if result.returncode == 0:
                    value = json.loads(result.stdout or "")
                    target_id = str(value.get("identities", {}).get("user", {}).get("openId", ""))
            except (OSError, subprocess.SubprocessError, AttributeError, TypeError, json.JSONDecodeError):
                target_id = ""
        if not target_id:
            raise FeishuNotificationError("Recipient ID is empty; send a message to the bot first")
        args = [cli, "im", "+messages-send", "--as", config.identity]
        args.extend(["--user-id" if config.target_type == "user_id" else "--chat-id", target_id])
        args.extend(["--text", text, "--idempotency-key", f"dreamkeeper-{key_suffix}"[:50]])
        try:
            result = self.runner(args, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise FeishuNotificationError(f"Failed to run lark-cli: {exc}") from exc
        output = (result.stdout or result.stderr or "").strip()
        if result.returncode != 0:
            raise FeishuNotificationError(output or f"lark-cli exited with code {result.returncode}")
        return {"ok": True, "output": output, "command": args[:4], "transport": "lark-cli"}


FeishuCliNotifier = FeishuNotifier


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
