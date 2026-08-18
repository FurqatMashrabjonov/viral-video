"""Self-check for analyze.py. The remap math is the part that breaks subtitles
across the whole video if it's wrong, so it gets the most coverage.
Run: .venv/bin/python test_analyze.py
"""
from analyze import (
    find_silences,
    remap_time,
    remap_words,
    mark_keywords,
    plan_zooms,
    build_edit_plan,
)

# 2.0s of dead air between "bor" and "keyin"
WORDS = [
    {"word": "Bugun", "start": 0.20, "end": 0.60},
    {"word": "50", "start": 0.60, "end": 0.90},
    {"word": "foiz", "start": 0.90, "end": 1.30},
    {"word": "bor", "start": 1.30, "end": 1.70},
    {"word": "keyin", "start": 3.70, "end": 4.10},
    {"word": "ketdik", "start": 4.10, "end": 4.60},
]


def test_finds_the_long_gap_only():
    cuts = find_silences(WORDS)
    assert len(cuts) == 1, f"expected 1 cut, got {cuts}"
    assert cuts[0]["start"] == 1.75 and cuts[0]["end"] == 3.65


def test_no_cuts_when_speech_is_continuous():
    tight = [
        {"word": "a", "start": 0.0, "end": 0.5},
        {"word": "b", "start": 0.55, "end": 1.0},
    ]
    assert find_silences(tight) == []


def test_remap_before_cut_is_unchanged():
    cuts = [{"start": 1.75, "end": 3.65, "reason": "silence"}]
    assert remap_time(1.30, cuts) == 1.30


def test_remap_after_cut_shifts_by_cut_length():
    cuts = [{"start": 1.75, "end": 3.65, "reason": "silence"}]
    assert remap_time(3.70, cuts) == round(3.70 - 1.90, 3)


def test_remap_subtracts_every_earlier_cut():
    cuts = [
        {"start": 1.0, "end": 2.0, "reason": "silence"},
        {"start": 4.0, "end": 4.5, "reason": "silence"},
    ]
    assert remap_time(5.0, cuts) == 3.5  # 1.0s + 0.5s removed before it


def test_words_stay_ordered_and_never_overlap_after_remap():
    cuts = find_silences(WORDS)
    out = remap_words(WORDS, cuts)
    assert len(out) == len(WORDS), "no word should be dropped here"
    for prev, nxt in zip(out, out[1:]):
        assert prev["end"] <= nxt["start"], f"{prev} overlaps {nxt}"
        assert prev["start"] < prev["end"]


def test_remap_preserves_each_word_duration():
    cuts = find_silences(WORDS)
    for before, after in zip(WORDS, remap_words(WORDS, cuts)):
        assert abs((after["end"] - after["start"]) - (before["end"] - before["start"])) < 1e-6


def test_word_inside_a_cut_is_dropped():
    cuts = [{"start": 0.0, "end": 1.0, "reason": "silence"}]
    words = [{"word": "x", "start": 0.2, "end": 0.5}, {"word": "y", "start": 2.0, "end": 2.4}]
    assert [w["word"] for w in remap_words(words, cuts)] == ["y"]


def test_numbers_are_keywords_plain_words_are_not():
    marked = {w["word"]: w["keyword"] for w in mark_keywords(WORDS)}
    assert marked["50"] is True
    assert marked["foiz"] is False
    assert marked["Bugun"] is False


def test_zooms_respect_minimum_spacing():
    words = [{"word": str(i), "start": i * 0.5, "end": i * 0.5 + 0.3, "keyword": True} for i in range(12)]
    zooms = plan_zooms(words, [])
    for prev, nxt in zip(zooms, zooms[1:]):
        assert nxt["start"] - prev["start"] >= 3.0, "zoom would pulse"


def test_plan_output_duration_matches_removed_time():
    plan = build_edit_plan(WORDS, source_duration=5.0)
    removed = sum(c["end"] - c["start"] for c in plan["cuts"])
    assert abs(plan["output_duration"] - (5.0 - removed)) < 1e-6
    assert plan["output_duration"] < plan["source_duration"]


def test_cut_silence_false_leaves_the_timeline_alone():
    plan = build_edit_plan(WORDS, source_duration=5.0, cut_silence=False)
    assert plan["cuts"] == []
    assert plan["output_duration"] == plan["source_duration"]
    assert [w["start"] for w in plan["words"]] == [w["start"] for w in WORDS]


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
