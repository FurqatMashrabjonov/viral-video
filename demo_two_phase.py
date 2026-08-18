"""Phase 1 demo: ingest once, render three times over the API, editing in between.
Scribe is mocked so this costs nothing. Run: .venv/bin/python demo_two_phase.py
"""
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import db
from test_pipeline_smoke import MOCK_WORDS, make_smoke_clip


def wait_render(client, render_id, timeout=90):
    for _ in range(timeout):
        row = client.get(f"/api/renders/{render_id}").json()
        if row["status"] in ("done", "error"):
            return row
        time.sleep(1)
    raise TimeoutError(render_id)


def main():
    clip = Path("output/demo_src.mp4")
    clip.parent.mkdir(exist_ok=True)
    make_smoke_clip(clip)

    with patch("pipeline.transcribe", return_value=MOCK_WORDS) as scribe:
        from api import app
        client = TestClient(app)

        with open(clip, "rb") as f:
            created = client.post("/api/projects",
                                  files={"file": ("demo.mp4", f, "video/mp4")}).json()
        project_id = created["project_id"]
        print(f"POST /api/projects -> {project_id[:8]} ingesting")

        for _ in range(60):
            project = client.get(f"/api/projects/{project_id}").json()
            if project["status"] in ("ready", "error"):
                break
            time.sleep(1)
        print(f"project {project_id[:8]} -> {project['status']}, "
              f"scribe chaqiruvlari: {scribe.call_count}")

        detail = project
        print("transkript:", [w["word"] for w in detail["plan"]["words"]])

        # 1. default render
        rid = client.post(f"/api/projects/{project_id}/render", json={}).json()["render_id"]
        print(f"\nrender 1 (standart)  -> {wait_render(client, rid)['status']}")

        # 2. same plan, different settings -- no Scribe
        rid = client.post(f"/api/projects/{project_id}/render",
                          json={"style": "bold_pop", "zoom": False}).json()["render_id"]
        print(f"render 2 (bold_pop, zoom o'chiq) -> {wait_render(client, rid)['status']}")

        # 3. edit a word, render again -- still no Scribe
        plan = detail["plan"]
        plan["words"][0]["word"] = "Assalom"
        client.put(f"/api/projects/{project_id}/plan", json=plan)
        rid = client.post(f"/api/projects/{project_id}/render", json={}).json()["render_id"]
        row = wait_render(client, rid)
        print(f"render 3 (so'z tuzatilgan) -> {row['status']}")

        ass = Path(row["ass_path"]).read_text(encoding="utf-8")
        print(f"  ASS ichida 'Assalom': {'Assalom' in ass}")

        print(f"\nJAMI Scribe chaqiruvlari: {scribe.call_count}  (3 render, 1 tahrir)")
        print(f"renderlar: {len(db.list_renders(project_id))}")


if __name__ == "__main__":
    main()
