from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import Experiment, ProcessMonitor, ServerProfile, ServerSnapshot, Status


class Storage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "runrelay.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS server_profiles (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS server_snapshots (
                    server_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS process_monitors (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def put(self, experiment: Experiment) -> None:
        payload = json.dumps(experiment.to_dict(), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiments (id, payload, created_at, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload=excluded.payload,
                    status=excluded.status
                """,
                (experiment.id, payload, experiment.created_at, experiment.status.value),
            )

    def get(self, experiment_id: str) -> Experiment | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
        return Experiment.from_dict(json.loads(row["payload"])) if row else None

    def list(self, statuses: Iterable[Status] | None = None) -> list[Experiment]:
        query = "SELECT payload FROM experiments"
        params: list[str] = []
        if statuses:
            values = [status.value for status in statuses]
            query += f" WHERE status IN ({','.join('?' for _ in values)})"
            params.extend(values)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Experiment.from_dict(json.loads(row["payload"])) for row in rows]

    def put_server(self, profile: ServerProfile) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO server_profiles (id, payload, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
                (profile.id, json.dumps(profile.to_dict(), ensure_ascii=False), profile.updated_at),
            )

    def get_server(self, server_id: str) -> ServerProfile | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM server_profiles WHERE id = ?", (server_id,)).fetchone()
        return ServerProfile.from_dict(json.loads(row["payload"])) if row else None

    def list_servers(self) -> list[ServerProfile]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM server_profiles ORDER BY updated_at DESC").fetchall()
        return [ServerProfile.from_dict(json.loads(row["payload"])) for row in rows]

    def delete_server(self, server_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM server_snapshots WHERE server_id = ?", (server_id,))
            connection.execute("DELETE FROM server_profiles WHERE id = ?", (server_id,))

    def put_snapshot(self, snapshot: ServerSnapshot) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO server_snapshots (server_id, payload, fetched_at) VALUES (?, ?, ?)
                ON CONFLICT(server_id) DO UPDATE SET payload=excluded.payload, fetched_at=excluded.fetched_at""",
                (snapshot.server_id, json.dumps(snapshot.to_dict(), ensure_ascii=False), snapshot.fetched_at),
            )

    def get_snapshot(self, server_id: str) -> ServerSnapshot | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM server_snapshots WHERE server_id = ?", (server_id,)).fetchone()
        return ServerSnapshot.from_dict(json.loads(row["payload"])) if row else None

    def put_monitor(self, monitor: ProcessMonitor) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO process_monitors (id, payload, status, created_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, status=excluded.status""",
                (monitor.id, json.dumps(monitor.to_dict(), ensure_ascii=False), monitor.status, monitor.created_at),
            )

    def get_monitor(self, monitor_id: str) -> ProcessMonitor | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM process_monitors WHERE id = ?", (monitor_id,)).fetchone()
        return ProcessMonitor.from_dict(json.loads(row["payload"])) if row else None

    def list_monitors(self, active_only: bool = False) -> list[ProcessMonitor]:
        query = "SELECT payload FROM process_monitors"
        if active_only:
            query += " WHERE status = 'RUNNING'"
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [ProcessMonitor.from_dict(json.loads(row["payload"])) for row in rows]
