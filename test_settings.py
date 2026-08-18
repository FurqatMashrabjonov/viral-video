"""Self-check for settings.py. merge() is a trust boundary -- values arrive over
HTTP and end up in an ffmpeg filter graph, so the clamping matters.
Run: .venv/bin/python test_settings.py
"""
from settings import schema, defaults, merge


def test_every_field_has_what_a_control_needs():
    for f in schema():
        assert f["key"] and f["label"] and f["group"], f
        assert f["type"] in ("bool", "number", "select"), f
        assert "default" in f, f
        if f["type"] == "number":
            assert f["min"] < f["max"], f
            assert f["min"] <= f["default"] <= f["max"], f
        if f["type"] == "select":
            assert f["options"], f"{f['key']} has no options on disk"
            assert f["default"] in f["options"], f


def test_defaults_cover_every_field():
    assert set(defaults()) == {f["key"] for f in schema()}


def test_numbers_clamp_to_their_declared_range():
    assert merge({"zoom_scale": 99})["zoom_scale"] == 1.5
    assert merge({"zoom_scale": -5})["zoom_scale"] == 1.02
    assert merge({"sfx_volume": 4})["sfx_volume"] == 1.0


def test_garbage_numbers_fall_back_rather_than_reach_ffmpeg():
    assert merge({"zoom_scale": "abc"})["zoom_scale"] == defaults()["zoom_scale"]
    assert merge({"target_lufs": None})["target_lufs"] == defaults()["target_lufs"]


def test_select_must_name_something_that_exists():
    assert merge({"style": "../../etc/passwd"})["style"] == defaults()["style"]
    assert merge({"lut": "warm_rich"})["lut"] == "warm_rich"


def test_unknown_keys_are_dropped():
    merged = merge({"evil": "; rm -rf /", "zoom": False})
    assert "evil" not in merged
    assert merged["zoom"] is False


def test_bools_are_coerced_not_passed_through():
    assert merge({"zoom": "yes"})["zoom"] is True
    assert merge({"zoom": 0})["zoom"] is False


def test_merge_of_nothing_is_the_defaults():
    assert merge(None) == defaults()
    assert merge({}) == defaults()


def test_cut_silence_is_not_offered():
    """The renderer cannot apply cuts yet. Exposing the control would give the
    user a switch that changes nothing."""
    assert "cut_silence" not in defaults()


def test_dependent_fields_name_a_real_parent():
    keys = {f["key"] for f in schema()}
    for f in schema():
        parent = f.get("depends_on")
        assert parent is None or parent in keys, f


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
