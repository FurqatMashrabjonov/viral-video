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


def build_broll_filter(broll: list[dict], broll_inputs: dict, width: int, height: int,
                       lut_path: str, lut_strength: float, source_label: str) -> str:
    """One full-frame cutaway per clip, chained onto `source_label`, each gated
    to its own time window. Returns a graph fragment ending in [pip].

    This is a real cut, not a PiP: the B-roll clip replaces the presenter
    frame entirely for its window, then the presenter frame resumes. Audio
    is untouched here -- broll inputs are only ever referenced as [idx:v],
    never [idx:a], so the narration (built purely from [0:a] in
    build_audio_filter) plays through the swap uninterrupted.

    Each B-roll input is trimmed to its own on-screen window length. Pexels
    source clips almost always outlast the ~1.6s window they're shown for; a
    downloaded clip longer than the main video makes ffmpeg's overlay treat
    IT as the long pole and freeze-repeat the main video's last frame past
    its real end, stretching total output duration. Trimming first keeps the
    main video the longer input, so total duration is governed by it alone.

    Every clip gets the SAME LUT at the SAME strength as the presenter frame,
    graded exactly like the main picture's own grade step (split, lut3d,
    blend) -- an ungraded insert would read as visibly colder/flatter than
    everything around it.
    """
    if not broll or not broll_inputs:
        return f"[{source_label}]copy[pip]"

    parts = []
    current = source_label
    for i, clip in enumerate(broll):
        idx = broll_inputs[i]
        out = f"pip{i}"
        dur = clip["end"] - clip["start"]
        parts.append(
            f"[{idx}:v]trim=duration={dur:.3f},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1[br{i}raw]"
            f";[br{i}raw]split=2[br{i}o][br{i}f]"
            f";[br{i}f]lut3d=file='{lut_path}'[br{i}g]"
            f";[br{i}o][br{i}g]blend=all_mode=normal:all_opacity={lut_strength}[br{i}]"
            f";[{current}][br{i}]overlay=x=0:y=0:enable='between(t,{clip['start']},{clip['end']})'[{out}]"
        )
        current = out
    parts.append(f"[{current}]copy[pip]")
    return ";".join(parts)


def build_video_filter(eq: dict, lut_path: str, ass_path: str | None, zoom: str = "",
                       lut_strength: float = LUT_OPACITY, denoise: bool = True,
                       vignette: bool = True, grade: bool = True, broll_graph: str = "") -> str:
    head = "hqdn3d=2:1.5:3:3," if denoise else ""
    graph = (
        f"[0:v]{head}eq=brightness={eq['brightness']}:contrast={eq['contrast']}[eqd]"
    )

    if grade and lut_strength > 0:
        graph += (
            f";[eqd]split=2[orig][forlut]"
            f";[forlut]lut3d=file='{lut_path}'[graded]"
            f";[orig][graded]blend=all_mode=normal:all_opacity={lut_strength}[blended]"
        )
    else:
        graph += ";[eqd]copy[blended]"

    # Zoom sits after the grade but before B-roll: a punch-in must not also
    # scale/crop the PiP window, so B-roll composites onto the already-zoomed
    # frame. Vignette and captions come last, over the final composited picture.
    graph += f";[blended]{zoom}[zoomed]" if zoom else ";[blended]copy[zoomed]"
    graph += ";" + (broll_graph or "[zoomed]copy[pip]")
    graph += ";[pip]vignette=PI/6[v_graded]" if vignette else ";[pip]copy[v_graded]"

    if ass_path:
        graph += f";[v_graded]ass='{ass_path}':fontsdir='{FONTS_DIR}'[vout]"
    else:
        graph += ";[v_graded]copy[vout]"
    return graph


SFX_DIR = Path("sfx")
SFX_VOLUME = 0.35  # well under speech; these punctuate, they don't compete


