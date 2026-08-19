"""ElevenLabs Scribe v2 speech-to-text adapter.

Sends an audio file, returns word-level timestamps:
[{"word": str, "start": float, "end": float, "logprob": float | None}, ...]

logprob is Scribe's log-probability for the word: near 0 means confident,
strongly negative means the model was guessing. Kept so the editor can flag
words worth a second look instead of the user re-reading the whole transcript.
"""
import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL_ID = "scribe_v1"
COST_PER_MINUTE_USD = 0.40  # ponytail: rough Scribe pricing, update if ElevenLabs changes it


class ScribeError(RuntimeError):
    pass


def transcribe(audio_path: str, language_code: str = "uzb", max_retries: int = 3) -> list[dict]:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ScribeError("ELEVENLABS_API_KEY not set")

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    data = None
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = httpx.post(
                API_URL,
                headers={"xi-api-key": api_key},
                data={
                    "model_id": MODEL_ID,
                    "language_code": language_code,
                    "timestamps_granularity": "word",
                    "tag_audio_events": "false",
                },
                files={"file": (os.path.basename(audio_path), audio_bytes)},
                timeout=120,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = ScribeError(f"Scribe API {resp.status_code}: {resp.text}")
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except httpx.RequestError as e:
            last_error = e
            time.sleep(2 ** attempt)

    if data is None:
        raise ScribeError(f"Scribe API failed after {max_retries} attempts: {last_error}")

    words = [
        {"word": w["text"], "start": w["start"], "end": w["end"], "logprob": w.get("logprob")}
        for w in data.get("words", [])
        if w.get("type", "word") == "word"
    ]

    duration_min = (words[-1]["end"] if words else 0) / 60
    cost = duration_min * COST_PER_MINUTE_USD
    print(f"[scribe] {audio_path}: {len(words)} words, ~{duration_min:.2f} min, est. cost ${cost:.4f}")

    return words
