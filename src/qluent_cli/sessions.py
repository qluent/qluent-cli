"""Persist successful investigate / deep-dive runs to disk.

Runs are written to ``~/.qluent/sessions/YYYY/MM/DD/<tree>-<run_id>.json``
and indexed in a SQLite database at ``~/.qluent/sessions/index.db`` so
``qluent runs list`` and ``--last`` / ``--resume`` lookups stay cheap.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from qluent_cli import config as _config_module


INVESTIGATE_COMMAND = "trees investigate"
DEEP_DIVE_COMMAND = "trees deep-dive"
KNOWN_COMMANDS = (INVESTIGATE_COMMAND, DEEP_DIVE_COMMAND)


# Crockford base32 (no I, L, O, U) — gives a time-sortable, unambiguous ID.
_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_RUN_ID_RE = re.compile(r"^[0-9A-Z]{16}$")
_DURATION_SHORT_RE = re.compile(r"^\s*(\d+)\s*([smhdwy])\s*$", re.IGNORECASE)
_DURATION_NATURAL_RE = re.compile(
    r"^\s*(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*(ago)?\s*$",
    re.IGNORECASE,
)
_DURATION_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31536000,
}
_NATURAL_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 30 * 86400,
    "year": 365 * 86400,
}


def _safe_filename_component(value: str | None) -> str:
    if not value:
        return "all"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return safe or "tree"


def _sessions_dir() -> Path:
    return _config_module.CONFIG_DIR / "sessions"


def _index_path() -> Path:
    return _sessions_dir() / "index.db"


def _encode_base32(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        chars.append(_BASE32[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def generate_run_id(now_ms: int | None = None) -> str:
    """Return a 16-char Crockford-base32 ID. 10 chars time prefix + 6 random."""
    ts = int(time.time() * 1000) if now_ms is None else now_ms
    time_part = _encode_base32(ts, 10)
    random_part = "".join(_BASE32[secrets.randbelow(32)] for _ in range(6))
    return time_part + random_part


def is_valid_run_id(value: str) -> bool:
    return bool(_RUN_ID_RE.match(value))


@dataclass
class RunRecord:
    run_id: str
    command: str
    tree_id: str | None
    period_start: str | None
    period_end: str | None
    comparison_start: str | None
    comparison_end: str | None
    started_at: str
    profile: str | None
    client_safe: bool
    path: Path

    def load(self) -> dict[str, Any]:
        with open(self.path) as f:
            return json.load(f)


def _connect() -> sqlite3.Connection:
    index = _index_path()
    index.parent.mkdir(parents=True, exist_ok=True)
    index.parent.chmod(0o700)
    conn = sqlite3.connect(str(index))
    index.chmod(0o600)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            tree_id TEXT,
            period_start TEXT,
            period_end TEXT,
            comparison_start TEXT,
            comparison_end TEXT,
            started_at TEXT NOT NULL,
            profile TEXT,
            client_safe INTEGER NOT NULL DEFAULT 0,
            path TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_command_tree ON runs(command, tree_id, started_at DESC)"
    )
    return conn


def _row_to_record(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        command=row["command"],
        tree_id=row["tree_id"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        comparison_start=row["comparison_start"],
        comparison_end=row["comparison_end"],
        started_at=row["started_at"],
        profile=row["profile"],
        client_safe=bool(row["client_safe"]),
        path=Path(row["path"]),
    )


def _now_iso() -> tuple[datetime, str]:
    now = datetime.now(timezone.utc)
    return now, _iso(now)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def record_run(
    *,
    command: str,
    tree_id: str | None,
    period_start: str | None,
    period_end: str | None,
    comparison_start: str | None,
    comparison_end: str | None,
    profile: str | None,
    client_safe: bool,
    args: dict[str, Any],
    payload: Any,
) -> RunRecord:
    """Persist a successful run. Writes the JSON file then indexes it."""
    now, started_at = _now_iso()
    run_id = generate_run_id(int(now.timestamp() * 1000))

    base = _sessions_dir() / f"{now:%Y/%m/%d}"
    base.mkdir(parents=True, exist_ok=True)
    _sessions_dir().chmod(0o700)
    for parent in base.relative_to(_sessions_dir()).parents:
        (_sessions_dir() / parent).chmod(0o700)
    base.chmod(0o700)
    file_name = f"{_safe_filename_component(tree_id)}-{run_id}.json"
    path = base / file_name

    file_payload = {
        "run_id": run_id,
        "command": command,
        "tree_id": tree_id,
        "period": {
            "current_from": period_start,
            "current_to": period_end,
            "comparison_from": comparison_start,
            "comparison_to": comparison_end,
        },
        "profile": profile,
        "client_safe": client_safe,
        "started_at": started_at,
        "args": args,
        "result": payload,
    }
    with open(path, "w") as f:
        json.dump(file_payload, f, indent=2, default=str)
    path.chmod(0o600)

    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, command, tree_id,
                    period_start, period_end,
                    comparison_start, comparison_end,
                    started_at, profile, client_safe, path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    command,
                    tree_id,
                    period_start,
                    period_end,
                    comparison_start,
                    comparison_end,
                    started_at,
                    profile,
                    1 if client_safe else 0,
                    str(path),
                ),
            )
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise

    return RunRecord(
        run_id=run_id,
        command=command,
        tree_id=tree_id,
        period_start=period_start,
        period_end=period_end,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
        started_at=started_at,
        profile=profile,
        client_safe=client_safe,
        path=path,
    )


def get_run(run_id: str) -> RunRecord | None:
    if not _index_path().exists():
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    return _row_to_record(row) if row else None


def find_last_run(
    *,
    command: str | None = None,
    tree_id: str | None = None,
) -> RunRecord | None:
    if not _index_path().exists():
        return None
    clauses: list[str] = []
    params: list[Any] = []
    if command:
        clauses.append("command = ?")
        params.append(command)
    if tree_id:
        clauses.append("tree_id = ?")
        params.append(tree_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM runs {where} ORDER BY started_at DESC LIMIT 1"
    with _connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return _row_to_record(row) if row else None


def list_runs(
    *,
    tree_id: str | None = None,
    command: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[RunRecord]:
    if not _index_path().exists():
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if tree_id:
        clauses.append("tree_id = ?")
        params.append(tree_id)
    if command:
        clauses.append("command = ?")
        params.append(command)
    if since:
        cutoff = relative_cutoff(since)
        clauses.append("started_at >= ?")
        params.append(_iso(cutoff))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM runs {where} ORDER BY started_at DESC"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_record(r) for r in rows]


def parse_relative_seconds(value: str) -> int:
    """Parse '30d', '12h', '7 days ago' into a positive number of seconds."""
    short = _DURATION_SHORT_RE.match(value)
    if short:
        return _DURATION_SECONDS[short.group(2).lower()] * int(short.group(1))
    natural = _DURATION_NATURAL_RE.match(value)
    if natural:
        return _NATURAL_SECONDS[natural.group(2).lower()] * int(natural.group(1))
    raise ValueError(
        f"Invalid duration '{value}'. Use forms like '30d', '12h', or '7 days ago'."
    )


def relative_cutoff(value: str) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=parse_relative_seconds(value))


def prune_runs(
    *, older_than: str | None = None, max_runs: int | None = None
) -> list[RunRecord]:
    """Delete runs older than ``older_than`` and beyond the ``max_runs`` cap."""
    if not _index_path().exists():
        return []

    removed: list[RunRecord] = []
    with _connect() as conn:
        if older_than:
            cutoff = relative_cutoff(older_than)
            rows = conn.execute(
                "SELECT * FROM runs WHERE started_at < ?", (_iso(cutoff),)
            ).fetchall()
            for row in rows:
                _delete_file(row["path"])
                conn.execute("DELETE FROM runs WHERE run_id = ?", (row["run_id"],))
                removed.append(_row_to_record(row))

        if max_runs is not None:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT -1 OFFSET ?",
                (max_runs,),
            ).fetchall()
            for row in rows:
                _delete_file(row["path"])
                conn.execute("DELETE FROM runs WHERE run_id = ?", (row["run_id"],))
                removed.append(_row_to_record(row))

    return removed


def _delete_file(path: str) -> None:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
