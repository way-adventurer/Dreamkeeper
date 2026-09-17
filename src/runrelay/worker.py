from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--log-dir", required=True)
    args = parser.parse_args()
    directory = Path(args.log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "start_time").write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    try:
        with (directory / "stdout.log").open("w", encoding="utf-8") as stdout, (
            directory / "stderr.log"
        ).open("w", encoding="utf-8") as stderr:
            result = subprocess.run(
                args.command,
                cwd=args.workdir,
                shell=True,
                stdout=stdout,
                stderr=stderr,
            )
            code = result.returncode
    except Exception as exc:
        (directory / "stderr.log").write_text(str(exc), encoding="utf-8")
        code = 1
    (directory / "exit_code").write_text(str(code), encoding="utf-8")
    (directory / "end_time").write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

