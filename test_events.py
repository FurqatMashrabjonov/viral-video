"""Self-check for the progress journal and the SSE stream.
Run: .venv/bin/python test_events.py
"""
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import db
from test_pipeline_smoke import MOCK_WORDS, make_smoke_clip

WORDS = MOCK_WORDS + [{"word": "30", "start": 2.0, "end": 2.4}]


def _fresh_project() -> str:
    shutil.rmtree(db.DATA_DIR, ignore_errors=True)
    db.init()
    return db.create_project("t", "x.mp4")


def test_events_come_back_in_insertion_order():
    pid = _fresh_project()
    for s in ["probe", "audio", "transcribe"]:
        db.add_event(pid, s)
    assert [e["stage"] for e in db.list_events(pid)] == ["probe", "audio", "transcribe"]


def test_after_id_returns_only_later_events():
    """This is what makes an SSE reconnect lossless rather than a guess."""
    pid = _fresh_project()
    ids = [db.add_event(pid, s) for s in ["probe", "audio", "transcribe", "plan"]]
    later = db.list_events(pid, after_id=ids[1])
    assert [e["stage"] for e in later] == ["transcribe", "plan"]
    assert all(e["id"] > ids[1] for e in later)


def test_events_are_scoped_to_their_project():
    pid_a = _fresh_project()
    pid_b = db.create_project("b", "y.mp4")
    db.add_event(pid_a, "probe")
    db.add_event(pid_b, "render")
    assert [e["stage"] for e in db.list_events(pid_a)] == ["probe"]
    assert [e["stage"] for e in db.list_events(pid_b)] == ["render"]


def test_every_declared_stage_is_reachable():
    """STAGES is what a client draws its checklist from, so a name that the
    pipeline never emits would leave a step stuck forever."""
    src = Path("pipeline.py").read_text(encoding="utf-8")
    for stage in db.STAGES:
        assert f'stage("{stage}"' in src, f"{stage} is declared but never emitted"


def test_ready_does_not_close_the_stream():
    """`ready` ends ingest, but a render follows on the same project and the
    client is still watching."""
    assert "ready" not in db.TERMINAL_STAGES
    assert db.TERMINAL_STAGES == {"done", "error"}


def test_stream_stays_open_across_ready():
    pid = _fresh_project()
    for s in ["probe", "ready", "subtitles", "done"]:
        db.add_event(pid, s)

    from api import app
    with TestClient(app).stream("GET", f"/api/projects/{pid}/stream") as r:
        body = "".join(r.iter_text())
    stages = [json.loads(l[6:])["stage"] for l in body.splitlines() if l.startswith("data: ")]
    assert stages == ["probe", "ready", "subtitles", "done"], stages


def test_stream_replays_from_last_event_id():
    pid = _fresh_project()
    ids = [db.add_event(pid, s) for s in ["probe", "audio", "transcribe"]]
    db.add_event(pid, "done")

    from api import app
    client = TestClient(app)
    with client.stream("GET", f"/api/projects/{pid}/stream",
                       headers={"Last-Event-ID": str(ids[0])}) as r:
        body = "".join(r.iter_text())

    stages = [json.loads(l[6:])["stage"] for l in body.splitlines() if l.startswith("data: ")]
    assert stages == ["audio", "transcribe", "done"], stages


def test_stream_closes_on_a_terminal_stage():
    """Without this the generator would hold a worker open forever."""
    pid = _fresh_project()
    db.add_event(pid, "render")
    db.add_event(pid, "done")
    db.add_event(pid, "probe")   # anything after the terminal frame is not sent

    from api import app
    client = TestClient(app)
    with client.stream("GET", f"/api/projects/{pid}/stream") as r:
        body = "".join(r.iter_text())
    stages = [json.loads(l[6:])["stage"] for l in body.splitlines() if l.startswith("data: ")]
    assert stages == ["render", "done"], stages


def test_progress_events_are_throttled_to_one_per_five_percent():
    """ffmpeg reports several times a second; journalling all of them would
    bury the stage rows."""
    shutil.rmtree(db.DATA_DIR, ignore_errors=True)
    clip = Path("output/events_src.mp4")
    clip.parent.mkdir(exist_ok=True)
    make_smoke_clip(clip)

    from pipeline import ingest, render
    with patch("pipeline.transcribe", return_value=WORDS):
        pid = ingest(str(clip), enrich=False)
        render(pid)

    render_events = [e for e in db.list_events(pid) if e["progress"] is not None]
    assert render_events, "no progress was journalled"
    assert len(render_events) <= 21, f"{len(render_events)} rows for 20 notches"
    progresses = [e["progress"] for e in render_events]
    assert progresses == sorted(progresses), "progress went backwards"


def test_unknown_project_has_no_stream():
    from api import app
    assert TestClient(app).get("/api/projects/nope/stream").status_code == 404


if __name__ == "__main__":
    import sys
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    shutil.rmtree(db.DATA_DIR, ignore_errors=True)
    sys.exit(1 if failed else 0)
