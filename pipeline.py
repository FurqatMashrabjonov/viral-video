"""Two phases, deliberately separate.

ingest()  runs once per uploaded video: probe, transcribe, normalise, plan.
          This is where ~98% of the cost lives (Scribe), so it must never run
          again just because the user changed a setting or fixed a typo.
render()  runs as often as the user likes: stored plan + settings -> mp4.

run_pipeline() still chains both for the existing single-shot callers.
"""
import resource
import shutil
import subprocess
import tempfile
from pathlib import Path

import db
from scribe import transcribe, COST_PER_MINUTE_USD
from normalize import normalize_words
from subtitles import build_ass, load_style
from enhance import enhance, get_video_dims, get_duration, get_fps
from analyze import build_edit_plan, llm_enrich, plan_zooms, plan_sfx
from cost import log_cost
from settings import merge as merge_settings, defaults as default_settings

STYLES_DIR = Path("styles")
LUTS_DIR = Path("luts")

DEFAULT_SETTINGS = default_settings()


def _apply_style_settings(style: dict, settings: dict) -> dict:
    """Scale the style's own numbers by the user's multipliers, and drop the
    highlight config entirely when highlighting is switched off -- subtitles.py
    emits no keyword tags when neither key is present."""
    style = {
        **style,
        "font_size": round(style["font_size"] * settings["font_scale"]),
        "margin_v": round(style.get("margin_v", 180) * settings["margin_scale"]),
    }
    if not settings["keyword_highlight"]:
        style.pop("keyword_color", None)
        style.pop("keyword_box", None)
    return style


def _extract_audio(video_path: str, out_wav: str):
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", out_wav],
        check=True, capture_output=True,
    )


def _cpu_seconds() -> float:
    """CPU time spent in ffmpeg/ffprobe child processes so far (user+sys)."""
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


# --- phase A: once per video ------------------------------------------------

def ingest(source_path: str, name: str | None = None, language_code: str = "uzb",
           enrich: bool = True, stage_cb=None, project_id: str | None = None) -> str:
    """Probe, transcribe and plan a newly uploaded video. Returns the project id.

    An upload handler that must answer the request before the work finishes can
    create the row itself and pass the id in.
    """
    db.init()
    if project_id is None:
        project_id = db.create_project(name or Path(source_path).stem, source_path)

    def stage(s, message=None):
        db.add_event(project_id, s, message=message)
        if stage_cb:
            stage_cb(s)

    try:
        stage("probe")
        width, height = get_video_dims(source_path)
        duration, fps = get_duration(source_path), get_fps(source_path)
        db.update_project(project_id, duration=duration, width=width, height=height, fps=fps)

        with tempfile.TemporaryDirectory() as tmp:
            stage("audio")
            audio_path = str(Path(tmp) / "audio.wav")
            _extract_audio(source_path, audio_path)

            stage("transcribe")
            words = normalize_words(transcribe(audio_path, language_code=language_code))

        stage("plan")
        plan = build_edit_plan(words, duration, cut_silence=False)
        if enrich:
            stage("enrich")
            plan = llm_enrich(plan)

        db.save_plan(project_id, plan)
        db.set_project_status(project_id, "ready")
    except Exception as e:
        db.set_project_status(project_id, "error", str(e))
        stage("error", message=str(e))
        raise

    log_cost(project_id, duration / 60, round(duration / 60 * COST_PER_MINUTE_USD, 4), 0.0)
    stage("ready")
    return project_id


# --- phase B: as often as the user likes ------------------------------------

