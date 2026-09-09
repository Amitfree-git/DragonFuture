from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


def sqlite_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("backup supports file-backed sqlite:/// URLs only")
    path = Path(database_url.removeprefix("sqlite:///")).expanduser()
    if str(path) in {":memory:", ""}:
        raise ValueError("in-memory databases cannot be backed up with this helper")
    return path.resolve()


def backup_sqlite(database_url: str, destination: Path) -> Path:
    """Use SQLite's backup API so WAL sidecars are checkpointed into the copy."""
    source = sqlite_path(database_url)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dest:
        src.backup(dest)
        dest.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return destination


def restore_sqlite(backup_path: Path, destination_url: str) -> Path:
    backup = Path(backup_path)
    target = sqlite_path(destination_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as src, sqlite3.connect(target) as dest:
        src.backup(dest)
    return target


def table_count(database_url: str, table: str) -> int:
    if not table.isidentifier() or not table.startswith("fut_"):
        raise ValueError("table must be a fut_* identifier")
    path = sqlite_path(database_url)
    with sqlite3.connect(path) as connection:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0]) if row else 0


def canonical_row_hash(database_url: str, table: str, columns: tuple[str, ...]) -> str:
    if not table.isidentifier() or not table.startswith("fut_"):
        raise ValueError("table must be a fut_* identifier")
    for column in columns:
        if not column.isidentifier():
            raise ValueError(f"invalid column {column}")
    path = sqlite_path(database_url)
    select_list = ", ".join(columns)
    order_list = ", ".join(columns)
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            f"SELECT {select_list} FROM {table} ORDER BY {order_list}"
        ).fetchall()
    digest = hashlib.sha256()
    for row in rows:
        digest.update(repr(tuple(row)).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()
