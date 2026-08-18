"""Milestone 3 end-to-end demo: synthetic dark+noisy clip -> enhance() -> compare.
Run: .venv/bin/python demo_milestone3.py
"""
import subprocess
from pathlib import Path

from enhance import enhance, make_compare

OUT_DIR = Path("output")
WIDTH, HEIGHT, DURATION = 1080, 1920, 6


def make_synthetic_input(path: Path):
    # dark background (to exercise the brightness-lift path) + voice-ish tone + hum noise
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=0x202020:s={WIDTH}x{HEIGHT}:d={DURATION}",
            "-f", "lavfi", "-i", f"sine=frequency=220:duration={DURATION}",
            "-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude=0.06:duration={DURATION}",
            "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=shortest[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(path),
        ],
        check=True, capture_output=True,
    )


def main():
    OUT_DIR.mkdir(exist_ok=True)
    input_path = OUT_DIR / "m3_input.mp4"
    output_path = OUT_DIR / "m3_enhanced.mp4"
    make_synthetic_input(input_path)

    ass_path = OUT_DIR / "warm_karaoke.ass"  # reuse milestone 2 output
    enhance(str(input_path), str(output_path), ass_path=str(ass_path) if ass_path.exists() else None)
    make_compare(str(input_path), str(output_path), str(OUT_DIR / "m3_compare.mp4"))


if __name__ == "__main__":
    main()
