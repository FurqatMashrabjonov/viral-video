"""Pexels stock video search + download, with disk caching.

Two cache layers, the same pattern faceless-video already proved out: a
short-TTL cache of search RESULTS (the free tier is rate-limited, and a
re-render must not re-search) and an indefinite cache of downloaded FILES
keyed by URL (a published clip never changes).
"""
import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.pexels.com/videos/search"
CACHE_DIR = Path("data/broll_cache")
SEARCH_CACHE_TTL = 24 * 3600
TARGET_WIDTH, TARGET_HEIGHT = 1080, 1920  # portrait, matches our project frame
MAX_RENDITION_WIDTH = 800  # the PiP window is a fraction of a 1080px frame -- 720p
                            # rendition is already more than sharp enough, and cuts
                            # a typical download from ~19MB to ~3MB


class PexelsError(RuntimeError):
    pass


def _cache_key(query: str, orientation: str) -> str:
    return hashlib.sha256(f"{query}|{orientation}".encode()).hexdigest()


def search(query: str, orientation: str = "portrait", min_duration: float = 1.5,
           per_page: int = 10) -> list[dict]:
    """Cached Pexels video search. Returns the raw API video entries."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"search_{_cache_key(query, orientation)}.json"
    if cache_path.exists() and time.time() - cache_path.stat().st_mtime < SEARCH_CACHE_TTL:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        raise PexelsError("PEXELS_API_KEY not set")

    resp = httpx.get(
        API_URL,
        headers={"Authorization": api_key},
        params={"query": query, "orientation": orientation, "per_page": per_page},
        timeout=20,
    )
    resp.raise_for_status()
    videos = [v for v in resp.json().get("videos", []) if v.get("duration", 0) >= min_duration]
    cache_path.write_text(json.dumps(videos), encoding="utf-8")
    return videos


def best_file(video: dict, target_w: int = TARGET_WIDTH, target_h: int = TARGET_HEIGHT) -> dict | None:
    """Closest-aspect rendition, not an exact width/height match.

    faceless-video's selection picks the first file whose dimensions equal the
    target exactly -- fragile, since Pexels doesn't guarantee that exact pair
    exists for every clip. This scores every rendition by aspect-ratio
    closeness and takes the largest one under a size cap, so it always returns
    something as long as the clip has any vertical-ish rendition at all.
    """
    target_ratio = target_w / target_h
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
    if not files:
        return None

    def aspect_gap(f):
        return abs((f["width"] / f["height"]) - target_ratio)

    files.sort(key=lambda f: (round(aspect_gap(f), 2), -f["width"]))
    for f in files:
        if f["width"] <= MAX_RENDITION_WIDTH:
            return f
    return files[0]  # every rendition was oversized; take the closest-aspect one anyway


def _download_path(url: str) -> Path:
    h = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"clip_{h}.mp4"


def download(url: str) -> str:
    """Fetch a rendition, or reuse it if already cached on disk."""
    path = _download_path(url)
    if path.exists() and path.stat().st_size > 0:
        return str(path)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=60, follow_redirects=True) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    return str(path)


def fetch_clip(query: str, orientation: str = "portrait", min_duration: float = 1.5) -> str | None:
    """Search, pick the best match, download it -- one call for the common case.

    None on any failure (no results, API error, download error): a missing
    B-roll clip is worth far less than a failed render, so this never raises.
    """
    try:
        videos = search(query, orientation=orientation, min_duration=min_duration)
    except Exception as e:
        print(f"[pexels] search failed for {query!r}: {e}")
        return None

    for video in videos:
        f = best_file(video)
        if not f:
            continue
        try:
            return download(f["link"])
        except Exception as e:
            print(f"[pexels] download failed for {query!r}: {e}")
            continue

    print(f"[pexels] no usable clip found for {query!r}")
    return None
