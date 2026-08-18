"""Self-check for the zoom expression builder in enhance.py.

The zoom factors themselves were verified by rendering a clip containing a
known-size box and measuring it: 1.000x outside the window, 1.225x mid-ramp,
1.300x at hold, 1.000x after. These tests guard the string that produced it.

Run: .venv/bin/python test_enhance.py
"""
from enhance import build_zoom_expr, build_zoom_filter, build_video_filter, build_audio_filter

ZOOMS = [
    {"start": 2.0, "end": 3.2, "scale": 1.30},
    {"start": 6.0, "end": 7.2, "scale": 1.15},
]


def test_no_zooms_means_no_filter():
    assert build_zoom_filter([], 1080, 1920, 30) == ""


def test_one_branch_per_zoom():
    assert build_zoom_expr(ZOOMS).count("if(between(") == len(ZOOMS)


def test_default_branch_is_unzoomed():
    """Anything outside every window must fall through to 1, or the clip stays
    stuck at the last zoom level. The tail is `,1` plus one `)` per nested if."""
    expr = build_zoom_expr(ZOOMS)
    head, _, tail = expr.rpartition(",1")
    assert head and set(tail) == {")"}, expr
    assert len(tail) == len(ZOOMS), "unbalanced nesting"


def test_expression_parentheses_balance():
    expr = build_zoom_expr(ZOOMS)
    assert expr.count("(") == expr.count(")")


def test_scale_appears_as_a_delta_above_one():
    expr = build_zoom_expr([{"start": 0.0, "end": 1.0, "scale": 1.30}])
    assert "1+0.3000*" in expr, expr


def test_windows_keep_their_order():
    expr = build_zoom_expr(ZOOMS)
    assert expr.index("2.0") < expr.index("6.0"), "later zoom must nest deeper"


def test_ramp_is_symmetric_at_both_edges():
    expr = build_zoom_expr([{"start": 2.0, "end": 3.2, "scale": 1.3}], ramp=0.22)
    assert "(in_time-2.0)/0.22" in expr, "no ease in"
    assert "(3.2-in_time)/0.22" in expr, "no ease out"


def test_filter_pins_output_size_and_fps():
    """zoompan defaults to hd720 and its own rate; both must be overridden or the
    clip silently changes resolution and timing."""
    f = build_zoom_filter(ZOOMS, 1080, 1920, 30)
    assert "s=1080x1920" in f
    assert "fps=30" in f


def test_zoom_is_centre_anchored():
    f = build_zoom_filter(ZOOMS, 1080, 1920, 30)
    assert "iw/2-(iw/zoom/2)" in f and "ih/2-(ih/zoom/2)" in f


def test_zoom_runs_before_vignette_and_captions():
    """Vignette belongs to the frame edge and captions must not scale with the
    picture, so both have to come after the zoom."""
    eq = {"brightness": 0.0, "contrast": 1.0}
    g = build_video_filter(eq, "luts/warm_standard.cube", "x.ass", build_zoom_filter(ZOOMS, 1080, 1920, 30))
    assert g.index("zoompan") < g.index("vignette") < g.index("ass=")


def test_graph_still_connects_when_there_is_no_zoom():
    eq = {"brightness": 0.0, "contrast": 1.0}
    g = build_video_filter(eq, "luts/warm_standard.cube", None, "")
    assert "[zoomed]" in g and "[vout]" in g


SFX = [{"time": 1.0, "name": "pop"}, {"time": 3.5, "name": "ding"}, {"time": 6.0, "name": "pop"}]
SFX_INPUTS = {"pop": 1, "ding": 2}


def test_audio_chain_without_sfx_is_speech_then_loudnorm():
    f = build_audio_filter()
    assert "amix" not in f
    assert f.index("acompressor") < f.index("loudnorm")


def test_amix_disables_normalisation():
    """amix divides every input by the input count unless told not to, which
    would silently drop the speech by 1/N."""
    assert "normalize=0" in build_audio_filter(SFX, SFX_INPUTS)


def test_amix_input_count_matches_speech_plus_every_hit():
    f = build_audio_filter(SFX, SFX_INPUTS)
    assert f"amix=inputs={1 + len(SFX)}" in f


def test_one_delay_per_hit_at_the_right_millisecond():
    f = build_audio_filter(SFX, SFX_INPUTS)
    for e in SFX:
        assert f"adelay={int(e['time'] * 1000)}:all=1" in f


def test_repeated_effect_is_split_not_reopened():
    """pop fires twice but the file is only decoded once."""
    f = build_audio_filter(SFX, SFX_INPUTS)
    assert f.count("[1:a]") == 1
    assert "asplit=2" in f


def test_loudnorm_runs_after_the_mix():
    """Effects must be inside the normalised mix, or they push the true peak
    past -1.5 dBTP afterwards."""
    f = build_audio_filter(SFX, SFX_INPUTS)
    assert f.index("amix") < f.index("loudnorm")


def test_effects_are_not_run_through_the_speech_cleanup():
    f = build_audio_filter(SFX, SFX_INPUTS)
    assert f.index("acompressor") < f.index("[1:a]"), "denoise would dull the effects"


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
