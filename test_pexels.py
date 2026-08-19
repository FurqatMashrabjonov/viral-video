"""Self-check for pexels.py's pure logic -- no network. Run: .venv/bin/python test_pexels.py"""
from pexels import best_file, _cache_key, _download_path, TARGET_WIDTH, TARGET_HEIGHT, MAX_RENDITION_WIDTH

PORTRAIT_VIDEO = {
    "video_files": [
        {"file_type": "video/mp4", "quality": "sd", "width": 360, "height": 640},
        {"file_type": "video/mp4", "quality": "hd", "width": 720, "height": 1280},
        {"file_type": "video/mp4", "quality": "hd", "width": 1080, "height": 1920},
        {"file_type": "video/mp4", "quality": "uhd", "width": 2160, "height": 3840},
    ]
}


def test_picks_largest_rendition_under_the_size_cap():
    f = best_file(PORTRAIT_VIDEO)
    assert f["width"] <= MAX_RENDITION_WIDTH
    assert f["width"] == 720, "720 is the largest rendition <= the 800px cap"


def test_prefers_closer_aspect_over_raw_size():
    """A landscape rendition with more pixels must lose to a smaller portrait
    one -- this is going into a 9:16 frame, aspect match matters more than
    resolution."""
    video = {"video_files": [
        {"file_type": "video/mp4", "width": 1920, "height": 1080},  # landscape, huge
        {"file_type": "video/mp4", "width": 360, "height": 640},    # portrait, tiny
    ]}
    f = best_file(video, target_w=TARGET_WIDTH, target_h=TARGET_HEIGHT)
    assert f["width"] == 360


def test_falls_back_to_closest_aspect_when_everything_is_oversized():
    video = {"video_files": [
        {"file_type": "video/mp4", "width": 2160, "height": 3840},
        {"file_type": "video/mp4", "width": 3840, "height": 2160},  # wrong aspect too
    ]}
    f = best_file(video)
    assert f["width"] == 2160, "closest aspect wins even over the cap when nothing fits"


def test_no_mp4_files_returns_none():
    assert best_file({"video_files": [{"file_type": "video/webm", "width": 720, "height": 1280}]}) is None
    assert best_file({"video_files": []}) is None
    assert best_file({}) is None


def test_cache_key_is_deterministic_and_query_specific():
    assert _cache_key("office meeting", "portrait") == _cache_key("office meeting", "portrait")
    assert _cache_key("office meeting", "portrait") != _cache_key("car driving", "portrait")
    assert _cache_key("office meeting", "portrait") != _cache_key("office meeting", "landscape")


def test_download_path_is_stable_for_the_same_url():
    url = "https://videos.pexels.com/video-files/123/123-hd.mp4"
    assert _download_path(url) == _download_path(url)


def test_download_path_differs_for_different_urls():
    a = _download_path("https://videos.pexels.com/video-files/123/a.mp4")
    b = _download_path("https://videos.pexels.com/video-files/123/b.mp4")
    assert a != b


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
