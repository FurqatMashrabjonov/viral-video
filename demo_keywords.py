"""Keyword highlight + hook title, end to end: Gemini plan -> ASS -> ffmpeg burn.
Run: .venv/bin/python demo_keywords.py
"""
import subprocess
from pathlib import Path

from normalize import normalize_words
from analyze import build_edit_plan, llm_enrich
from subtitles import build_ass, load_style

WIDTH, HEIGHT = 1080, 1920
OUT = Path("output")
FONTS = str(Path("fonts").resolve())

RAW = [
    {"word": "Bugun", "start": 0.2, "end": 0.6}, {"word": "sizga", "start": 0.6, "end": 0.95},
    {"word": "biznesda", "start": 0.95, "end": 1.5}, {"word": "reklama", "start": 1.5, "end": 2.0},
    {"word": "byudjetini", "start": 2.0, "end": 2.6}, {"word": "qanday", "start": 2.6, "end": 3.0},
    {"word": "qilib", "start": 3.0, "end": 3.3}, {"word": "30", "start": 3.3, "end": 3.6},
    {"word": "foizga", "start": 3.6, "end": 4.1}, {"word": "kamaytirishni", "start": 4.1, "end": 4.9},
    {"word": "aytaman.", "start": 4.9, "end": 5.4},
    {"word": "Birinchi", "start": 7.0, "end": 7.5}, {"word": "qadam", "start": 7.5, "end": 7.9},
    {"word": "auditoriyani", "start": 7.9, "end": 8.6}, {"word": "segmentlash,", "start": 8.6, "end": 9.3},
    {"word": "ikkinchisi", "start": 9.3, "end": 9.9}, {"word": "konversiya", "start": 9.9, "end": 10.5},
    {"word": "voronkasini", "start": 10.5, "end": 11.1}, {"word": "tekshirish.", "start": 11.1, "end": 11.7},
]


def make_bg(path: Path, duration: float):
    """Mid-bright gradient -- the case where a caption without a box or outline fails."""
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"gradients=s={WIDTH}x{HEIGHT}:c0=0xB8C4D0:c1=0x6E5A48:d={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ], check=True, capture_output=True)


def burn(bg: Path, ass: Path, out: Path):
    subprocess.run([
        "ffmpeg", "-y", "-i", str(bg), "-vf", f"ass={ass}:fontsdir={FONTS}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ], check=True, capture_output=True)


def main():
    OUT.mkdir(exist_ok=True)
    plan = llm_enrich(build_edit_plan(normalize_words(RAW), source_duration=12.0))

    print("hook    :", plan["hook"]["text"] if plan["hook"] else "(yo'q)")
    print("keywords:", [w["word"] for w in plan["words"] if w["keyword"]])

    duration = plan["output_duration"] + 0.5
    bg = OUT / "kw_bg.mp4"
    make_bg(bg, duration)

    for name in ["warm_karaoke", "bold_pop"]:
        style = load_style(f"styles/{name}.yaml")
        ass = OUT / f"kw_{name}.ass"
        build_ass(plan["words"], style, WIDTH, HEIGHT, hook=plan["hook"]).save(str(ass))
        out = OUT / f"kw_{name}.mp4"
        burn(bg, ass, out)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
