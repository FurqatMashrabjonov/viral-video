"""Milestone 2 end-to-end demo: normalize -> ASS -> ffmpeg burn.
Uses a synthetic word list (no live Scribe call) on a synthetic 9:16 background.
Run: .venv/bin/python demo_milestone2.py
"""
import subprocess
import sys
from pathlib import Path

from normalize import normalize_words
from subtitles import build_ass, load_style

WIDTH, HEIGHT = 1080, 1920
OUT_DIR = Path("output")
FONTS_DIR = Path("fonts").resolve()

# raw words as Scribe might return them: mixed apostrophes + Uzbek-Russian code-switch
RAW_WORDS = [
    {"word": "Assalomu", "start": 0.20, "end": 0.65},
    {"word": "alaykum,", "start": 0.65, "end": 1.10},
    {"word": "bugun", "start": 1.20, "end": 1.55},
    {"word": "o`zbek", "start": 1.55, "end": 1.95},
    {"word": "tilida", "start": 1.95, "end": 2.35},
    {"word": "gaplashamiz", "start": 2.35, "end": 3.00},
    {"word": "va", "start": 3.10, "end": 3.25},
    {"word": "spasibo", "start": 3.25, "end": 3.70},
    {"word": "aytamiz,", "start": 3.70, "end": 4.20},
    {"word": "G’isht", "start": 4.30, "end": 4.75},
    {"word": "ko'chasida", "start": 4.75, "end": 5.35},
    {"word": "пожалуйста", "start": 5.35, "end": 6.00},
]


def make_background(path: Path, duration: float):
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=gray:s={WIDTH}x{HEIGHT}:d={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True, capture_output=True,
    )


def burn(bg_path: Path, ass_path: Path, out_path: Path):
    vf = f"ass={ass_path}:fontsdir={FONTS_DIR}"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(bg_path), "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)],
        check=True, capture_output=True,
    )


def main():
    OUT_DIR.mkdir(exist_ok=True)
    words = normalize_words(RAW_WORDS)
    print("normalized words:", [w["word"] for w in words])

    duration = words[-1]["end"] + 0.5
    bg_path = OUT_DIR / "bg.mp4"
    make_background(bg_path, duration)

    for style_name in ["warm_karaoke", "bold_pop"]:
        style = load_style(f"styles/{style_name}.yaml")
        subs = build_ass(words, style, WIDTH, HEIGHT)
        ass_path = OUT_DIR / f"{style_name}.ass"
        subs.save(str(ass_path))
        out_path = OUT_DIR / f"test_{style_name}.mp4"
        burn(bg_path, ass_path, out_path)
        print(f"wrote {ass_path} and {out_path}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(e.stderr.decode(errors="replace"), file=sys.stderr)
        raise
