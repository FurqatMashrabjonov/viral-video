"""Self-check for the keyword-highlight and hook tags in subtitles.py.
Run: .venv/bin/python test_subtitles.py
"""
from subtitles import (
    build_ass, _keyword_tags, _tag_color, _emoji_run, _style_font, _display_word,
    _highlight_tags, EMOJI_FONT,
)

BASE = {
    "mode": "karaoke", "font": "Noto Sans", "font_bold": "Noto Sans Bold",
    "font_size": 72, "bold": True,
    "primary_color": [255, 255, 255], "outline_color": [0, 0, 0],
}
COLOR_STYLE = {**BASE, "keyword_color": [90, 226, 130]}
BOX_STYLE = {
    **BASE, "mode": "pop", "keyword_box": True,
    "keyword_box_color": [30, 158, 30], "keyword_color": [255, 255, 255],
    "box_color": [0, 0, 0], "box_alpha": 96,
}
HIGHLIGHT_STYLE = {
    **BASE, "mode": "highlight",
    "box_color": [20, 20, 20], "box_alpha": 110, "keyword_box_color": [254, 44, 85],
}

WORDS = [
    {"word": "narx", "start": 0.0, "end": 0.4, "keyword": False},
    {"word": "30", "start": 0.4, "end": 0.8, "keyword": True},
    {"word": "foiz", "start": 0.8, "end": 1.2, "keyword": False},
]


def test_ass_colour_is_bgr_not_rgb():
    # &HBBGGRR& -- red must land in the last pair, not the first
    assert _tag_color([255, 0, 0]) == "&H0000FF&"
    assert _tag_color([0, 0, 255]) == "&HFF0000&"


def test_no_keyword_config_emits_no_tags():
    assert _keyword_tags(BASE, True) == ""
    assert _keyword_tags(BASE, False) == ""


def test_colour_mode_switches_between_keyword_and_primary():
    assert _tag_color([90, 226, 130]) in _keyword_tags(COLOR_STYLE, True)
    assert _tag_color([255, 255, 255]) in _keyword_tags(COLOR_STYLE, False)


def test_every_run_states_its_own_colour():
    """ASS tags persist down the line, so a non-keyword run must actively reset."""
    assert "\\c" in _keyword_tags(COLOR_STYLE, False), "highlight would bleed onward"


def test_box_mode_makes_keyword_opaque_and_others_translucent():
    assert "\\3a&H00&" in _keyword_tags(BOX_STYLE, True)
    assert "\\3a&H60&" in _keyword_tags(BOX_STYLE, False)  # 96 == 0x60


def test_box_mode_sets_borderstyle_3_so_the_box_exists():
    subs = build_ass(WORDS, BOX_STYLE, 1080, 1920)
    assert subs.styles["Default"].borderstyle == 3


def test_colour_mode_keeps_borderstyle_1_so_the_outline_survives():
    subs = build_ass(WORDS, COLOR_STYLE, 1080, 1920)
    assert subs.styles["Default"].borderstyle == 1


def test_karaoke_keeps_spaces_between_words():
    subs = build_ass(WORDS, COLOR_STYLE, 1080, 1920)
    assert " " in subs[0].text, "words would run together"


def test_karaoke_emits_one_k_tag_per_word():
    subs = build_ass(WORDS, COLOR_STYLE, 1080, 1920)
    assert subs[0].text.count("\\k") == len(WORDS)


def test_hook_adds_a_separate_top_aligned_event():
    hook = {"text": "Sarlavha", "start": 0.0, "end": 3.0}
    subs = build_ass(WORDS, COLOR_STYLE, 1080, 1920, hook=hook)
    hooks = [e for e in subs if e.style == "Hook"]
    assert len(hooks) == 1
    assert "Sarlavha" in hooks[0].text
    assert hooks[0].end == 3000
    assert subs.styles["Hook"].alignment == 8  # top-center, away from the captions


def test_no_hook_means_no_hook_style():
    subs = build_ass(WORDS, COLOR_STYLE, 1080, 1920, hook=None)
    assert "Hook" not in subs.styles


def test_empty_hook_text_is_ignored():
    subs = build_ass(WORDS, COLOR_STYLE, 1080, 1920, hook={"text": "", "start": 0, "end": 3})
    assert "Hook" not in subs.styles


EMOJI_WORDS = [
    {"word": "narx", "start": 0.0, "end": 0.4, "keyword": False},
    {"word": "30", "start": 0.4, "end": 0.8, "keyword": True, "emoji": "📈"},
    {"word": "foiz", "start": 0.8, "end": 1.2, "keyword": False},
]


