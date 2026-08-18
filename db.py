"""SQLite state for projects, their editable plans, and every render attempt.

Videos live on disk under data/media and only their paths are stored here --
SQLite BLOBs of a few MB each would bloat the database file, make backups
heavy, and rule out serving the video as a normal range-request stream.
"""
import json
import sqlite3
import time
import uuid
from pathlib import Path

DATA_DIR = Path("data")
MEDIA_DIR = DATA_DIR / "media"
DB_PATH = DATA_DIR / "uzcaption.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    source_path TEXT NOT NULL,
    duration    REAL,
    width       INTEGER,
    height      INTEGER,
    fps         REAL,
    status      TEXT NOT NULL DEFAULT 'new',
    error       TEXT,
    created_at  REAL NOT NULL
);

-- The plan is what the user edits: words, keyword flags, hook text, zoom and
-- sfx marks. Kept as one JSON document because a transcript is a couple of
-- hundred words and edits replace it wholesale.
CREATE TABLE IF NOT EXISTS plans (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    data       TEXT NOT NULL,
    updated_at REAL NOT NULL
);

-- One row per render attempt, each keeping the settings it ran with, so
-- "the previous one looked better" is answerable.
CREATE TABLE IF NOT EXISTS renders (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    settings    TEXT NOT NULL,
    output_path TEXT,
    ass_path    TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    REAL NOT NULL DEFAULT 0,
    error       TEXT,
    created_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS renders_by_project ON renders(project_id, created_at DESC);

-- Progress is journalled rather than kept in memory so a browser that
-- reconnects mid-render can replay what it missed instead of seeing a gap.
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    render_id  TEXT,
    stage      TEXT NOT NULL,
    progress   REAL,
    message    TEXT,
    ts         REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS events_by_project ON events(project_id, id);
"""

# Stages a client can expect, in order. The slow ones are worth a percentage;
# the rest are over in well under a second.
STAGES = ["probe", "audio", "transcribe", "plan", "enrich", "ready",
          "subtitles", "render", "done"]

# Stages that end a stream. "ready" is not one of them: it closes ingest, but a
# render follows on the same project and the client wants to keep watching.
TERMINAL_STAGES = {"done", "error"}


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL lets the API read while a render writes progress; without it the
    # reader blocks for the length of the render.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)


def new_id() -> str:
    return uuid.uuid4().hex


# --- projects ---------------------------------------------------------------

def create_project(name: str, source_path: str, duration: float | None = None,
                   width: int | None = None, height: int | None = None,
                   fps: float | None = None) -> str:
    """Dimensions are optional so an upload handler can create the row and return
    an id immediately, letting the worker fill in the probe results."""
    project_id = new_id()
    with connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_path, duration, width, height, fps,"
            " status, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (project_id, name, source_path, duration, width, height, fps, "ingesting", time.time()),
        )
    return project_id


def update_project(project_id: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE projects SET {cols} WHERE id=?", (*fields.values(), project_id))


def set_project_status(project_id: str, status: str, error: str | None = None):
    with connect() as conn:
        conn.execute("UPDATE projects SET status=?, error=? WHERE id=?", (status, error, project_id))


def get_project(project_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return dict(row) if row else None


def list_projects(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# --- plans ------------------------------------------------------------------

def save_plan(project_id: str, plan: dict):
    with connect() as conn:
        conn.execute(
            "INSERT INTO plans (project_id, data, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(project_id) DO UPDATE SET data=excluded.data,"
            " updated_at=excluded.updated_at",
            (project_id, json.dumps(plan, ensure_ascii=False), time.time()),
        )


def get_plan(project_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT data FROM plans WHERE project_id=?", (project_id,)).fetchone()
    return json.loads(row["data"]) if row else None


# --- renders ----------------------------------------------------------------

def create_render(project_id: str, settings: dict) -> str:
    render_id = new_id()
    with connect() as conn:
        conn.execute(
            "INSERT INTO renders (id, project_id, settings, status, created_at)"
            " VALUES (?,?,?,?,?)",
            (render_id, project_id, json.dumps(settings, ensure_ascii=False), "queued", time.time()),
        )
    return render_id


def update_render(render_id: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE renders SET {cols} WHERE id=?", (*fields.values(), render_id))


def get_render(render_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM renders WHERE id=?", (render_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["settings"] = json.loads(out["settings"])
    return out


def list_renders(project_id: str, limit: int = 20) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM renders WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["settings"] = json.loads(d["settings"])
        out.append(d)
    return out


# --- events -----------------------------------------------------------------

def add_event(project_id: str, stage: str, progress: float | None = None,
              message: str | None = None, render_id: str | None = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO events (project_id, render_id, stage, progress, message, ts)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, render_id, stage, progress, message, time.time()),
        )
    return cur.lastrowid


def list_events(project_id: str, after_id: int = 0, limit: int = 500) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE project_id=? AND id>? ORDER BY id LIMIT ?",
            (project_id, after_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
