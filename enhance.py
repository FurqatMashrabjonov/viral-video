"""Audio cleanup + color grade (CPU only). One filter_complex, ffmpeg does the work.

Video: hqdn3d -> eq (luma-adaptive) -> lut3d (blended ~60%) -> vignette -> [ass burn]
Audio: afftdn -> highpass 80Hz -> acompressor -> loudnorm -16 LUFS / -1.5 dBTP
"""
import argparse
import re
import subprocess
from pathlib import Path

DEFAULT_LUT = "luts/warm_standard.cube"
LUT_OPACITY = 0.6  # never 100% per spec
FONTS_DIR = str(Path("fonts").resolve())


def measure_mean_luma(video_path: str, sample_every: int = 15) -> float:
    """Mean luma (0-255) sampled via ffprobe/signalstats, no extra deps."""
    cmd = [
        "ffprobe", "-v", "error",
        "-f", "lavfi",
        "-i", f"movie={video_path},select=not(mod(n\\,{sample_every})),signalstats",
        "-show_entries", "frame_tags=lavfi.signalstats.YAVG",
        "-of", "default=nokey=1:noprint_wrappers=1",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    values = [float(v) for v in result.stdout.split() if re.match(r"^[\d.]+$", v)]
    if not values:
        return 128.0
    return sum(values) / len(values)


def get_video_dims(path: str) -> tuple[int, int]:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split("x")
    return int(w), int(h)


def get_fps(path: str) -> float:
    """zoompan re-times its output, so it has to be handed the source rate."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate", "-of", "default=nokey=1:noprint_wrappers=1", path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    num, _, den = out.partition("/")
    return float(num) / float(den or 1)


def get_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1", path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def adaptive_eq_params(mean_luma: float) -> dict:
    """Gentle exposure lift for dark clips, none/negative for already-bright ones."""
    target = 120.0
    diff = target - mean_luma
    brightness = max(-0.08, min(0.08, diff / 255 * 0.4))
    contrast = 1.05 if mean_luma < 150 else 1.0
    return {"brightness": round(brightness, 4), "contrast": contrast}


ZOOM_RAMP = 0.22  # seconds to ease in and back out of a punch-in


def build_zoom_expr(zooms: list[dict], ramp: float = ZOOM_RAMP) -> str:
    """One zoompan `z` expression covering every punch-in.

    Each window ramps 1 -> scale, holds, and ramps back to 1:
        1 + (k-1) * min(1, min((t-start)/ramp, (end-t)/ramp))
    which is 1 at both edges and k across the middle -- no nesting needed inside
    a window, so the chain stays one `if` per zoom.
    """
    expr = "1"
    for z in reversed(zooms):  # innermost else first
        s, e, k = z["start"], z["end"], z["scale"]
        ramped = f"1+{k - 1:.4f}*min(1,min((in_time-{s})/{ramp},({e}-in_time)/{ramp}))"
        expr = f"if(between(in_time,{s},{e}),{ramped},{expr})"
    return expr


def build_zoom_filter(zooms: list[dict], width: int, height: int, fps: float) -> str:
    """Centre-anchored punch-in. No face tracking: the input is already a framed
    9:16 talking head, so the subject is where the crop centre already is."""
    if not zooms:
        return ""
    return (
        f"zoompan=z='{build_zoom_expr(zooms)}':d=1"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={width}x{height}:fps={fps:g}"
    )


def build_video_filter(eq: dict, lut_path: str, ass_path: str | None, zoom: str = "") -> str:
    graph = (
        f"[0:v]hqdn3d=2:1.5:3:3,eq=brightness={eq['brightness']}:contrast={eq['contrast']}[eqd];"
        f"[eqd]split=2[orig][forlut];"
        f"[forlut]lut3d=file='{lut_path}'[graded];"
        f"[orig][graded]blend=all_mode=normal:all_opacity={LUT_OPACITY}[blended]"
    )
    # Zoom sits after the grade but before the vignette and the captions: the
    # vignette belongs to the frame edge, and captions must not scale with the
    # picture.
    graph += f";[blended]{zoom}[zoomed]" if zoom else ";[blended]copy[zoomed]"
    graph += ";[zoomed]vignette=PI/6[v_graded]"

    if ass_path:
        graph += f";[v_graded]ass='{ass_path}':fontsdir='{FONTS_DIR}'[vout]"
    else:
        graph += ";[v_graded]copy[vout]"
    return graph


def build_audio_filter() -> str:
    return (
        "[0:a]afftdn=nr=12,"
        "highpass=f=80,"
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,"
        "loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )


def _run_ffmpeg(cmd: list[str], total_duration: float | None = None, progress_cb=None):
    """Runs ffmpeg; streams -progress pipe:1 into progress_cb(fraction) if given."""
    if progress_cb is None or not total_duration:
        subprocess.run(cmd, check=True, capture_output=True)
        return

    cmd = cmd[:-1] + ["-progress", "pipe:1", "-nostats"] + cmd[-1:]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        if line.startswith("out_time_ms="):
            try:
                ms = int(line.strip().split("=")[1])
                progress_cb(min(1.0, max(0.0, ms / 1_000_000 / total_duration)))
            except ValueError:
                pass
    proc.wait()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, stderr=proc.stderr.read().encode())
    progress_cb(1.0)


def enhance(input_path: str, output_path: str, lut_path: str = DEFAULT_LUT, ass_path: str | None = None,
            progress_cb=None, zooms: list[dict] | None = None):
    mean_luma = measure_mean_luma(input_path)
    eq = adaptive_eq_params(mean_luma)

    zoom = ""
    if zooms:
        w, h = get_video_dims(input_path)
        zoom = build_zoom_filter(zooms, w, h, get_fps(input_path))
    print(f"[enhance] mean luma={mean_luma:.1f} -> eq={eq}, {len(zooms or [])} zooms")

    filter_complex = build_video_filter(eq, lut_path, ass_path, zoom) + ";" + build_audio_filter()
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        output_path,
    ]
    total_duration = get_duration(input_path) if progress_cb else None
    _run_ffmpeg(cmd, total_duration=total_duration, progress_cb=progress_cb)
    print(f"[enhance] wrote {output_path}")


def make_compare(original_path: str, enhanced_path: str, out_path: str):
    filter_complex = "[0:v]scale=540:-2[l];[1:v]scale=540:-2[r];[l][r]hstack=inputs=2[v]"
    cmd = [
        "ffmpeg", "-y", "-i", original_path, "-i", enhanced_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[enhance] wrote compare {out_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--lut", default=DEFAULT_LUT)
    p.add_argument("--ass", default=None)
    p.add_argument("--compare", action="store_true")
    p.add_argument("--plan", default=None, help="edit_plan.json -- zoom nuqtalari shundan olinadi")
    args = p.parse_args()

    zooms = None
    if args.plan:
        import json
        zooms = json.loads(Path(args.plan).read_text(encoding="utf-8")).get("zooms")

    enhance(args.input, args.output, lut_path=args.lut, ass_path=args.ass, zooms=zooms)
    if args.compare:
        compare_path = str(Path(args.output).with_name(Path(args.output).stem + "_compare.mp4"))
        make_compare(args.input, args.output, compare_path)
