"""Small dependency-free MCP stdio adapter for the RunRelay CLI/service.

The plugin keeps the MCP surface narrow: read operations are available for
inspection, while submit and cancel require an explicit ``confirm`` input and
are marked for approval by the plugin manifest.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _load_runrelay() -> tuple[Any, Any, Any]:
    """Load the sibling project package when the plugin is installed from this repo."""
    script = Path(__file__).resolve()
    candidates = [
        Path(os.environ["RUNRELAY_ROOT"]) / "src" if os.environ.get("RUNRELAY_ROOT") else Path("__missing__"),
        script.parents[3] / "src",
        script.parents[2] / "src",
    ]
    for candidate in candidates:
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    try:
        from runrelay.config import state_dir
        from runrelay.models import Status
        from runrelay.service import RunRelayService
    except (ImportError, KeyError) as exc:
        raise RuntimeError(
            "RunRelay package is unavailable. Install the repository with "
            "python -m pip install -e . or set RUNRELAY_ROOT."
        ) from exc
    return RunRelayService, Status, state_dir


def _service(home: str | None):
    service_type, _, state_dir = _load_runrelay()
    return service_type(state_dir(home))


def _item(item: Any) -> dict[str, Any]:
    return item.to_dict()


def _result(value: Any, message: str | None = None) -> dict[str, Any]:
    text = message or json.dumps(value, ensure_ascii=False, indent=2)
    return {"structuredContent": value, "content": [{"type": "text", "text": text}]}


def _error(message: str) -> dict[str, Any]:
    return {"isError": True, "content": [{"type": "text", "text": message}]}


def _require_confirmation(args: dict[str, Any], action: str) -> None:
    if args.get("confirm") is not True:
        raise ValueError(
            f"{action} was not executed. Call this tool again with confirm=true "
            "only after the user has explicitly requested the action."
        )


def _list(args: dict[str, Any]) -> dict[str, Any]:
    items = [_item(item) for item in _service(args.get("home")).list()]
    if args.get("status"):
        items = [item for item in items if item["status"] == args["status"]]
    if args.get("host"):
        items = [item for item in items if item["host"] == args["host"]]
    limit = max(1, min(int(args.get("limit", 50)), 200))
    return _result({"experiments": items[:limit], "total": len(items)})


def _get(args: dict[str, Any]) -> dict[str, Any]:
    item = _service(args.get("home")).refresh(args["experiment_id"])
    return _result(_item(item))


def _submit(args: dict[str, Any]) -> dict[str, Any]:
    _require_confirmation(args, "Submitting an experiment")
    service = _service(args.get("home"))
    item = service.submit(
        host=args["host"],
        workdir=args["workdir"],
        command=args["command"],
        name=args.get("name"),
        artifacts=args.get("artifacts") or [],
        source_dir=args.get("source_dir"),
        wake_backend=args.get("wake_backend", "auto"),
        session_id=args.get("session_id"),
        continuation_prompt=args.get("continuation_prompt"),
        wake_command=args.get("wake_command"),
    )
    value = _item(item)
    return _result(value, f"Submitted RunRelay experiment {item.id}.\n{json.dumps(value, ensure_ascii=False, indent=2)}")


def _wait(args: dict[str, Any]) -> dict[str, Any]:
    interval = max(0.2, min(float(args.get("interval", 5)), 60))
    timeout = args.get("timeout")
    timeout = None if timeout is None else max(0.0, float(timeout))
    item = _service(args.get("home")).wait(args["experiment_id"], interval=interval, timeout=timeout)
    return _result(_item(item))


def _logs(args: dict[str, Any]) -> dict[str, Any]:
    stdout, stderr = _service(args.get("home")).logs(args["experiment_id"])
    max_chars = max(1000, min(int(args.get("max_chars", 12000)), 50000))
    value = {
        "experiment_id": args["experiment_id"],
        "stdout": stdout[:max_chars],
        "stderr": stderr[:max_chars],
        "truncated": len(stdout) > max_chars or len(stderr) > max_chars,
    }
    return _result(value)


def _cancel(args: dict[str, Any]) -> dict[str, Any]:
    _require_confirmation(args, "Cancelling an experiment")
    item = _service(args.get("home")).cancel(args["experiment_id"])
    return _result(_item(item))


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


COMMON_HOME = {"home": {"type": "string", "description": "Optional RunRelay state directory."}}
TOOLS = [
    {
        "name": "runrelay_list_experiments",
        "title": "List RunRelay experiments",
        "description": "List detached experiments and their current status. Use for a status overview or to find an experiment ID.",
        "inputSchema": _schema({**COMMON_HOME, "status": {"type": "string"}, "host": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "runrelay_get_experiment",
        "title": "Get RunRelay experiment",
        "description": "Refresh and return one experiment's current status, exit code, paths, and metadata.",
        "inputSchema": _schema({**COMMON_HOME, "experiment_id": {"type": "string"}}, ["experiment_id"]),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "runrelay_submit_experiment",
        "title": "Submit RunRelay experiment",
        "description": "Submit a detached local or SSH experiment. Use only when the user explicitly asked to run the specified command; confirm=true is required.",
        "inputSchema": _schema({**COMMON_HOME, "host": {"type": "string", "description": "local or an SSH config alias."}, "workdir": {"type": "string"}, "command": {"type": "string"}, "name": {"type": "string"}, "artifacts": {"type": "array", "items": {"type": "string"}}, "source_dir": {"type": "string"}, "wake_backend": {"type": "string", "enum": ["noop", "auto", "file", "command", "codex-cli"]}, "session_id": {"type": "string"}, "continuation_prompt": {"type": "string"}, "wake_command": {"type": "string"}, "confirm": {"type": "boolean"}}, ["host", "workdir", "command", "confirm"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    },
    {
        "name": "runrelay_wait_experiment",
        "title": "Wait for RunRelay experiment",
        "description": "Wait for one experiment to reach a terminal state without repeated model-side polling.",
        "inputSchema": _schema({**COMMON_HOME, "experiment_id": {"type": "string"}, "interval": {"type": "number", "minimum": 0.2, "maximum": 60}, "timeout": {"type": ["number", "null"], "minimum": 0}}, ["experiment_id"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "runrelay_get_logs",
        "title": "Read RunRelay logs",
        "description": "Read bounded stdout and stderr for a RunRelay experiment after or during execution.",
        "inputSchema": _schema({**COMMON_HOME, "experiment_id": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 1000, "maximum": 50000}}, ["experiment_id"]),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "runrelay_cancel_experiment",
        "title": "Cancel RunRelay experiment",
        "description": "Cancel a running experiment. Use only after the user explicitly asks to stop the named experiment; confirm=true is required.",
        "inputSchema": _schema({**COMMON_HOME, "experiment_id": {"type": "string"}, "confirm": {"type": "boolean"}}, ["experiment_id", "confirm"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    },
]


HANDLERS = {
    "runrelay_list_experiments": _list,
    "runrelay_get_experiment": _get,
    "runrelay_submit_experiment": _submit,
    "runrelay_wait_experiment": _wait,
    "runrelay_get_logs": _logs,
    "runrelay_cancel_experiment": _cancel,
}


def _send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    instructions = (
        "Use RunRelay for long-running experiments. Before submit or cancel, "
        "confirm the user's intent and exact target; submit returns an ID, and "
        "wait avoids repeated model-side polling."
    )
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            method = request.get("method")
            request_id = request.get("id")
            if method == "initialize":
                _send({"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "runrelay", "version": "0.1.0"}, "instructions": instructions}})
            elif method == "tools/list":
                _send({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
            elif method == "tools/call":
                params = request.get("params") or {}
                handler = HANDLERS.get(params.get("name"))
                if handler is None:
                    raise ValueError(f"Unknown RunRelay tool: {params.get('name')}")
                result = handler(params.get("arguments") or {})
                _send({"jsonrpc": "2.0", "id": request_id, "result": result})
            elif method == "ping":
                _send({"jsonrpc": "2.0", "id": request_id, "result": {}})
            elif request_id is not None:
                _send({"jsonrpc": "2.0", "id": request_id, "result": {}})
        except Exception as exc:  # Keep the stdio server alive for the next request.
            if "request_id" in locals() and request_id is not None:
                _send({"jsonrpc": "2.0", "id": request_id, "result": _error(str(exc))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
