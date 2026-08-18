"""ASS subtitle generation from normalized word segments (pysubs2 + libass)."""
import yaml
import pysubs2


def load_style(style_path: str) -> dict:
    with open(style_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _color(rgb, alpha=0):
    r, g, b = rgb
    return pysubs2.Color(r, g, b, alpha)


def _make_ssa_style(style: dict) -> pysubs2.SSAStyle:
    s = pysubs2.SSAStyle()
    s.fontname = style["font_bold"] if style.get("bold") else style["font"]
    s.fontsize = style["font_size"]
    s.primarycolor = _color(style["primary_color"])
    s.secondarycolor = _color(style.get("secondary_color", style["primary_color"]))
    s.outlinecolor = _color(style["outline_color"])
    s.bold = style.get("bold", True)
    s.outline = style.get("outline_width", 3)
    s.shadow = style.get("shadow", 0)
    s.alignment = pysubs2.Alignment(2)  # bottom-center
    s.marginv = style.get("margin_v", 180)
    s.marginl = style.get("margin_h", 60)
    s.marginr = style.get("margin_h", 60)
    return s


def group_words(words: list[dict], max_words: int = 4, max_chars: int = 22) -> list[list[dict]]:
    """Chunk words into on-screen lines, capped by word count and a char-count proxy
    for pixel width.
    # ponytail: char-count is a width proxy, swap for real font-metrics measurement
    # if lines still overflow 9:16 on long/wide words
    """
    groups = []
    current, current_len = [], 0
    for w in words:
        wlen = len(w["word"]) + 1
        if current and (len(current) >= max_words or current_len + wlen > max_chars):
            groups.append(current)
            current, current_len = [], 0
        current.append(w)
        current_len += wlen
    if current:
        groups.append(current)
    return groups


def _karaoke_text(group: list[dict]) -> str:
    parts = []
    for w in group:
        dur_cs = max(1, round((w["end"] - w["start"]) * 100))
        parts.append(f"{{\\k{dur_cs}}}{w['word']}")
    return " ".join(parts)


def build_ass(words: list[dict], style: dict, video_width: int, video_height: int) -> pysubs2.SSAFile:
    subs = pysubs2.SSAFile()
    subs.info["PlayResX"] = str(video_width)
    subs.info["PlayResY"] = str(video_height)
    subs.styles["Default"] = _make_ssa_style(style)

    mode = style.get("mode", "pop")
    if mode == "karaoke":
        for group in group_words(words, style.get("max_words_per_line", 4), style.get("max_chars_per_line", 22)):
            start_ms = int(group[0]["start"] * 1000)
            end_ms = int(group[-1]["end"] * 1000)
            subs.append(pysubs2.SSAEvent(start=start_ms, end=end_ms, text=_karaoke_text(group), style="Default"))
    elif mode == "pop":
        pop_ms = style.get("pop_duration_ms", 120)
        scale_from = style.get("pop_scale_from", 130)
        for w in words:
            start_ms = int(w["start"] * 1000)
            end_ms = int(w["end"] * 1000)
            text = f"{{\\fscx{scale_from}\\fscy{scale_from}\\t(0,{pop_ms},\\fscx100\\fscy100)}}{w['word']}"
            subs.append(pysubs2.SSAEvent(start=start_ms, end=end_ms, text=text, style="Default"))
    else:
        raise ValueError(f"unknown style mode: {mode!r}")

    return subs
