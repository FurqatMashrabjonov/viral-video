"""FastAPI service.

Two job kinds, matching the two pipeline phases: ingest runs once per upload and
is the expensive one; render runs whenever the user changes a setting or edits
the plan, and never goes back to Scribe.

# ponytail: single-worker in-process queue. State now lives in SQLite so it
# survives a restart; swap ThreadPoolExecutor for Celery/RQ when renders need to
# run across more than one machine. Media stays on disk (S3/R2 later).
"""
import asyncio
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import db
from pipeline import ingest, render, re_enrich, DEFAULT_SETTINGS
from settings import schema as settings_schema, merge as merge_settings

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=1)

POLL_INTERVAL = 0.4     # seconds between checks for new journal rows
HEARTBEAT_EVERY = 15.0  # comment frame so idle proxies keep the stream open
STREAM_TIMEOUT = 300.0  # give up on a stream that has been silent this long

# Schema at import, not on a startup event: TestClient only fires startup when
# used as a context manager, and a handler that assumes the tables exist should
# not depend on how the app was instantiated. CREATE TABLE IF NOT EXISTS makes
# this safe to repeat.
db.init()


APP_DIR = Path("static/app")   # built frontend bundle, written by `npm run build`


@app.get("/", response_class=HTMLResponse)
async def index():
    built = APP_DIR / "index.html"
    if not built.exists():
        return (
            "<pre>Frontend bundle topilmadi. "
            "`cd web &amp;&amp; npm run build` ni ishga tushiring, "
            "yoki ishlab chiqishda `npm run dev` orqali oching.</pre>"
        )
    return built.read_text(encoding="utf-8")


if APP_DIR.exists():
    app.mount("/assets", StaticFiles(directory=APP_DIR / "assets"), name="assets")


# --- projects ---------------------------------------------------------------

@app.get("/api/projects")
async def api_list_projects():
    return db.list_projects()


@app.post("/api/projects")
async def api_create_project(file: UploadFile = File(...)):
    """Upload and ingest. This is the call that spends Scribe credit."""
    db.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    stored = db.MEDIA_DIR / f"src_{db.new_id()}{Path(file.filename or '.mp4').suffix}"
    with open(stored, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Create the row before queueing so the client gets an id to poll straight
    # away; the worker fills in the probe results.
    project_id = db.create_project(file.filename or stored.stem, str(stored))

    def work():
        try:
            ingest(str(stored), project_id=project_id)
        except Exception:
            pass  # ingest() already journalled the error and marked the project

    executor.submit(work)
    return {"project_id": project_id, "status": "ingesting"}


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "project not found")
    return {**project, "plan": db.get_plan(project_id), "renders": db.list_renders(project_id)}


@app.put("/api/projects/{project_id}/plan")
async def api_save_plan(project_id: str, plan: dict = Body(...)):
    """Save an edited plan: corrected words, keyword flags, hook text."""
    if not db.get_project(project_id):
        raise HTTPException(404, "project not found")
    db.save_plan(project_id, plan)
    return {"ok": True}


@app.post("/api/projects/{project_id}/enrich")
async def api_enrich(project_id: str):
    """Re-run hook/keyword/emoji generation on the stored transcript. A few
    seconds of Gemini, no Scribe call -- unlike render, this is cheap enough to
    just await and hand back the updated plan directly rather than making the
    client poll a job id."""
    if not db.get_project(project_id):
        raise HTTPException(404, "project not found")
    if not db.get_plan(project_id):
        raise HTTPException(409, "project has no plan yet")

    loop = asyncio.get_event_loop()
    try:
        plan = await loop.run_in_executor(executor, re_enrich, project_id)
    except Exception as e:
        raise HTTPException(502, f"enrich failed: {e}")
    return plan


# --- renders ----------------------------------------------------------------

