"""End-to-end smoke test on a 5s synthetic clip. Scribe is mocked -> no API credits spent.
Run: .venv/bin/python test_pipeline_smoke.py
"""
import subprocess
from pathlib import Path
from unittest.mock import patch

import db
from pipeline import run_pipeline, ingest, render, re_enrich

MOCK_WORDS = [
    {"word": "Salom", "start": 0.2, "end": 0.6},
    {"word": "o`zbekcha", "start": 0.6, "end": 1.2},
    {"word": "sinov", "start": 1.3, "end": 1.7},
]


def make_smoke_clip(path: Path):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=gray:s=1080x1920:d=5",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(path),
        ],
        check=True, capture_output=True,
    )


def _clip() -> Path:
    clip = Path("output/smoke_input.mp4")
    clip.parent.mkdir(exist_ok=True)
    if not clip.exists():
        make_smoke_clip(clip)
    return clip


def test_pipeline_smoke():
    # enrich=False keeps the Gemini call out of CI, same reason Scribe is mocked
    with patch("pipeline.transcribe", return_value=MOCK_WORDS):
        metadata = run_pipeline(str(_clip()), style_name="warm_karaoke", enrich=False)

    assert Path(metadata["output_path"]).exists(), "output video missing"
    assert Path(metadata["output_path"]).stat().st_size > 0, "output video is empty"
    assert Path(metadata["ass_path"]).exists(), "ASS subtitle file missing"
    assert metadata["word_count"] == len(MOCK_WORDS)
    assert metadata["duration_sec"] > 0
    assert Path("logs/cost_log.jsonl").exists(), "cost log not written"


def test_rerender_never_calls_scribe():
    """The whole point of splitting ingest from render: transcription is ~98% of
    the cost, so changing a setting must not pay it again."""
    with patch("pipeline.transcribe", return_value=MOCK_WORDS) as scribe:
        project_id = ingest(str(_clip()), enrich=False)
        assert scribe.call_count == 1

        render(project_id, {"zoom": False, "sfx": False})
        render(project_id, {"style": "bold_pop"})
        assert scribe.call_count == 1, "a re-render went back to Scribe"


def test_render_settings_are_stored_with_the_render():
    with patch("pipeline.transcribe", return_value=MOCK_WORDS):
        project_id = ingest(str(_clip()), enrich=False)
        render_id = render(project_id, {"zoom": False, "style": "bold_pop"})

    row = db.get_render(render_id)
    assert row["status"] == "done"
    assert row["settings"]["zoom"] is False
    assert row["settings"]["style"] == "bold_pop"
    assert Path(row["output_path"]).exists()


def test_plan_survives_and_is_reused():
    with patch("pipeline.transcribe", return_value=MOCK_WORDS):
        project_id = ingest(str(_clip()), enrich=False)

    plan = db.get_plan(project_id)
    assert plan is not None
    assert [w["word"] for w in plan["words"]] == ["Salom", "oʻzbekcha", "sinov"]
    assert db.get_project(project_id)["status"] == "ready"


def test_editing_the_plan_changes_the_next_render():
    """Proves the edit path works end to end without re-transcribing."""
    with patch("pipeline.transcribe", return_value=MOCK_WORDS) as scribe:
        project_id = ingest(str(_clip()), enrich=False)

        plan = db.get_plan(project_id)
        plan["words"][0]["word"] = "Assalom"
        db.save_plan(project_id, plan)

        render_id = render(project_id)
        assert scribe.call_count == 1

    ass = Path(db.get_render(render_id)["ass_path"]).read_text(encoding="utf-8")
    assert "Assalom" in ass and "Salom{" not in ass


def test_segment_render_crops_and_shifts():
    """The editor preview: a slice of the source through the exact same filter
    path, on a timeline that starts at zero."""
    with patch("pipeline.transcribe", return_value=MOCK_WORDS):
        project_id = ingest(str(_clip()), enrich=False)

    render_id = render(project_id, {"zoom": False, "sfx": False}, segment=(0.8, 2.2))
    row = db.get_render(render_id)
    assert row["status"] == "done"
    assert row["output_path"].endswith("_seg.mp4")

    from enhance import get_duration
    assert abs(get_duration(row["output_path"]) - 1.4) < 0.25

    ass = Path(row["ass_path"]).read_text(encoding="utf-8")
    # the word at 0.6-1.2 shifts to start at zero; the one before the slice is gone
    assert "oʻzbekcha" in ass
    assert "Salom" not in ass


FAKE_HOOK = {"text": "Yangi hook", "start": 0.0, "end": 3.0}


def test_re_enrich_never_calls_scribe():
    """The whole point: a project ingested without a hook (or before this field
    existed) can be enriched later without paying for transcription again."""
    with patch("pipeline.transcribe", return_value=MOCK_WORDS) as scribe:
        project_id = ingest(str(_clip()), enrich=False)
        assert db.get_plan(project_id)["hook"] is None

        with patch("pipeline.llm_enrich", return_value={**db.get_plan(project_id), "hook": FAKE_HOOK}):
            re_enrich(project_id)

        assert scribe.call_count == 1, "re-enrich went back to Scribe"


def test_re_enrich_persists_the_updated_plan():
    with patch("pipeline.transcribe", return_value=MOCK_WORDS):
        project_id = ingest(str(_clip()), enrich=False)

    with patch("pipeline.llm_enrich", return_value={**db.get_plan(project_id), "hook": FAKE_HOOK}):
        result = re_enrich(project_id)

    assert result["hook"]["text"] == "Yangi hook"
    assert db.get_plan(project_id)["hook"]["text"] == "Yangi hook"


def test_re_enrich_unknown_project_raises():
    try:
        re_enrich("no-such-project")
        assert False, "should have raised"
    except ValueError:
        pass


def test_re_enrich_without_a_plan_raises():
    project_id = db.create_project("no-plan-yet", "x.mp4")
    try:
        re_enrich(project_id)
        assert False, "should have raised"
    except ValueError:
        pass


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
    sys.exit(1 if failed else 0)
