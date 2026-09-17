from __future__ import annotations

import os
from pathlib import Path


def state_dir(explicit: str | None = None) -> Path:
    value = explicit or os.environ.get("DREAMKEEPER_HOME") or os.environ.get("RUNRELAY_HOME")
    if not value:
        legacy = Path("~/.runrelay").expanduser()
        value = str(legacy if legacy.exists() else Path("~/.dreamkeeper").expanduser())
    path = Path(value).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    (path / "experiments").mkdir(parents=True, exist_ok=True)
    return path
