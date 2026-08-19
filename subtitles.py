"""ASS subtitle generation from normalized word segments (pysubs2 + libass)."""
import yaml
import pysubs2


EMOJI_FONT = "Noto Emoji"          # monochrome, renders through the normal text
                                    # path -- no colour-font support needed in libass
EMOJI_SCALE = 130                  # the glyph reads small next to bold caption text
HIGHLIGHT_SWITCH_MS = 40           # near-instant box on/off, not a visible fade


def load_style(style_path: str) -> dict:
    with open(style_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _style_font(style: dict) -> str:
    return style["font_bold"] if style.get("bold") else style["font"]


def _display_word(word: dict, style: dict) -> str:
    """The word as it's burned into the video -- upper-cased for a style that
    wants it. Never mutates the stored word: the editor and keyword matching
    still need the original casing."""
    text = word["word"]
    return text.upper() if style.get("uppercase") else text


def _color(rgb, alpha=0):
    r, g, b = rgb
    return pysubs2.Color(r, g, b, alpha)


def _tag_color(rgb) -> str:
    """ASS inline colour override -- &HBBGGRR&, reversed from RGB."""
    r, g, b = rgb
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _make_ssa_style(style: dict) -> pysubs2.SSAStyle:
    s = pysubs2.SSAStyle()
    s.fontname = _style_font(style)
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
    # "highlight" mode needs this unconditionally: the box is the whole point of
    # the mode, not an optional keyword accent on top of it.
    if style.get("keyword_box") or style.get("mode") == "highlight":
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


def _emoji_run(style: dict, emoji: str) -> str:
    """A word's emoji as its own text run: switch font, scale up, switch back.

    The scale and font revert inside the tag block itself rather than relying
    on the next word to reset them -- a line with no more emoji after this one
    must not stay on the emoji font.
    """
    return (
        f"{{\\fn{EMOJI_FONT}\\fscx{EMOJI_SCALE}\\fscy{EMOJI_SCALE}}}"
        f" {emoji}"
        f"{{\\fn{_style_font(style)}\\fscx100\\fscy100}}"
    )


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


def _karaoke_text(group: list[dict], style: dict, show_emoji: bool) -> str:
    parts = []
    for w in group:
        dur_cs = max(1, round((w["end"] - w["start"]) * 100))
        tags = _keyword_tags(style, w.get("keyword", False))
        run = f"{{{tags}\\k{dur_cs}}}{_display_word(w, style)}"
        if show_emoji and w.get("emoji"):
            run += _emoji_run(style, w["emoji"])
        parts.append(run)
    # Joining with a bare space leaves the separator under the *preceding* word's
    # tags, so a highlight box gets trailing padding instead of a stray sliver of
    # the next word's colour.
    return " ".join(parts)


def _highlight_tags(style: dict, word: dict, event_start_ms: int) -> str:
    """The whole phrase stays on screen; only the word currently being spoken
    gets a background box, timed to switch on and off at that word's own
    start/end -- proven against a real render (two words, two independent
    windows, each box appearing only in its own word's frame).

    Scoped per run exactly like _keyword_tags: each word schedules its own
    \\t() transforms on \\3c/\\3a, so at any render timestamp only the word
    whose window contains that timestamp is showing the active colour --
    nothing shared or global to get out of sync.
    """
    start_rel = int(word["start"] * 1000) - event_start_ms
    end_rel = int(word["end"] * 1000) - event_start_ms
    neutral_alpha = style.get("box_alpha", 96)
    neutral_color = _tag_color(style.get("box_color", [0, 0, 0]))
    active_color = _tag_color(style.get("keyword_box_color", style["primary_color"]))
    m = HIGHLIGHT_SWITCH_MS
    return (
        f"\\3a&H{neutral_alpha:02X}&\\3c{neutral_color}"
        f"\\t({start_rel},{start_rel + m},\\3c{active_color}\\3a&H00&)"
        f"\\t({end_rel},{end_rel + m},\\3c{neutral_color}\\3a&H{neutral_alpha:02X}&)"
    )


def _highlight_text(group: list[dict], style: dict, show_emoji: bool) -> str:
    event_start_ms = int(group[0]["start"] * 1000)
    parts = []
    for w in group:
        run = f"{{{_highlight_tags(style, w, event_start_ms)}}}{_display_word(w, style)}"
        if show_emoji and w.get("emoji"):
            run += _emoji_run(style, w["emoji"])
        parts.append(run)
    return " ".join(parts)


def _make_hook_style(style: dict) -> pysubs2.SSAStyle:
    s = pysubs2.SSAStyle()
    s.fontname = _style_font(style)
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
              hook: dict | None = None, show_emoji: bool = True) -> pysubs2.SSAFile:
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
                                        text=_karaoke_text(group, style, show_emoji), style="Default"))
    elif mode == "highlight":
        for group in group_words(words, style.get("max_words_per_line", 4), style.get("max_chars_per_line", 22)):
            start_ms = int(group[0]["start"] * 1000)
            end_ms = int(group[-1]["end"] * 1000)
            subs.append(pysubs2.SSAEvent(start=start_ms, end=end_ms,
                                        text=_highlight_text(group, style, show_emoji), style="Default"))
    elif mode == "pop":
        pop_ms = style.get("pop_duration_ms", 120)
        scale_from = style.get("pop_scale_from", 130)
        for w in words:
            tags = _keyword_tags(style, w.get("keyword", False))
            text = (f"{{\\fscx{scale_from}\\fscy{scale_from}"
                    f"\\t(0,{pop_ms},\\fscx100\\fscy100){tags}}}{_display_word(w, style)}")
            if show_emoji and w.get("emoji"):
                text += _emoji_run(style, w["emoji"])
            subs.append(pysubs2.SSAEvent(start=int(w["start"] * 1000), end=int(w["end"] * 1000),
                                        text=text, style="Default"))
    else:
        raise ValueError(f"unknown style mode: {mode!r}")

    if hook and hook.get("text"):
        subs.styles["Hook"] = _make_hook_style(style)
        fade = style.get("hook_fade_ms", 250)
        hook_text = hook["text"].upper() if style.get("uppercase") else hook["text"]
        subs.append(pysubs2.SSAEvent(
            start=int(hook.get("start", 0.0) * 1000),
            end=int(hook.get("end", 3.0) * 1000),
            text=f"{{\\fad({fade},{fade})}}{hook_text}",
            style="Hook",
        ))

    return subs
