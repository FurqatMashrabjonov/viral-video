"""End-to-end smoke test on a 5s synthetic clip. Scribe is mocked -> no API credits spent.
Run: .venv/bin/python test_pipeline_smoke.py
"""
import subprocess
from pathlib import Path
from unittest.mock import patch

from pipeline import run_pipeline

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


def test_pipeline_smoke():
    clip = Path("output/smoke_input.mp4")
    clip.parent.mkdir(exist_ok=True)
    make_smoke_clip(clip)

    with patch("pipeline.transcribe", return_value=MOCK_WORDS):
        metadata = run_pipeline(str(clip), style_name="warm_karaoke")

    assert Path(metadata["output_path"]).exists(), "output video missing"
    assert Path(metadata["output_path"]).stat().st_size > 0, "output video is empty"
    assert Path(metadata["ass_path"]).exists(), "ASS subtitle file missing"
    assert metadata["word_count"] == len(MOCK_WORDS)
    assert metadata["duration_sec"] > 0
    assert metadata["cost"]["total_cost_usd"] >= 0
    assert Path("logs/cost_log.jsonl").exists(), "cost log not written"


if __name__ == "__main__":
    test_pipeline_smoke()
    print("PASS test_pipeline_smoke")
