"""Self-check for the keyword-highlight and hook tags in subtitles.py.
Run: .venv/bin/python test_subtitles.py
"""
from subtitles import build_ass, _keyword_tags, _tag_color

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
