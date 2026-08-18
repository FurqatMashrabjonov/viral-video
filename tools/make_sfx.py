"""Generate placeholder sound effects with ffmpeg's own synths -- self-made, CC0,
same reasoning as tools/make_lut.py: no scraped audio with unclear licensing.

Run: .venv/bin/python tools/make_sfx.py
"""
import subprocess
from pathlib import Path

OUT_DIR = Path("sfx")
SR = 48000

# Each entry is a lavfi source plus the filter chain that shapes it.
RECIPES = {
    # short bright blip -- lands on an emphasised word
    "pop": (
        f"sine=frequency=660:duration=0.10:sample_rate={SR}",
        "afade=t=out:st=0.012:d=0.085,volume=0.9",
    ),
    # airy swell -- reads as motion, pairs with a punch-in
    "whoosh": (
        # seeded: anoisesrc is otherwise different on every render, which would
        # break the measure-then-normalise pass below and make builds unrepeatable
        f"anoisesrc=color=brown:duration=0.34:sample_rate={SR}:amplitude=0.7:seed=42",
        "bandpass=f=1100:width_type=o:w=2.2,"
        "afade=t=in:st=0:d=0.16,afade=t=out:st=0.16:d=0.18,volume=1.4",
    ),
    # two-tone chime -- for a number or a result
    "ding": (
        f"sine=frequency=990:duration=0.45:sample_rate={SR}",
        "afade=t=out:st=0.03:d=0.42,volume=0.7",
    ),
}


TARGET_PEAK_DB = -6.0  # every effect lands at the same headroom, whatever its synth


def _render(source: str, chain: str, path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", source,
         "-af", chain, "-ac", "1", "-ar", str(SR), str(path)],
        check=True, capture_output=True,
    )


def measure(path: Path) -> tuple[float, float]:
    """Peak and RMS in dB, so a silent or clipping file is caught without listening."""
    out = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "astats=measure_overall=Peak_level+RMS_level",
         "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    peak = rms = float("nan")
    for line in out.splitlines():
        if "Peak level dB" in line:
            peak = float(line.split(":")[-1].strip())
        elif "RMS level dB" in line:
            rms = float(line.split(":")[-1].strip())
    return peak, rms


def build(name: str, source: str, chain: str) -> Path:
    """Render once to find the peak, then again with the gain that hits the target.

    Without this the synths come out 20+ dB apart, and a mix level tuned for one
    effect leaves the others inaudible under speech.
    """
    path = OUT_DIR / f"{name}.wav"
    _render(source, chain, path)
    peak, _ = measure(path)
    _render(source, f"{chain},volume={TARGET_PEAK_DB - peak:.2f}dB", path)
    return path


def main():
    OUT_DIR.mkdir(exist_ok=True)
    for name, (source, chain) in RECIPES.items():
        path = build(name, source, chain)
        peak, rms = measure(path)
        print(f"wrote {path}  (peak {peak:.1f} dB, RMS {rms:.1f} dB)")


if __name__ == "__main__":
    main()
