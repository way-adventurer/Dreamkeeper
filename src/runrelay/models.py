from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any


class Status(str, Enum):
    PENDING = "PENDING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    LOST = "LOST"


TERMINAL_STATUSES = {Status.COMPLETED, Status.FAILED, Status.CANCELLED, Status.LOST}


@dataclass
class ServerProfile:
    id: str
    name: str
    host: str
    port: int = 22
    username: str | None = None
    identity_file: str | None = None
    remote_forwards: list[str] = field(default_factory=list)
    watch_status: str = "OFF"
    watch_interval: float = 2.0
    created_at: str = ""
    updated_at: str = ""
    last_test_at: str | None = None
    last_test_ok: bool | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ServerProfile":
        value = dict(value)
        value.setdefault("remote_forwards", [])
        return cls(**value)


@dataclass
class GPUSnapshot:
    index: str
    name: str
    memory_total_mib: float | None = None
    memory_used_mib: float | None = None
    utilization_percent: float | None = None
    temperature_c: float | None = None
    power_draw_w: float | None = None
    uuid: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ProcessSnapshot:
    pid: int
    user: str
    state: str
    elapsed_seconds: int | None = None
    command: str = ""
    gpu_index: str | None = None
    gpu_memory_mib: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ServerSnapshot:
    server_id: str
    fetched_at: str
    hostname: str = ""
    system: str = ""
    gpus: list[GPUSnapshot] = field(default_factory=list)
    processes: list[ProcessSnapshot] = field(default_factory=list)
    error: str | None = None
    gpu_processes: list[ProcessSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.__dict__)
        result["gpus"] = [item.to_dict() for item in self.gpus]
        result["processes"] = [item.to_dict() for item in self.processes]
        result["gpu_processes"] = [item.to_dict() for item in self.gpu_processes]
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ServerSnapshot":
        value = dict(value)
        value["gpus"] = [GPUSnapshot(**item) for item in value.get("gpus", [])]
        value["processes"] = [ProcessSnapshot(**item) for item in value.get("processes", [])]
        value["gpu_processes"] = [
            ProcessSnapshot(**item) for item in value.get(
                "gpu_processes", [item for item in value["processes"] if item.gpu_index]
            )
        ]
        return cls(**value)


@dataclass
class ProcessMonitor:
    id: str
    server_id: str
    pid: int | None = None
    command_filter: str | None = None
    user_filter: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    interval_seconds: float = 5.0
    status: str = "PENDING"
    created_at: str = ""
    started_at: str | None = None
    ended_at: str | None = None
    last_seen_at: str | None = None
    exit_code: int | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    log_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.__dict__)
        result["summary"] = dict(self.summary)
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProcessMonitor":
        allowed = {item.name for item in fields(cls)}
        value = {key: item for key, item in dict(value).items() if key in allowed}
        value.setdefault("summary", {})
        return cls(**value)


@dataclass
class Experiment:
    id: str
    host: str
    workdir: str
    command: str
    status: Status = Status.PENDING
    name: str | None = None
    created_at: str = ""
    started_at: str | None = None
    ended_at: str | None = None
    pid: int | None = None
    exit_code: int | None = None
    local_dir: str = ""
    remote_dir: str | None = None
    git_repo: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    git_dirty: bool | None = None
    artifacts: list[str] = field(default_factory=list)
    wake_backend: str = "noop"
    wake_status: str = "PENDING"
    wake_detail: str | None = None
    session_id: str | None = None
    continuation_prompt: str | None = None
    wake_command: str | None = None
    last_error: str | None = None
    monitor_pid: int | None = None
    monitor_status: str = "PENDING"

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.__dict__)
        result["status"] = self.status.value
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Experiment":
        value = dict(value)
        value["status"] = Status(value["status"])
        value.setdefault("artifacts", [])
        return cls(**value)
