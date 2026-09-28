"""SQLite 存储：项目身份、原子快照、事件与持久化幂等回执。"""

import hashlib
import hmac
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import Project, Snapshot, summarize


@contextmanager
def connect(db_path: str):
    db = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        if db.in_transaction:
            db.commit()
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0,
                snapshot_json TEXT, observed_at TEXT, received_at TEXT
            );
            CREATE TABLE IF NOT EXISTS receipts (
                project_id TEXT NOT NULL, request_key TEXT NOT NULL,
                request_hash TEXT NOT NULL, response_json TEXT NOT NULL,
                PRIMARY KEY(project_id, request_key),
                FOREIGN KEY(project_id) REFERENCES projects(project_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                received_at TEXT NOT NULL, observed_at TEXT NOT NULL,
                change_note TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(project_id)
            );
        """)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_project(db_path: str, project_id: str, token: str) -> None:
    with connect(db_path) as db:
        db.execute("INSERT INTO projects(project_id, token_hash) VALUES (?, ?)",
                   (project_id, hash_token(token)))


def rotate_project(db_path: str, project_id: str, token: str) -> None:
    with connect(db_path) as db:
        cursor = db.execute("UPDATE projects SET token_hash=? WHERE project_id=?",
                            (hash_token(token), project_id))
        if cursor.rowcount != 1:
            raise KeyError(project_id)


def authorized_revision(db_path: str, project_id: str, token: str) -> int | None:
    with connect(db_path) as db:
        row = db.execute("SELECT token_hash, revision FROM projects WHERE project_id=?",
                         (project_id,)).fetchone()
    if row is None or not hmac.compare_digest(row["token_hash"], hash_token(token)):
        return None
    return row["revision"]


class RevisionConflict(Exception):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision


class KeyConflict(Exception):
    pass


class AuthenticationChanged(Exception):
    pass


def save_snapshot(db_path: str, project_id: str, token: str, key: str, snapshot: Snapshot) -> dict:
    normalized = snapshot.model_dump(mode="json", exclude_none=True)
    canonical = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT token_hash, revision FROM projects WHERE project_id=?",
                         (project_id,)).fetchone()
        if row is None or not hmac.compare_digest(row["token_hash"], hash_token(token)):
            raise AuthenticationChanged()
        receipt = db.execute("SELECT request_hash, response_json FROM receipts WHERE project_id=? AND request_key=?",
                             (project_id, key)).fetchone()
        if receipt:
            if receipt["request_hash"] != request_hash:
                raise KeyConflict()
            return {**json.loads(receipt["response_json"]), "replayed": True}
        if row["revision"] != snapshot.expected_revision:
            raise RevisionConflict(row["revision"])
        revision = row["revision"] + 1
        received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        response = {"project_id": project_id, "revision": revision,
                    "received_at": received_at, "replayed": False}
        db.execute("UPDATE projects SET revision=?, snapshot_json=?, observed_at=?, received_at=? WHERE project_id=?",
                   (revision, json.dumps(normalized["project"], ensure_ascii=False),
                    snapshot.observed_at, received_at, project_id))
        db.execute("INSERT INTO events(project_id, revision, received_at, observed_at, change_note) VALUES (?, ?, ?, ?, ?)",
                   (project_id, revision, received_at, snapshot.observed_at, snapshot.change_note))
        db.execute("INSERT INTO receipts(project_id, request_key, request_hash, response_json) VALUES (?, ?, ?, ?)",
                   (project_id, key, request_hash, json.dumps(response)))
        db.commit()
        return response


def project_views(db_path: str, project_id: str | None = None) -> list[dict]:
    query = "SELECT project_id, revision, snapshot_json, observed_at, received_at FROM projects WHERE snapshot_json IS NOT NULL"
    params = ()
    if project_id is not None:
        query += " AND project_id=?"
        params = (project_id,)
    query += " ORDER BY project_id"
    with connect(db_path) as db:
        rows = db.execute(query, params).fetchall()
    views = []
    for row in rows:
        project = Project.model_validate(json.loads(row["snapshot_json"]))
        views.append({**project.model_dump(mode="json", exclude_none=True),
                      "id": row["project_id"], "revision": row["revision"],
                      "receivedAt": row["received_at"], "observedAt": row["observed_at"],
                      "progress": summarize(project)})
    return views