def build_audio_filter(sfx: list[dict] | None = None, sfx_inputs: dict | None = None,
                       volume: float = SFX_VOLUME, target_lufs: float = -16.0,
                       cleanup: bool = True) -> str:
    """Speech cleanup, then the effect bed mixed in, then loudness normalisation.

    Denoise/high-pass/compression apply to the voice only -- running them over the
    effects would dull them. loudnorm goes last so the whole mix, effects
    included, lands on the target rather than the effects pushing the true peak
    past it afterwards.
    """
    chain = ("afftdn=nr=12,highpass=f=80,"
             "acompressor=threshold=-18dB:ratio=3:attack=5:release=50" if cleanup else "anull")
    speech = f"[0:a]{chain}[speech]"
    norm = f"loudnorm=I={target_lufs:g}:TP=-1.5:LRA=11"

    if not sfx or not sfx_inputs:
        return f"{speech};[speech]{norm}[aout]"

    parts, labels = [speech], []
    for name, idx in sfx_inputs.items():
        times = [e["time"] for e in sfx if e["name"] == name]
        if not times:
            continue
        # One decoded copy of the file, split into as many voices as it is used.
        outs = "".join(f"[{name}{i}]" for i in range(len(times)))
        parts.append(f"[{idx}:a]asplit={len(times)}{outs}")
        for i, t in enumerate(times):
            label = f"{name}d{i}"
            parts.append(f"[{name}{i}]adelay={int(t * 1000)}:all=1,volume={volume}[{label}]")
            labels.append(f"[{label}]")

    # normalize=0 is essential: amix otherwise divides every input by the input
    # count, which would quietly drop the speech by 1/N.
    parts.append(
        f"[speech]{''.join(labels)}amix=inputs={1 + len(labels)}:normalize=0:duration=first[mixed]"
    )
    parts.append(f"[mixed]{norm}[aout]")
    return ";".join(parts)


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
            progress_cb=None, zooms: list[dict] | None = None, sfx: list[dict] | None = None,
            lut_strength: float = LUT_OPACITY, denoise: bool = True, vignette: bool = True,
            grade: bool = True, sfx_volume: float = SFX_VOLUME, target_lufs: float = -16.0,
            audio_cleanup: bool = True, seek_start: float | None = None,
            seek_duration: float | None = None, broll: list[dict] | None = None):
    """broll entries are {"start", "end", "path"} -- path already resolved to a
    local file (pexels.fetch_clip, called by the caller) so this module stays
    ffmpeg-only and never touches the network."""
    mean_luma = measure_mean_luma(input_path)
    eq = adaptive_eq_params(mean_luma)
    w, h = get_video_dims(input_path)

    zoom = ""
    if zooms:
        zoom = build_zoom_filter(zooms, w, h, get_fps(input_path))

    # One -i per distinct effect file; asplit fans it out to each hit.
    sfx_args, sfx_inputs = [], {}
    for name in dict.fromkeys(e["name"] for e in sfx or []):
        path = SFX_DIR / f"{name}.wav"
        if not path.exists():
            print(f"[enhance] missing effect {path}, skipping it")
            continue
        # count inputs, not argv entries -- each -i contributes two of the latter
        sfx_inputs[name] = len(sfx_inputs) + 1
        sfx_args += ["-i", str(path)]
    usable = [e for e in (sfx or []) if e["name"] in sfx_inputs]

    # B-roll inputs come after sfx inputs in argv, so their stream index has to
    # start counting from there, not from 1.
    broll_args, broll_inputs, usable_broll = [], {}, []
    for clip in broll or []:
        path = clip.get("path")
        if not path or not Path(path).exists():
            print(f"[enhance] missing broll clip {path}, skipping it")
            continue
        broll_inputs[len(usable_broll)] = 1 + len(sfx_inputs) + len(usable_broll)
        broll_args += ["-i", path]
        usable_broll.append(clip)

    print(f"[enhance] mean luma={mean_luma:.1f} -> eq={eq}, "
          f"{len(zooms or [])} zooms, {len(usable)} sfx, {len(usable_broll)} broll")

    broll_graph = build_broll_filter(usable_broll, broll_inputs, w, h, lut_path, lut_strength, "zoomed")
    filter_complex = (
        build_video_filter(eq, lut_path, ass_path, zoom, lut_strength=lut_strength,
                           denoise=denoise, vignette=vignette, grade=grade, broll_graph=broll_graph)
        + ";"
        + build_audio_filter(usable, sfx_inputs, volume=sfx_volume,
                             target_lufs=target_lufs, cleanup=audio_cleanup)
    )
    # Segment previews seek into the source. The seek goes before -i so ffmpeg
    # fast-seeks to a keyframe and decodes forward, rather than decoding the
    # whole clip and throwing frames away.
    seek_args = []
    if seek_start is not None:
        seek_args = ["-ss", f"{seek_start:.3f}"]
    if seek_duration is not None:
        seek_args += ["-t", f"{seek_duration:.3f}"]
    cmd = [
        "ffmpeg", "-y", *seek_args, "-i", input_path, *sfx_args, *broll_args,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        output_path,
    ]
    total_duration = seek_duration or (get_duration(input_path) if progress_cb else None)
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
    p.add_argument("--plan", default=None, help="edit_plan.json -- zoom va sfx shundan olinadi")
    args = p.parse_args()

    zooms = sfx = None
    if args.plan:
        import json
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        zooms, sfx = plan.get("zooms"), plan.get("sfx")

    enhance(args.input, args.output, lut_path=args.lut, ass_path=args.ass, zooms=zooms, sfx=sfx)
    if args.compare:
        compare_path = str(Path(args.output).with_name(Path(args.output).stem + "_compare.mp4"))
        make_compare(args.input, args.output, compare_path)
