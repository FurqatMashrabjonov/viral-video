"""Phase 3 demo: watch the pipeline over SSE, then prove a reconnect replays
what it missed. Scribe is mocked. Run: .venv/bin/python demo_stream.py
"""
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import db
from test_pipeline_smoke import MOCK_WORDS

WORDS = MOCK_WORDS + [{"word": "30", "start": 2.0, "end": 2.4},
                      {"word": "foiz", "start": 2.4, "end": 2.9}]


def read_stream(client, project_id, out, stop_after=None, last_event_id=None):
    """Consume the SSE stream, appending (id, stage, progress) to `out`."""
    headers = {"Last-Event-ID": str(last_event_id)} if last_event_id else {}
    with client.stream("GET", f"/api/projects/{project_id}/stream", headers=headers) as r:
        buf = ""
        for chunk in r.iter_text():
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                data = next((l[6:] for l in frame.splitlines() if l.startswith("data: ")), None)
                if not data:
                    continue          # heartbeat comment
                e = json.loads(data)
                out.append((e["id"], e["stage"], e["progress"]))
                if stop_after and len(out) >= stop_after:
                    return


def main():
    clip = Path("output/tex_src.mp4")
    if not clip.exists():
        print("output/tex_src.mp4 kerak -- avval demo_two_phase.py ni ishga tushiring")
        return

    with patch("pipeline.transcribe", return_value=WORDS):
        from api import app
        client = TestClient(app)

        with open(clip, "rb") as f:
            pid = client.post("/api/projects",
                              files={"file": ("stream.mp4", f, "video/mp4")}).json()["project_id"]

        seen: list = []
        t = threading.Thread(target=read_stream, args=(client, pid, seen), daemon=True)
        t.start()

        for _ in range(60):
            if client.get(f"/api/projects/{pid}").json()["status"] in ("ready", "error"):
                break
            time.sleep(0.5)

        client.post(f"/api/projects/{pid}/render", json={})
        t.join(timeout=120)

    print("SSE orqali kelgan bosqichlar:")
    for eid, stage, prog in seen:
        bar = "" if prog is None else f"  {'#' * int(prog * 20):<20} {prog * 100:5.1f}%"
        print(f"  [{eid:>3}] {stage:<11}{bar}")

    # Reconnect: ask for everything after the 3rd event and check the ids line up.
    resume_from = seen[2][0]
    replay: list = []
    with patch("pipeline.transcribe", return_value=WORDS):
        from api import app
        read_stream(TestClient(app), pid, replay, last_event_id=resume_from)

    expected = [e[0] for e in seen if e[0] > resume_from]
    got = [e[0] for e in replay]
    print(f"\nqayta ulanish (id>{resume_from}): {len(got)} hodisa qaytarildi")
    print(f"  yo'qotishsizmi: {got == expected}")


if __name__ == "__main__":
    main()