@app.post("/api/projects/{project_id}/render")
async def api_render(project_id: str, body: dict = Body(default={})):
    """Render the stored plan. Body is either the settings directly (as the
    first clients posted) or {"settings": {...}, "segment": [t0, t1]} for a
    preview slice."""
    if not db.get_project(project_id):
        raise HTTPException(404, "project not found")
    if not db.get_plan(project_id):
        raise HTTPException(409, "project has no plan yet")

    settings = body.get("settings", body)
    merged = merge_settings(settings)

    segment = None
    raw_segment = body.get("segment")
    if raw_segment:
        try:
            t0, t1 = float(raw_segment[0]), float(raw_segment[1])
            if t0 < 0 or t1 <= t0:
                raise ValueError
            segment = (t0, t1)
        except (TypeError, ValueError, IndexError):
            raise HTTPException(422, "segment must be [t0, t1] with 0 <= t0 < t1")

    # Create the row up front so the client gets an id it can poll immediately,
    # rather than after the render finishes.
    render_id = db.create_render(project_id, merged)

    def work():
        try:
            render(project_id, merged, render_id=render_id, segment=segment)
        except Exception:
            pass  # render() already journalled the error and marked the row

    executor.submit(work)
    return {"render_id": render_id, "project_id": project_id, "settings": merged, "status": "queued"}


@app.get("/api/renders/{render_id}")
async def api_get_render(render_id: str):
    row = db.get_render(render_id)
    if not row:
        raise HTTPException(404, "render not found")
    return row


@app.get("/api/renders/{render_id}/video")
async def api_render_video(render_id: str):
    row = db.get_render(render_id)
    if not row:
        raise HTTPException(404, "render not found")
    if row["status"] != "done":
        raise HTTPException(409, f"render status is {row['status']}")
    return FileResponse(row["output_path"], media_type="video/mp4")


@app.get("/api/projects/{project_id}/events")
async def api_events(project_id: str, after: int = 0):
    """Everything journalled so far. Useful on its own, and it is what the
    stream replays on reconnect."""
    if not db.get_project(project_id):
        raise HTTPException(404, "project not found")
    return db.list_events(project_id, after_id=after)


@app.get("/api/projects/{project_id}/stream")
async def api_stream(project_id: str, request: Request, after: int = 0):
    """Server-Sent Events: progress only ever flows server to client, so a
    WebSocket would add a return channel nothing uses.

    Each frame carries its row id, and a browser reconnecting sends it back in
    Last-Event-ID, so the replay picks up exactly where it stopped instead of
    leaving a hole.
    """
    if not db.get_project(project_id):
        raise HTTPException(404, "project not found")

    resume = request.headers.get("last-event-id")
    start = int(resume) if resume and resume.isdigit() else after

    async def frames():
        # Two clocks, not one: the heartbeat resets on every beat, so reusing it
        # to age out the stream would mean the timeout never arrives.
        last_id, idle, since_beat = start, 0.0, 0.0
        while True:
            if await request.is_disconnected():
                return

            events = db.list_events(project_id, after_id=last_id)
            for e in events:
                last_id = e["id"]
                yield f"id: {e['id']}\nevent: stage\ndata: {json.dumps(e)}\n\n"
                if e["stage"] in db.TERMINAL_STAGES:
                    return

            if events:
                idle = since_beat = 0.0
            else:
                idle += POLL_INTERVAL
                since_beat += POLL_INTERVAL

            if idle > STREAM_TIMEOUT:
                return
            if since_beat >= HEARTBEAT_EVERY:
                since_beat = 0.0
                yield ": keep-alive\n\n"   # stops idle proxies closing the stream
            await asyncio.sleep(POLL_INTERVAL)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/schema")
async def api_schema():
    """Every control the user has, declared once in settings.py, plus the stage
    names. The frontend draws its panel and its progress checklist from this
    rather than keeping second copies of either."""
    return {
        "fields": settings_schema(),
        "defaults": DEFAULT_SETTINGS,
        "stages": db.STAGES,
        "terminal_stages": sorted(db.TERMINAL_STAGES),
    }
