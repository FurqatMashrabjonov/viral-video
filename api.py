"""FastAPI service.

Two job kinds, matching the two pipeline phases: ingest runs once per upload and
is the expensive one; render runs whenever the user changes a setting or edits
the plan, and never goes back to Scribe.

# ponytail: single-worker in-process queue. State now lives in SQLite so it
# survives a restart; swap ThreadPoolExecutor for Celery/RQ when renders need to
# run across more than one machine. Media stays on disk (S3/R2 later).
"""
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import FileResponse, HTMLResponse

import db
from pipeline import run_pipeline, ingest, render, DEFAULT_SETTINGS
from settings import schema as settings_schema, merge as merge_settings

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=1)
jobs: dict[str, dict] = {}          # legacy single-shot jobs
stages: dict[str, str] = {}         # project_id / render_id -> current stage

# Schema at import, not on a startup event: TestClient only fires startup when
# used as a context manager, and a handler that assumes the tables exist should
# not depend on how the app was instantiated. CREATE TABLE IF NOT EXISTS makes
# this safe to repeat.
db.init()


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("static/index.html").read_text(encoding="utf-8")


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
            ingest(str(stored), project_id=project_id,
                   stage_cb=lambda s: stages.update({project_id: s}))
        except Exception as e:
            stages[project_id] = f"error: {e}"

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


# --- renders ----------------------------------------------------------------

@app.post("/api/projects/{project_id}/render")
async def api_render(project_id: str, settings: dict = Body(default={})):
    if not db.get_project(project_id):
        raise HTTPException(404, "project not found")
    if not db.get_plan(project_id):
        raise HTTPException(409, "project has no plan yet")

    merged = merge_settings(settings)
    # Create the row up front so the client gets an id it can poll immediately,
    # rather than after the render finishes.
    render_id = db.create_render(project_id, merged)

    def work():
        try:
            render(project_id, merged, render_id=render_id,
                   stage_cb=lambda s: stages.update({render_id: s}))
        except Exception as e:
            stages[render_id] = f"error: {e}"

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


@app.get("/api/schema")
async def api_schema():
    """Every control the user has, declared once in settings.py. The frontend
    draws its panel from this rather than keeping a second list of its own."""
    return {"fields": settings_schema(), "defaults": DEFAULT_SETTINGS}


# --- legacy single-shot flow (the existing test UI) --------------------------

@app.post("/process")
async def process(file: UploadFile = File(...), style: str = Form("warm_karaoke")):
    job_id = db.new_id()
    input_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    jobs[job_id] = {"status": "queued", "progress": 0.0}
    executor.submit(_process_job, job_id, str(input_path), style)
    return {"job_id": job_id}


def _process_job(job_id: str, input_path: str, style: str):
    jobs[job_id]["status"] = "processing"
    try:
        metadata = run_pipeline(
            input_path, style_name=style,
            progress_cb=lambda f: jobs[job_id].update(progress=f),
        )
        jobs[job_id].update(status="done", progress=1.0, metadata=metadata)
    except Exception as e:
        jobs[job_id].update(status="error", error=str(e))


@app.get("/status/{job_id}")
async def status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return {"status": job["status"], "progress": job.get("progress", 0.0), "error": job.get("error")}


@app.get("/result/{job_id}")
async def result(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] != "done":
        raise HTTPException(409, f"job status is {job['status']}")
    return FileResponse(job["metadata"]["output_path"], media_type="video/mp4")


@app.get("/result/{job_id}/metadata")
async def result_metadata(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] != "done":
        raise HTTPException(409, f"job status is {job['status']}")
    return job["metadata"]
