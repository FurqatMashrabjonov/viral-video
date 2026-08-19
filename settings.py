"""The one declaration of what a user can control.

Backend declares it, GET /api/schema serves it, the frontend draws controls from
it. Kept in a single place on purpose: a second hand-maintained list in the UI
drifts, and the failure mode is a control that appears to work but changes
nothing.

A field only appears here once the renderer actually honours it. `cut_silence`
is deliberately absent for that reason -- analyze.py can compute the cuts but
enhance.py does not apply them yet.
"""
from pathlib import Path

STYLES_DIR = Path("styles")
LUTS_DIR = Path("luts")


def _stems(directory: Path, pattern: str) -> list[str]:
    return sorted(p.stem for p in directory.glob(pattern))


def _fields() -> list[dict]:
    return [
        # --- subtitles ---
        {"key": "captions", "group": "Subtitr", "label": "Subtitr", "type": "bool", "default": True},
        {"key": "style", "group": "Subtitr", "label": "Uslub", "type": "select",
         "default": "warm_karaoke", "options": _stems(STYLES_DIR, "*.yaml"), "depends_on": "captions"},
        {"key": "font_scale", "group": "Subtitr", "label": "Shrift o'lchami", "type": "number",
         "default": 1.0, "min": 0.6, "max": 1.6, "step": 0.05, "depends_on": "captions"},
        {"key": "margin_scale", "group": "Subtitr", "label": "Pastdan masofa", "type": "number",
         "default": 1.0, "min": 0.3, "max": 2.5, "step": 0.05, "depends_on": "captions"},
        {"key": "keyword_highlight", "group": "Subtitr", "label": "Kalit so'z ajratish",
         "type": "bool", "default": True, "depends_on": "captions"},
        {"key": "emoji", "group": "Subtitr", "label": "Emoji taklif", "type": "bool",
         "default": True, "depends_on": "captions"},

        # --- hook ---
        {"key": "hook", "group": "Hook", "label": "Hook sarlavha", "type": "bool", "default": True},
        {"key": "hook_duration", "group": "Hook", "label": "Davomiyligi (s)", "type": "number",
         "default": 3.0, "min": 1.0, "max": 8.0, "step": 0.5, "depends_on": "hook"},

        # --- zoom ---
        {"key": "zoom", "group": "Zoom", "label": "Punch-in zoom", "type": "bool", "default": True},
        {"key": "zoom_scale", "group": "Zoom", "label": "Kuchi", "type": "number",
         "default": 1.15, "min": 1.02, "max": 1.5, "step": 0.01, "depends_on": "zoom"},
        {"key": "zoom_spacing", "group": "Zoom", "label": "Eng kam oraliq (s)", "type": "number",
         "default": 3.0, "min": 1.0, "max": 15.0, "step": 0.5, "depends_on": "zoom"},
        {"key": "zoom_duration", "group": "Zoom", "label": "Davomiyligi (s)", "type": "number",
         "default": 1.2, "min": 0.5, "max": 4.0, "step": 0.1, "depends_on": "zoom"},

        # --- sound effects ---
        {"key": "sfx", "group": "Effekt", "label": "Sound effect", "type": "bool", "default": True},
        {"key": "sfx_volume", "group": "Effekt", "label": "Ovoz balandligi", "type": "number",
         "default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05, "depends_on": "sfx"},
        {"key": "sfx_spacing", "group": "Effekt", "label": "Eng kam oraliq (s)", "type": "number",
         "default": 1.5, "min": 0.5, "max": 8.0, "step": 0.5, "depends_on": "sfx"},

        # --- colour ---
        {"key": "grade", "group": "Rang", "label": "Rang grading", "type": "bool", "default": True},
        {"key": "lut", "group": "Rang", "label": "LUT", "type": "select",
         "default": "warm_standard", "options": _stems(LUTS_DIR, "*.cube"), "depends_on": "grade"},
        {"key": "lut_strength", "group": "Rang", "label": "LUT kuchi", "type": "number",
         "default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05, "depends_on": "grade"},
        {"key": "denoise", "group": "Rang", "label": "Shovqin tozalash", "type": "bool", "default": True},
        {"key": "vignette", "group": "Rang", "label": "Vignette", "type": "bool", "default": True},

        # --- audio ---
        {"key": "audio_cleanup", "group": "Audio", "label": "Audio tozalash", "type": "bool", "default": True},
        {"key": "target_lufs", "group": "Audio", "label": "Balandlik (LUFS)", "type": "number",
         "default": -16.0, "min": -24.0, "max": -9.0, "step": 0.5},
    ]


def schema() -> list[dict]:
    """Options are read from disk each call, so a new style or LUT file shows up
    without a code change."""
    return _fields()


def defaults() -> dict:
    return {f["key"]: f["default"] for f in _fields()}


def merge(user: dict | None) -> dict:
    """Defaults overlaid with user values, validated.

    This is a trust boundary -- values arrive over HTTP. Numbers are clamped to
    their declared range, selects must name something that exists on disk, and
    unknown keys are dropped rather than passed through to a filter graph.
    """
    fields = {f["key"]: f for f in _fields()}
    out = {k: f["default"] for k, f in fields.items()}

    for key, value in (user or {}).items():
        field = fields.get(key)
        if field is None:
            continue

        if field["type"] == "bool":
            out[key] = bool(value)
        elif field["type"] == "number":
            try:
                out[key] = min(field["max"], max(field["min"], float(value)))
            except (TypeError, ValueError):
                pass  # keep the default rather than feed a filter garbage
        elif field["type"] == "select":
            if value in field["options"]:
                out[key] = value

    return out
