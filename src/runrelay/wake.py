from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Protocol

from .models import Experiment


class WakeBackend(Protocol):
    name: str

    def wake(self, experiment: Experiment) -> str:
        ...


class NoopWake:
    name = "noop"

    def wake(self, experiment: Experiment) -> str:
        return "Completion recorded; no wake action requested."


class FileWake:
    name = "file"

    def wake(self, experiment: Experiment) -> str:
        target = Path(experiment.local_dir) / "wake.json"
        target.write_text(
            json.dumps(experiment.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(target)


class CommandWake:
    name = "command"

    def wake(self, experiment: Experiment) -> str:
        if not experiment.wake_command:
            raise RuntimeError("command wake backend requires wake_command")
        environment = os.environ.copy()
        environment.update(
            {
                "RUNRELAY_EXPERIMENT_ID": experiment.id,
                "RUNRELAY_STATUS": experiment.status.value,
                "RUNRELAY_EXIT_CODE": (
                    "" if experiment.exit_code is None else str(experiment.exit_code)
                ),
                "RUNRELAY_LOCAL_DIR": experiment.local_dir,
            }
        )
        result = subprocess.run(
            experiment.wake_command,
            shell=True,
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                result.stderr.strip() or f"wake command exited with {result.returncode}"
            )
        return result.stdout.strip() or "Wake command completed."


def make_wake_backend(experiment: Experiment) -> WakeBackend:
    if experiment.wake_backend == "noop":
        return NoopWake()
    if experiment.wake_backend == "file":
        return FileWake()
    if experiment.wake_backend == "command":
        return CommandWake()
    # Treat the old experimental value as a no-op so existing state files
    # remain readable after the unsupported integration was removed.
    if experiment.wake_backend == "auto":
        return NoopWake()
    raise ValueError(f"Unknown wake backend: {experiment.wake_backend}")
