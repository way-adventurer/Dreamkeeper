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


class CodexCliResumeWake:
    name = "codex-cli"

    def wake(self, experiment: Experiment) -> str:
        if not experiment.session_id:
            raise RuntimeError("codex-cli wake backend requires session_id")
        prompt = experiment.continuation_prompt or (
            f"Dreamkeeper experiment {experiment.id} finished.\n"
            f"Status: {experiment.status.value}; exit code: {experiment.exit_code}.\n"
            f"Host: {experiment.host}; workdir: {experiment.workdir}.\n"
            f"Local Dreamkeeper state and logs: {experiment.local_dir}.\n"
            "Inspect the experiment status, logs, and declared artifacts, then continue the plan."
        )
        result = subprocess.run(
            ["codex", "exec", "resume", experiment.session_id, prompt, "--json"],
            cwd=experiment.git_repo or None,
            text=True,
            capture_output=True,
            check=False,
        )
        Path(experiment.local_dir).mkdir(parents=True, exist_ok=True)
        (Path(experiment.local_dir) / "codex-wake.jsonl").write_text(
            result.stdout, encoding="utf-8"
        )
        if result.returncode:
            raise RuntimeError(
                result.stderr.strip() or f"codex exec resume exited with {result.returncode}"
            )
        return "Codex CLI resume completed."


def make_wake_backend(experiment: Experiment) -> WakeBackend:
    if experiment.wake_backend == "noop":
        return NoopWake()
    if experiment.wake_backend == "file":
        return FileWake()
    if experiment.wake_backend == "command":
        return CommandWake()
    if experiment.wake_backend == "codex-cli":
        return CodexCliResumeWake()
    raise ValueError(f"Unknown wake backend: {experiment.wake_backend}")
