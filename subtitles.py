"""ASS subtitle generation from normalized word segments (pysubs2 + libass)."""
import yaml
import pysubs2


def load_style(style_path: str) -> dict:
    with open(style_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _color(rgb, alpha=0):
    r, g, b = rgb
    return pysubs2.Color(r, g, b, alpha)


def _tag_color(rgb) -> str:
    """ASS inline colour override -- &HBBGGRR&, reversed from RGB."""
    r, g, b = rgb
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _make_ssa_style(style: dict) -> pysubs2.SSAStyle:
    s = pysubs2.SSAStyle()
    s.fontname = style["font_bold"] if style.get("bold") else style["font"]
    s.fontsize = style["font_size"]
    s.primarycolor = _color(style["primary_color"])
    s.secondarycolor = _color(style.get("secondary_color", style["primary_color"]))
    s.outlinecolor = _color(style["outline_color"])
    s.bold = style.get("bold", True)
    s.shadow = style.get("shadow", 0)
    s.alignment = pysubs2.Alignment(2)  # bottom-center
    s.marginv = style.get("margin_v", 180)
    s.marginl = style.get("margin_h", 60)
    s.marginr = style.get("margin_h", 60)

    # BorderStyle 3 turns the outline into a filled box behind the text, which is
    # what makes a per-word highlight possible -- but it also means there is no
    # outline left, so every word needs its own box to stay legible over video.
    if style.get("keyword_box"):
        s.borderstyle = 3
        s.outline = style.get("box_pad", 10)
    else:
        s.borderstyle = 1
        s.outline = style.get("outline_width", 3)
    return s


def _keyword_tags(style: dict, is_keyword: bool) -> str:
    """Inline overrides that turn the highlight on or off for one run of text.

    Every run states its own colours rather than relying on a reset, because ASS
    tags persist across a line -- a highlight that only sets itself would bleed
    into every word after it.
    """
    has_color = bool(style.get("keyword_color"))
    boxed = bool(style.get("keyword_box"))
    if not has_color and not boxed:
        return ""

    tags = ""
    if has_color:
        rgb = style["keyword_color"] if is_keyword else style["primary_color"]
        tags += f"\\c{_tag_color(rgb)}"
    if boxed:
        if is_keyword:
            tags += f"\\3a&H00&\\3c{_tag_color(style['keyword_box_color'])}"
        else:
            alpha = style.get("box_alpha", 96)
            tags += f"\\3a&H{alpha:02X}&\\3c{_tag_color(style.get('box_color', [0, 0, 0]))}"
    return tags


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


def _karaoke_text(group: list[dict], style: dict) -> str:
    parts = []
    for w in group:
        dur_cs = max(1, round((w["end"] - w["start"]) * 100))
        tags = _keyword_tags(style, w.get("keyword", False))
        parts.append(f"{{{tags}\\k{dur_cs}}}{w['word']}")
    # Joining with a bare space leaves the separator under the *preceding* word's
    # tags, so a highlight box gets trailing padding instead of a stray sliver of
    # the next word's colour.
    return " ".join(parts)


def _make_hook_style(style: dict) -> pysubs2.SSAStyle:
    s = pysubs2.SSAStyle()
    s.fontname = style["font_bold"] if style.get("bold") else style["font"]
    s.fontsize = style.get("hook_font_size", round(style["font_size"] * 1.05))
    s.primarycolor = _color(style.get("hook_color", style["primary_color"]))
    s.outlinecolor = _color(style.get("hook_outline_color", style["outline_color"]))
    s.bold = True
    s.borderstyle = 1
    s.outline = style.get("hook_outline_width", 4)
    s.shadow = 0
    s.alignment = pysubs2.Alignment(8)  # top-center
    s.marginv = style.get("hook_margin_v", 220)
    s.marginl = style.get("margin_h", 60)
    s.marginr = style.get("margin_h", 60)
    return s


def build_ass(words: list[dict], style: dict, video_width: int, video_height: int,
              hook: dict | None = None) -> pysubs2.SSAFile:
    subs = pysubs2.SSAFile()
    subs.info["PlayResX"] = str(video_width)
    subs.info["PlayResY"] = str(video_height)
    subs.styles["Default"] = _make_ssa_style(style)

    mode = style.get("mode", "pop")
    if mode == "karaoke":
        for group in group_words(words, style.get("max_words_per_line", 4), style.get("max_chars_per_line", 22)):
            start_ms = int(group[0]["start"] * 1000)
            end_ms = int(group[-1]["end"] * 1000)
            subs.append(pysubs2.SSAEvent(start=start_ms, end=end_ms,
                                        text=_karaoke_text(group, style), style="Default"))
    elif mode == "pop":
        pop_ms = style.get("pop_duration_ms", 120)
        scale_from = style.get("pop_scale_from", 130)
        for w in words:
            tags = _keyword_tags(style, w.get("keyword", False))
            text = (f"{{\\fscx{scale_from}\\fscy{scale_from}"
                    f"\\t(0,{pop_ms},\\fscx100\\fscy100){tags}}}{w['word']}")
            subs.append(pysubs2.SSAEvent(start=int(w["start"] * 1000), end=int(w["end"] * 1000),
                                        text=text, style="Default"))
    else:
        raise ValueError(f"unknown style mode: {mode!r}")

    if hook and hook.get("text"):
        subs.styles["Hook"] = _make_hook_style(style)
        fade = style.get("hook_fade_ms", 250)
        subs.append(pysubs2.SSAEvent(
            start=int(hook.get("start", 0.0) * 1000),
            end=int(hook.get("end", 3.0) * 1000),
            text=f"{{\\fad({fade},{fade})}}{hook['text']}",
            style="Hook",
        ))

    return subs
