from __future__ import annotations

import subprocess
from pathlib import Path


def _git(workdir: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=workdir,
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def capture(workdir: str | Path) -> dict[str, str | bool | None]:
    path = Path(workdir).expanduser()
    inside = _git(path, "rev-parse", "--show-toplevel")
    if not inside:
        return {"git_repo": None, "git_branch": None, "git_commit": None, "git_dirty": None}
    dirty = _git(path, "status", "--porcelain")
    return {
        "git_repo": inside,
        "git_branch": _git(path, "branch", "--show-current") or None,
        "git_commit": _git(path, "rev-parse", "HEAD"),
        "git_dirty": bool(dirty),
    }

