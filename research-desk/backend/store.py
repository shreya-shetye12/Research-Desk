"""Small SQLite ledger; one JSON record per immutable artifact or mutable state."""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
DB = RUNTIME / "workspace.sqlite3"


@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=20)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT PRIMARY KEY, payload TEXT, created REAL, updated REAL)"
        )


def put(kind, data, identifier=None, db=None):
    identifier = identifier or kind + "_" + uuid.uuid4().hex[:12]
    now = time.time()
    if db is None:
        with connect() as connection:
            return put(kind, data, identifier, connection)
    db.execute(
        "INSERT INTO records VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated=excluded.updated",
        (kind, identifier, json.dumps(data, allow_nan=False), now, now),
    )
    return identifier


def create_once(kind, data, identifier):
    """Replay-safe immutable artifact creation for checkpoint retries."""
    with connect() as db:
        now = time.time()
        db.execute(
            "INSERT OR IGNORE INTO records VALUES(?,?,?,?,?)",
            (kind, identifier, json.dumps(data, allow_nan=False), now, now),
        )
    return get(kind, identifier)


def get(kind, identifier):
    with connect() as db:
        row = db.execute(
            "SELECT * FROM records WHERE kind=? AND id=?", (kind, identifier)
        ).fetchone()
    if row is None:
        raise ValueError(f"{kind.capitalize()} record not found")
    return decode(row)


def decode(row):
    return {**json.loads(row["payload"]), "id": row["id"], "created": row["created"]}


def rows(kind):
    with connect() as db:
        return [
            decode(r)
            for r in db.execute(
                "SELECT * FROM records WHERE kind=? ORDER BY created DESC,id", (kind,)
            )
        ]


def update(kind, identifier, **changes):
    item = get(kind, identifier)
    item.update(changes)
    put(kind, item, identifier)
    return item


def log(action, detail):
    return put("event", {"action": action, "detail": detail})
