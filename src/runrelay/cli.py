from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .config import state_dir
from .models import Status
from .service import RunRelayService
from .web import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dreamkeeper",
        description="Dreamkeeper: let AI rest and wake it when experiments finish",
    )
    parser.add_argument("--home", help="Dreamkeeper state directory (legacy ~/.runrelay is reused when present)")
    sub = parser.add_subparsers(dest="action", required=True)

    submit = sub.add_parser("submit", help="Submit a detached experiment")
    submit.add_argument("--host", default="local")
    submit.add_argument("--workdir", default=".")
    submit.add_argument("--command", required=True)
    submit.add_argument("--name")
    submit.add_argument("--artifact", action="append", default=[])
    submit.add_argument("--source-dir")
    submit.add_argument(
        "--wake-backend",
        choices=["noop", "auto", "file", "command", "codex-cli"],
        default="noop",
    )
    submit.add_argument("--session", dest="session_id")
    submit.add_argument("--continuation-prompt")
    submit.add_argument("--wake-command")

    list_parser = sub.add_parser("list", help="List experiments")
    list_parser.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="Show one experiment")
    status.add_argument("id")
    status.add_argument("--json", action="store_true")

    logs = sub.add_parser("logs", help="Show experiment logs")
    logs.add_argument("id")
    logs.add_argument("--stderr", action="store_true")
    logs.add_argument("--follow", "-f", action="store_true")
    logs.add_argument("--interval", type=float, default=2.0)

    wait = sub.add_parser("wait", help="Wait without model polling")
    wait.add_argument("id")
    wait.add_argument("--interval", type=float, default=5.0)
    wait.add_argument("--timeout", type=float)

    cancel = sub.add_parser("cancel", help="Cancel an experiment")
    cancel.add_argument("id")

    daemon = sub.add_parser("daemon", help="Run the local reconciler")
    daemon_sub = daemon.add_subparsers(dest="daemon_action", required=True)
    daemon_run = daemon_sub.add_parser("run")
    daemon_run.add_argument("--interval", type=float, default=5.0)

    ui = sub.add_parser("ui", help="Run the localhost dashboard")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)

    server = sub.add_parser("server", help="Manage saved SSH server profiles")
    server_sub = server.add_subparsers(dest="server_action", required=True)
    server_add = server_sub.add_parser("add")
    server_add.add_argument("--name", required=True)
    server_add.add_argument("--host", required=True)
    server_add.add_argument("--port", type=int, default=22)
    server_add.add_argument("--user")
    server_add.add_argument("--identity-file")
    server_sub.add_parser("list")
    import_ssh = server_sub.add_parser("import-ssh")
    import_ssh.add_argument("--path", required=True)
    for action in ("test", "refresh"):
        item = server_sub.add_parser(action)
        item.add_argument("id")

    monitor = sub.add_parser("monitor", help="Monitor a remote process without model polling")
    monitor_sub = monitor.add_subparsers(dest="monitor_action", required=True)
    monitor_start = monitor_sub.add_parser("start")
    monitor_start.add_argument("--server-id", required=True)
    monitor_start.add_argument("--pid", type=int)
    monitor_start.add_argument("--command-filter")
    monitor_start.add_argument("--user-filter")
    monitor_start.add_argument("--stdout-path")
    monitor_start.add_argument("--stderr-path")
    monitor_start.add_argument("--interval", type=float, default=5.0)
    monitor_sub.add_parser("list")
    for action in ("status", "stop"):
        item = monitor_sub.add_parser(action)
        item.add_argument("id")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = RunRelayService(state_dir(args.home))
    try:
        if args.action == "submit":
            workdir = (
                str(Path(args.workdir).expanduser().resolve())
                if args.host == "local"
                else args.workdir
            )
            experiment = service.submit(
                host=args.host,
                workdir=workdir,
                command=args.command,
                name=args.name,
                artifacts=args.artifact,
                source_dir=args.source_dir,
                wake_backend=args.wake_backend,
                session_id=args.session_id,
                continuation_prompt=args.continuation_prompt,
                wake_command=args.wake_command,
            )
            print(
                "Experiment submitted\n\n"
                f"ID: {experiment.id}\n"
                f"Host: {experiment.host}\n"
                f"Status: {experiment.status.value}\n"
                f"PID: {experiment.pid}\n"
                f"State: {experiment.local_dir}"
            )
            print("\nYou may safely stop polling this experiment.")
            return
        if args.action == "list":
            items = service.list()
            if args.json:
                print(json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2))
            else:
                print(f"{'ID':<34} {'HOST':<16} {'STATUS':<10} COMMAND")
                for item in items:
                    print(f"{item.id:<34} {item.host:<16} {item.status.value:<10} {item.command}")
            return
        if args.action == "status":
            item = service.refresh(args.id)
            print(json.dumps(item.to_dict(), ensure_ascii=False, indent=2) if args.json else _format_status(item))
            return
        if args.action == "logs":
            _show_logs(service, args.id, args.stderr, args.follow, args.interval)
            return
        if args.action == "wait":
            item = service.wait(args.id, args.interval, args.timeout)
            print(_format_status(item))
            if item.status == Status.FAILED:
                raise SystemExit(item.exit_code or 1)
            return
        if args.action == "cancel":
            print(_format_status(service.cancel(args.id)))
            return
        if args.action == "daemon":
            service.daemon(args.interval)
            return
        if args.action == "ui":
            serve(service, args.host, args.port)
            return
        if args.action == "server":
            if args.server_action == "add":
                item = service.servers.save_server(
                    server_id=None, name=args.name, host=args.host, port=args.port,
                    username=args.user, identity_file=args.identity_file,
                )
                print(json.dumps(item.to_dict(), ensure_ascii=False, indent=2))
            elif args.server_action == "list":
                print(json.dumps([item.to_dict() for item in service.storage.list_servers()], ensure_ascii=False, indent=2))
            elif args.server_action == "import-ssh":
                items = service.servers.import_ssh_config(args.path)
                print(json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2))
            elif args.server_action == "test":
                print(json.dumps(service.servers.test_connection(args.id).to_dict(), ensure_ascii=False, indent=2))
            elif args.server_action == "refresh":
                print(json.dumps(service.servers.refresh_server(args.id).to_dict(), ensure_ascii=False, indent=2))
            return
        if args.action == "monitor":
            if args.monitor_action == "start":
                item = service.servers.start_monitor(
                    server_id=args.server_id, pid=args.pid, command_filter=args.command_filter,
                    user_filter=args.user_filter, stdout_path=args.stdout_path,
                    stderr_path=args.stderr_path, interval_seconds=args.interval,
                )
                print(json.dumps(item.to_dict(), ensure_ascii=False, indent=2))
            elif args.monitor_action == "list":
                print(json.dumps([item.to_dict() for item in service.storage.list_monitors()], ensure_ascii=False, indent=2))
            elif args.monitor_action == "status":
                print(json.dumps(service.storage.get_monitor(args.id).to_dict(), ensure_ascii=False, indent=2) if service.storage.get_monitor(args.id) else "Unknown monitor")
            elif args.monitor_action == "stop":
                print(json.dumps(service.servers.stop_monitor(args.id).to_dict(), ensure_ascii=False, indent=2))
            return
    except (KeyError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))


def _format_status(item) -> str:
    return (
        f"{item.id}\n"
        f"Status: {item.status.value}\n"
        f"Host: {item.host}\n"
        f"PID: {item.pid}\n"
        f"Exit code: {item.exit_code}\n"
        f"Started: {item.started_at}\n"
        f"Ended: {item.ended_at}\n"
        f"Wake: {item.wake_backend} / {item.wake_status}\n"
        f"Monitor: {item.monitor_status} (PID {item.monitor_pid})\n"
        f"Git: {item.git_commit or 'n/a'} ({item.git_branch or 'n/a'}) dirty={item.git_dirty}\n"
        f"Error: {item.last_error or 'n/a'}"
    )


def _show_logs(
    service: RunRelayService,
    experiment_id: str,
    stderr: bool,
    follow: bool,
    interval: float,
) -> None:
    while True:
        item = service.refresh(experiment_id)
        stdout, error = service.logs(experiment_id)
        print(error if stderr else stdout, end="")
        if not follow or item.status in {
            Status.COMPLETED,
            Status.FAILED,
            Status.CANCELLED,
            Status.LOST,
        }:
            return
        time.sleep(max(0.1, interval))


if __name__ == "__main__":
    main()