def render(project_id: str, settings: dict | None = None, progress_cb=None,
           stage_cb=None, render_id: str | None = None,
           segment: tuple[float, float] | None = None) -> str:
    """Render the stored plan. Never touches Scribe, so a re-render is CPU only.

    With `segment=(t0, t1)` only that slice of the source is rendered, on a
    timeline shifted to start at zero: the preview the editor plays after a
    correction goes through the exact same filter path as the full render, so it
    cannot drift from what the final video will show.

    A caller that needs the id before the work starts (an HTTP handler wanting
    to hand the client something to poll) can create the row itself and pass it
    in.
    """
    db.init()
    project = db.get_project(project_id)
    if not project:
        raise ValueError(f"unknown project {project_id}")
    plan = db.get_plan(project_id)
    if not plan:
        raise ValueError(f"project {project_id} has no plan yet")

    settings = merge_settings(settings)
    if render_id is None:
        render_id = db.create_render(project_id, settings)

    def stage(s, progress=None, message=None):
        db.add_event(project_id, s, progress=progress, message=message, render_id=render_id)
        if stage_cb:
            stage_cb(s)

    out_dir = db.MEDIA_DIR / project_id
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{render_id}{'_seg' if segment else ''}.mp4"
    ass_path = out_dir / f"{render_id}{'_seg' if segment else ''}.ass"

    cpu_start = _cpu_seconds()
    try:
        db.update_render(render_id, status="rendering")

        stage("subtitles")
        burn_ass = None

        words = plan["words"]
        hook = plan.get("hook")
        t0 = 0.0
        if segment:
            t0, t1 = segment
            words = [w for w in words if w["end"] > t0 and w["start"] < t1]
            words = [{**w, "start": round(w["start"] - t0, 3),
                      "end": round(w["end"] - t0, 3)} for w in words]
            hook = ({**hook, "start": 0.0, "end": min(hook["end"], t1) - t0}
                    if hook and hook["start"] < t1 else None)

        if settings["captions"]:
            style = _apply_style_settings(
                load_style(str(STYLES_DIR / f"{settings['style']}.yaml")), settings
            )
            if hook and settings["hook"]:
                hook = {**hook, "end": hook.get("start", 0.0) + settings["hook_duration"]}
            else:
                hook = None
            build_ass(words, style, project["width"], project["height"],
                      hook=hook).save(str(ass_path))
            burn_ass = str(ass_path)

        # Zoom and sfx placement is a pure function of the words plus a few
        # numbers, so it is recomputed here from the current settings rather
        # than read from the plan. Changing the spacing costs nothing.
        # Placement is computed from the same (possibly shifted) word list, so a
        # segment preview shows zooms and effects exactly as the full render
        # would place them around that moment.
        zooms = sfx = None
        if settings["zoom"]:
            zooms = plan_zooms(words, [], spacing=settings["zoom_spacing"],
                               duration=settings["zoom_duration"], scale=settings["zoom_scale"])
        if settings["sfx"]:
            sfx = plan_sfx(words, min_spacing=settings["sfx_spacing"])

        stage("render")

        last_notch = -1

        def report(fraction: float):
            # The render owns its own row, so progress lands in the database
            # whether or not the caller passed a callback.
            nonlocal last_notch
            db.update_render(render_id, progress=round(fraction, 4))
            # ffmpeg reports several times a second; journalling every one of
            # those would bury the stage events. One row per 5% is enough to
            # drive a progress bar.
            notch = int(fraction * 20)
            if notch > last_notch:
                last_notch = notch
                db.add_event(project_id, "render", progress=round(fraction, 4),
                             render_id=render_id)
            if progress_cb:
                progress_cb(fraction)

        enhance(
            project["source_path"], str(output_path),
            lut_path=str(LUTS_DIR / f"{settings['lut']}.cube"),
            ass_path=burn_ass,
            progress_cb=report,
            zooms=zooms,
            sfx=sfx,
            seek_start=t0 if segment else None,
            seek_duration=round(t1 - t0, 3) if segment else None,
            lut_strength=settings["lut_strength"],
            denoise=settings["denoise"],
            vignette=settings["vignette"],
            grade=settings["grade"],
            sfx_volume=settings["sfx_volume"],
            target_lufs=settings["target_lufs"],
            audio_cleanup=settings["audio_cleanup"],
        )
        db.update_render(
            render_id, status="done", progress=1.0,
            output_path=str(output_path), ass_path=burn_ass,
        )
    except Exception as e:
        db.update_render(render_id, status="error", error=str(e))
        stage("error", message=str(e))
        raise

    # Scribe minutes are zero here on purpose: this phase re-uses the stored
    # transcript, so a re-render costs CPU only.
    log_cost(render_id, 0.0, 0.0, _cpu_seconds() - cpu_start)
    stage("done")
    return render_id


# --- both, for single-shot callers ------------------------------------------

def run_pipeline(input_path: str, style_name: str = "warm_karaoke", language_code: str = "uzb",
                 lut_path: str | None = None, progress_cb=None, enrich: bool = True,
                 sfx: bool = True) -> dict:
    """Ingest then render in one call. Kept so existing callers keep working."""
    db.init()
    db.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    stored = db.MEDIA_DIR / f"src_{db.new_id()}{Path(input_path).suffix}"
    shutil.copy(input_path, stored)

    project_id = ingest(str(stored), name=Path(input_path).stem,
                        language_code=language_code, enrich=enrich)
    overrides = {"style": style_name, "sfx": sfx}
    if lut_path:
        overrides["lut"] = Path(lut_path).stem
    render_id = render(project_id, overrides, progress_cb=progress_cb)

    project, plan, r = db.get_project(project_id), db.get_plan(project_id), db.get_render(render_id)
    return {
        "project_id": project_id,
        "render_id": render_id,
        "output_path": r["output_path"],
        "ass_path": r["ass_path"],
        "duration_sec": round(project["duration"], 2),
        "word_count": len(plan["words"]),
        "hook": plan["hook"]["text"] if plan.get("hook") else None,
    }
