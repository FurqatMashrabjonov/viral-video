"""Milestone 4 end-to-end demo: FastAPI /process -> /status -> /result.
Scribe is mocked (canned words) so this doesn't spend API credits.
Run: .venv/bin/python demo_milestone4.py
"""
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from demo_milestone3 import make_synthetic_input

MOCK_WORDS = [
    {"word": "Assalomu", "start": 0.20, "end": 0.65},
    {"word": "alaykum,", "start": 0.65, "end": 1.10},
    {"word": "bugun", "start": 1.20, "end": 1.55},
    {"word": "o`zbek", "start": 1.55, "end": 1.95},
    {"word": "tilida", "start": 1.95, "end": 2.35},
    {"word": "gaplashamiz", "start": 2.35, "end": 3.00},
]


def main():
    input_path = Path("output/m4_input.mp4")
    input_path.parent.mkdir(exist_ok=True)
    make_synthetic_input(input_path)

    with patch("pipeline.transcribe", return_value=MOCK_WORDS):
        from api import app
        client = TestClient(app)

        with open(input_path, "rb") as f:
            resp = client.post("/process", files={"file": ("m4_input.mp4", f, "video/mp4")}, data={"style": "warm_karaoke"})
        print("POST /process ->", resp.status_code, resp.json())
        job_id = resp.json()["job_id"]

        for _ in range(60):
            status = client.get(f"/status/{job_id}").json()
            print("GET /status ->", status)
            if status["status"] in ("done", "error"):
                break
            time.sleep(1)

        meta = client.get(f"/result/{job_id}/metadata")
        print("GET /result/metadata ->", meta.status_code, meta.json())

        result = client.get(f"/result/{job_id}")
        print("GET /result ->", result.status_code, len(result.content), "bytes")


if __name__ == "__main__":
    main()