def test_emoji_run_switches_font_and_switches_back():
    """A karaoke line is one Dialogue event with several words in it, so the
    emoji's font override must not leak into whatever comes after it."""
    run = _emoji_run(COLOR_STYLE, "📈")
    assert run.count(f"\\fn{EMOJI_FONT}") == 1
    assert run.rstrip().endswith(f"{{\\fn{_style_font(COLOR_STYLE)}\\fscx100\\fscy100}}")


def test_karaoke_includes_emoji_when_present_and_enabled():
    subs = build_ass(EMOJI_WORDS, COLOR_STYLE, 1080, 1920, show_emoji=True)
    assert "📈" in subs[0].text
    assert f"\\fn{EMOJI_FONT}" in subs[0].text


def test_show_emoji_false_omits_the_glyph_entirely():
    subs = build_ass(EMOJI_WORDS, COLOR_STYLE, 1080, 1920, show_emoji=False)
    assert "📈" not in subs[0].text


def test_word_without_emoji_field_is_unaffected():
    subs = build_ass(WORDS, COLOR_STYLE, 1080, 1920, show_emoji=True)
    assert EMOJI_FONT not in subs[0].text


def test_pop_mode_appends_emoji_after_the_word():
    # Pop mode emits one event per word, in order -- index straight into the
    # list rather than searching by substring, since "30" also matches inside
    # the "fscx130" override tag every event carries.
    pop_style = {**COLOR_STYLE, "mode": "pop"}
    subs = build_ass(EMOJI_WORDS, pop_style, 1080, 1920, show_emoji=True)
    event = subs[1]
    assert "📈" in event.text
    assert event.text.index("30") < event.text.index("📈")


def test_uppercase_transforms_display_text_only():
    word = {"word": "oʻzbekcha"}
    assert _display_word(word, {"uppercase": True}) == "OʻZBEKCHA"
    assert _display_word(word, {"uppercase": False}) == "oʻzbekcha"
    assert word["word"] == "oʻzbekcha", "must not mutate the stored word"


def test_uppercase_off_by_default():
    assert _display_word({"word": "test"}, {}) == "test"


def test_hook_is_uppercased_when_the_style_asks_for_it():
    hook = {"text": "salom dunyo", "start": 0.0, "end": 3.0}
    subs = build_ass(WORDS, {**COLOR_STYLE, "uppercase": True}, 1080, 1920, hook=hook)
    hook_event = next(e for e in subs if e.style == "Hook")
    assert "SALOM DUNYO" in hook_event.text


# --- highlight mode: whole phrase visible, active word tracked by time -----

HL_GROUP = [
    {"word": "birinchi", "start": 0.0, "end": 1.0, "keyword": False},
    {"word": "ikkinchi", "start": 1.0, "end": 2.0, "keyword": False},
]


def test_highlight_mode_emits_one_event_per_group_not_per_word():
    subs = build_ass(HL_GROUP, HIGHLIGHT_STYLE, 1080, 1920)
    assert len(subs) == 1, "the whole phrase is one Dialogue event, not one per word"
    assert "birinchi" in subs[0].text and "ikkinchi" in subs[0].text


def test_highlight_mode_forces_borderstyle_3_even_without_keyword_box():
    """The box is the mechanism, not an opt-in accent -- unlike keyword_box,
    which stays off unless a style asks for it."""
    subs = build_ass(HL_GROUP, HIGHLIGHT_STYLE, 1080, 1920)
    assert subs.styles["Default"].borderstyle == 3


def test_highlight_tags_schedule_each_word_at_its_own_time():
    # Second word starts 1000ms into the group -- confirmed against a real
    # render: at t=0.5s only "birinchi" showed the active colour, at t=1.5s
    # only "ikkinchi" did.
    event_start_ms = 0
    tags = _highlight_tags(HIGHLIGHT_STYLE, HL_GROUP[1], event_start_ms)
    assert "\\t(1000," in tags, "word 2's own start (1000ms) must drive its \\t window"
    assert "\\t(2000," in tags, "word 2's own end (2000ms) must drive its \\t window"


def test_highlight_tags_shift_relative_to_event_start():
    """A later group doesn't start its Dialogue event at t=0 -- the schedule
    must be relative to the event, not absolute video time, or the box fires
    at the wrong moment for every group after the first."""
    word = {"word": "x", "start": 5.5, "end": 6.0}
    tags = _highlight_tags(HIGHLIGHT_STYLE, word, event_start_ms=5000)
    assert "\\t(500," in tags
    assert "\\t(1000," in tags


def test_highlight_active_colour_is_the_keyword_box_colour():
    tags = _highlight_tags(HIGHLIGHT_STYLE, HL_GROUP[0], 0)
    assert _tag_color(HIGHLIGHT_STYLE["keyword_box_color"]) in tags
    assert _tag_color(HIGHLIGHT_STYLE["box_color"]) in tags


if __name__ == "__main__":
    import sys
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
