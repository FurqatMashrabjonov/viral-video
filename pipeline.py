"""input.mp4 + style -> output.mp4, chaining Scribe -> normalize -> ASS -> enhance."""
import resource
import subprocess
import tempfile
from pathlib import Path

from scribe import transcribe, COST_PER_MINUTE_USD
from normalize import normalize_words
from subtitles import build_ass, load_style
from enhance import enhance, get_video_dims, get_duration
from analyze import build_edit_plan, llm_enrich, save_plan
from cost import log_cost

STYLES_DIR = Path("styles")
OUTPUT_DIR = Path("output")
DEFAULT_LUT = "luts/warm_standard.cube"


def _extract_audio(video_path: str, out_wav: str):
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", out_wav],
        check=True, capture_output=True,
    )


def _cpu_seconds() -> float:
    """CPU time spent in ffmpeg/ffprobe child processes so far (user+sys)."""
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


def run_pipeline(input_path: str, style_name: str = "warm_karaoke", language_code: str = "uzb",
                  lut_path: str | None = None, progress_cb=None, enrich: bool = True, sfx: bool = True) -> dict:
    OUTPUT_DIR.mkdir(exist_ok=True)
    job_stem = Path(input_path).stem
    output_path = OUTPUT_DIR / f"{job_stem}_out.mp4"
    ass_path = OUTPUT_DIR / f"{job_stem}.ass"

    cpu_start = _cpu_seconds()
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = str(Path(tmp) / "audio.wav")
        _extract_audio(input_path, audio_path)

        words = normalize_words(transcribe(audio_path, language_code=language_code))

        plan = build_edit_plan(words, get_duration(input_path), cut_silence=False)
        if enrich:
            plan = llm_enrich(plan)
        save_plan(plan, str(OUTPUT_DIR / f"{job_stem}_plan.json"))

        width, height = get_video_dims(input_path)
        style = load_style(str(STYLES_DIR / f"{style_name}.yaml"))
        subs = build_ass(plan["words"], style, width, height, hook=plan["hook"])
        subs.save(str(ass_path))

        enhance(
            input_path, str(output_path),
            lut_path=lut_path or DEFAULT_LUT,
            ass_path=str(ass_path),
            progress_cb=progress_cb,
            zooms=plan["zooms"],
            sfx=plan["sfx"] if sfx else None,
        )

    cpu_seconds = _cpu_seconds() - cpu_start
    duration = get_duration(input_path)
    scribe_minutes = duration / 60
    scribe_cost_usd = round(scribe_minutes * COST_PER_MINUTE_USD, 4)
    cost_entry = log_cost(job_stem, scribe_minutes, scribe_cost_usd, cpu_seconds)

    return {
        "output_path": str(output_path),
        "ass_path": str(ass_path),
        "duration_sec": round(duration, 2),
        "word_count": len(plan["words"]),
        "hook": plan["hook"]["text"] if plan["hook"] else None,
        "cost": cost_entry,
    }
