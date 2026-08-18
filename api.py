"""FastAPI job service: POST /process, GET /status/{id}, GET /result/{id}.

# ponytail: single-worker in-process queue + on-disk jobs dict, fine for one box.
# Swap ThreadPoolExecutor for Celery/RQ and jobs dict for Redis/DB when jobs need
# to survive a restart or run across multiple machines. Same for output storage:
# on disk now, S3/R2 later.
"""
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from pipeline import run_pipeline

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=1)
jobs: dict[str, dict] = {}


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("static/index.html").read_text(encoding="utf-8")


def _process_job(job_id: str, input_path: str, style: str):
    jobs[job_id]["status"] = "processing"
    try:
        def progress_cb(frac: float):
            jobs[job_id]["progress"] = frac

        metadata = run_pipeline(input_path, style_name=style, progress_cb=progress_cb)
        jobs[job_id].update(status="done", progress=1.0, metadata=metadata)
    except Exception as e:
        jobs[job_id].update(status="error", error=str(e))


@app.post("/process")
async def process(file: UploadFile = File(...), style: str = Form("warm_karaoke")):
    job_id = uuid.uuid4().hex
    input_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    jobs[job_id] = {"status": "queued", "progress": 0.0}
    executor.submit(_process_job, job_id, str(input_path), style)
    return {"job_id": job_id}


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
