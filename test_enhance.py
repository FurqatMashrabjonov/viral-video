"""Self-check for the zoom expression builder in enhance.py.

The zoom factors themselves were verified by rendering a clip containing a
known-size box and measuring it: 1.000x outside the window, 1.225x mid-ramp,
1.300x at hold, 1.000x after. These tests guard the string that produced it.

Run: .venv/bin/python test_enhance.py
"""
from enhance import (
    build_zoom_expr, build_zoom_filter, build_video_filter, build_audio_filter, build_broll_filter,
)

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


# --- B-roll PiP overlay ------------------------------------------------------

BROLL = [
    {"start": 1.5, "end": 3.1, "query": "office meeting"},
    {"start": 8.0, "end": 9.6, "query": "car driving"},
]
BROLL_INPUTS = {0: 3, 1: 4}  # e.g. after 2 sfx inputs: 0=main, 1,2=sfx, 3,4=broll


def test_no_broll_falls_through_untouched():
    g = build_broll_filter([], {}, 1080, 1920, "luts/warm_standard.cube", 0.6, "zoomed")
    assert g == "[zoomed]copy[pip]"


def test_each_clip_gated_to_its_own_time_window():
    g = build_broll_filter(BROLL, BROLL_INPUTS, 1080, 1920, "luts/warm_standard.cube", 0.6, "zoomed")
    assert "enable='between(t,1.5,3.1)'" in g
    assert "enable='between(t,8.0,9.6)'" in g


def test_broll_reads_from_its_own_input_index_not_the_main_video():
    g = build_broll_filter(BROLL, BROLL_INPUTS, 1080, 1920, "luts/warm_standard.cube", 0.6, "zoomed")
    assert "[3:v]" in g and "[4:v]" in g
    assert "[0:v]" not in g


def test_broll_gets_the_same_lut_and_strength_as_the_main_grade():
    g = build_broll_filter(BROLL, BROLL_INPUTS, 1080, 1920, "luts/hormozi_glow.cube", 0.42, "zoomed")
    assert g.count("lut3d=file='luts/hormozi_glow.cube'") == len(BROLL)
    assert g.count("all_opacity=0.42") == len(BROLL)


def test_broll_height_is_capped_short_of_the_full_frame():
    """The backlog spec is explicit: partial overlay, presenter stays visible,
    never full-screen."""
    g = build_broll_filter(BROLL[:1], {0: 3}, 1080, 1920, "luts/warm_standard.cube", 0.6, "zoomed")
    assert "scale=1080:1114" in g  # 1920 * 0.58, rounded


def test_broll_chains_onto_the_given_source_label_not_a_hardcoded_one():
    g = build_broll_filter(BROLL[:1], {0: 3}, 1080, 1920, "luts/warm_standard.cube", 0.6, "custom_src")
    assert g.startswith("[3:v]") or "[custom_src][" in g
    assert "custom_src" in g


def test_broll_sits_between_zoom_and_vignette():
    """A punch-in must not also scale/crop the PiP window, and vignette+
    captions belong to the final composited picture, not just the presenter."""
    eq = {"brightness": 0.0, "contrast": 1.0}
    broll_graph = build_broll_filter(BROLL[:1], {0: 3}, 1080, 1920, "luts/warm_standard.cube", 0.6, "zoomed")
    g = build_video_filter(eq, "luts/warm_standard.cube", "x.ass",
                           zoom="zoompan=z=1", broll_graph=broll_graph)
    assert g.index("zoompan") < g.index("[pip]") < g.index("vignette") < g.index("ass=")


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
