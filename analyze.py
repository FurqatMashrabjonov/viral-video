"""Word timestamps -> edit_plan.json: cuts, keywords, zooms, hook.

Everything here except the hook text and semantic keywords is pure math on
Scribe's word timings -- no API call needed. The LLM layer (llm_enrich) is
optional and only adds what heuristics cannot infer.

Timeline rule: cuts are computed on the ORIGINAL timeline, then every word is
remapped onto the cut timeline. Downstream code only ever sees remapped times.
"""
import json
import re
import time
from pathlib import Path

MIN_SILENCE_GAP = 0.35      # gaps longer than this get cut
KEEP_PAD = 0.05             # leave a sliver of silence so speech isn't clipped
MIN_ZOOM_SPACING = 3.0      # research: a visual change every 3-5s
MIN_ZOOM_DURATION = 0.6     # floor so a short phrase still clears the ~0.22s ramp in/out
ZOOM_SCALE = 1.15
HOOK_END = 3.0
LOW_CONFIDENCE_LOGPROB = -1.0  # below this, Scribe was guessing -- flag for review
BROLL_MAX_PER_MINUTE = 2.5     # backlog spec: "never more than 2-3 per minute"
BROLL_DISPLAY_SECONDS = 1.6    # a flash cutaway, not a hold -- unlike a zoom span,
                                # this does not stretch to the phrase's own length
BROLL_MIN_SPACING = 8.0        # research: overusing B-roll reads as noisy, not lively

_HAS_DIGIT = re.compile(r"\d")


def find_silences(words: list[dict], min_gap: float = MIN_SILENCE_GAP) -> list[dict]:
    """Gaps between consecutive words. Scribe already gives us this for free."""
    cuts = []
    for prev, nxt in zip(words, words[1:]):
        gap = nxt["start"] - prev["end"]
        if gap > min_gap:
            start = prev["end"] + KEEP_PAD
            end = nxt["start"] - KEEP_PAD
            if end > start:
                cuts.append({"start": round(start, 3), "end": round(end, 3), "reason": "silence"})
    return cuts


def remap_time(t: float, cuts: list[dict]) -> float:
    """Shift a time onto the cut timeline: subtract every cut that ended before it."""
    removed = sum(c["end"] - c["start"] for c in cuts if c["end"] <= t)
    return round(t - removed, 3)


def remap_words(words: list[dict], cuts: list[dict]) -> list[dict]:
    """Words that fall inside a cut are dropped (silence cuts hold none, but guard anyway)."""
    out = []
    for w in words:
        if any(c["start"] <= w["start"] and w["end"] <= c["end"] for c in cuts):
            continue
        out.append({**w, "start": remap_time(w["start"], cuts), "end": remap_time(w["end"], cuts)})
    return out


def mark_keywords(words: list[dict]) -> list[dict]:
    """Heuristic pass: numbers, percentages, money, shouted words.

    # ponytail: numbers only -- semantic Uzbek keywords need llm_enrich().
    # Research says stats/numbers are the highest-value highlight targets anyway,
    # so this alone carries most of the effect.
    """
    out = []
    for w in words:
        text = w["word"]
        bare = text.strip(".,!?:;()")
        is_kw = bool(_HAS_DIGIT.search(text)) or (len(bare) > 2 and bare.isupper())
        out.append({**w, "keyword": is_kw})
    return out


def mark_low_confidence(words: list[dict], threshold: float = LOW_CONFIDENCE_LOGPROB) -> list[dict]:
    """Flag words Scribe was unsure about, so the editor can point the user at
    exactly those instead of making them re-read the whole transcript.

    A missing logprob (older API response, or the field genuinely absent) is
    left unflagged -- silence is not evidence of a bad guess.
    """
    out = []
    for w in words:
        lp = w.get("logprob")
        out.append({**w, "low_confidence": lp is not None and lp < threshold})
    return out


def zooms_from_spans(spans: list[dict], spacing: float = MIN_ZOOM_SPACING,
                     min_duration: float = MIN_ZOOM_DURATION, scale: float = ZOOM_SCALE) -> list[dict]:
    """Punch in on emphasised phrases, not keywords.

    A keyword marks one word for a subtitle highlight; a zoom is a camera move
    for a whole sentence that matters. Conflating the two meant a ten-keyword
    line camera-punched ten times in ten seconds. Spans come from the LLM
    (llm_enrich's emphasis_spans, already resolved to seconds) -- each covers a
    real phrase, so the zoom holds for the phrase's own length rather than a
    fixed duration.

    Pure function of the spans plus these three numbers, which is what lets the
    renderer recompute zoom placement from changed settings without going back
    to Scribe.
    """
    zooms, last_end = [], float("-inf")
    for span in sorted(spans, key=lambda s: s["start"]):
        start = span["start"]
        if start - last_end < spacing:
            continue
        end = max(span["end"], start + min_duration)
        zooms.append({"start": round(start, 3), "end": round(end, 3), "scale": scale})
        last_end = end
    return zooms


SFX_MIN_SPACING = 1.5   # closer than this and emphasis turns into a rattle


def plan_sfx(words: list[dict], min_spacing: float = SFX_MIN_SPACING) -> list[dict]:
    """One hit per emphasised word: a chime on numbers, a blip on everything else."""
    events, last = [], -min_spacing
    for w in words:
        if not w.get("keyword") or w["start"] - last < min_spacing:
            continue
        events.append({
            "time": round(w["start"], 3),
            "name": "ding" if _HAS_DIGIT.search(w["word"]) else "pop",
        })
        last = w["start"]
    return events


def build_edit_plan(words: list[dict], source_duration: float, cut_silence: bool = True) -> dict:
    cuts = find_silences(words) if cut_silence else []
    new_words = mark_low_confidence(mark_keywords(remap_words(words, cuts)))

    return {
        "source_duration": round(source_duration, 3),
        "output_duration": round(source_duration - sum(c["end"] - c["start"] for c in cuts), 3),
        "cuts": cuts,
        "words": new_words,
        "emphasis_spans": [],  # filled by llm_enrich() -- heuristics can't judge what a sentence means
        "zooms": [],
        "broll_spans": [],
        "broll": [],
        "sfx": plan_sfx(new_words),
        "hook": None,  # filled by llm_enrich()
    }


SYSTEM_PROMPT = """Sen o'zbek tilidagi qisqa vertikal videolar uchun subtitr muharrirsan.

Senga video transkripti so'z raqamlari bilan beriladi: "0:Bugun 1:reklama 2:byudjetini ...".
Uchta narsa qaytar:

1. hook — videoning birinchi 3 soniyasida ekranda turadigan sarlavha.
   - o'zbek tilida, transkript mazmuniga asoslangan
   - eng ko'pi 6 so'z, qisqaroq bo'lsa yaxshiroq
   - tomoshabinni to'xtatadigan: savol, dadil da'vo yoki aniq raqam
   - clickbait emas, transkriptda yo'q narsani va'da qilma

2. keywords — transkriptdagi urg'u berilishi kerak bo'lgan SO'ZLAR (subtitrda rang bilan
   ajratish uchun), har biriga bitta emoji bilan.
   - word: faqat transkriptda AYNAN uchraydigan so'zni qaytar, raqamsiz, o'zgartirmasdan
   - emoji: shu so'z mazmuniga mos BITTA emoji — teri rangi modifikatori yoki
     ZWJ ketma-ketligi (bir nechta emoji birlashgan turi) ishlatma, faqat oddiy
     yakka belgi (masalan 🚗, 💰, ⚠️, 📈)
   - atamalar, ismlar, muhim tushunchalar, natijani bildiruvchi so'zlar
   - har 8-10 so'zga taxminan bittadan, hammasini belgilama
   - "va", "bu", "shu" kabi yordamchi so'zlarga emoji bermang

3. emphasis_spans — videoning eng muhim GAPLARI, kamera yaqinlashishi (zoom) uchun.
   - BUTUNLAY ALOHIDA tushuncha keywords'dan: keywords bitta so'zni subtitrda
     ranglaydi, emphasis_spans esa butun gapni kamera bilan urg'ulaydi
   - start_index / end_index — transkriptdagi so'z raqamlari (ikkalasi ham kiritiladi)
   - HAR BIR span kamida 2 ta so'zdan iborat bo'lsin — bitta so'z hech qachon emas
   - butun video uchun 2 tadan 4 tagacha, ko'proq emas — faqat haqiqatan asosiy
     xulosa, natija yoki da'vo bo'lgan gaplarni tanla, har jumlaga emas

4. broll_spans — gapda KONKRET, KO'RGAZMALI narsa tasvirlangan joylar (masalan
   "avtomobil", "ofisda uchrashuv", "pul sanash") — bir soniyalik stok video
   bilan ko'rsatilishi mumkin bo'lgan tushunchalar.
   - start_index / end_index — o'sha tushuncha aytilgan so'zlar oralig'i
   - query_en — Pexels’dan qidirish uchun INGLIZCHA 1-3 so'zlik so'rov
     (masalan "car driving", "office meeting", "counting money")
   - mavhum yoki hissiy gaplarga (masalan his-tuyg'u, xulosa) broll bermang —
     faqat aniq, jismoniy tasvirlanadigan narsalarga
   - daqiqasiga 2 tadan oshmasin, hammasiga emas — eng ko'zga ko'rinadigan
     2-3 tasini tanla"""

_ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "keywords": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "emoji": {"type": "string"},
                },
                "required": ["word", "emoji"],
            },
        },
        "emphasis_spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_index": {"type": "integer"},
                    "end_index": {"type": "integer"},
                },
                "required": ["start_index", "end_index"],
            },
        },
        "broll_spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_index": {"type": "integer"},
                    "end_index": {"type": "integer"},
                    "query_en": {"type": "string"},
                },
                "required": ["start_index", "end_index", "query_en"],
            },
        },
    },
    "required": ["hook", "keywords", "emphasis_spans", "broll_spans"],
}


def _looks_like_a_query(s) -> bool:
    """Reject an empty, absurdly long, or non-string answer -- the schema
    requires the field, but a required string field can still be ''.  Loanwords
    and place names can be non-ASCII, so this only bounds length, it doesn't
    demand pure ASCII."""
    return isinstance(s, str) and 0 < len(s.strip()) <= 40


def plan_broll(spans: list[dict], video_duration: float, spacing: float = BROLL_MIN_SPACING,
               display_seconds: float = BROLL_DISPLAY_SECONDS,
               max_per_minute: float = BROLL_MAX_PER_MINUTE) -> list[dict]:
    """Turn resolved {start, end, query} spans into short, spaced-out flashes.

    Two things distinguish this from zooms_from_spans: the display window is a
    fixed short duration anchored at the span's own start rather than
    stretched to cover the phrase (a cutaway is a flash, not a hold), and the
    whole list is capped by video length -- a 90s clip earning the same 2-3
    inserts as a 20s one would read as noisy, not lively.
    """
    # round(), not int(x+0.5): Python's round() rounds half-to-even, so a
    # duration landing exactly on a .5 boundary (e.g. 12s at 2.5/min -> 0.5)
    # would silently round down to 0 half the time.
    cap = max(0, int(video_duration / 60 * max_per_minute + 0.5))
    clips, last_end = [], float("-inf")
    for span in sorted(spans, key=lambda s: s["start"]):
        if len(clips) >= cap:
            break
        start = span["start"]
        if start - last_end < spacing:
            continue
        end = min(start + display_seconds, video_duration)
        if end - start < 0.4:  # too close to the end of the video to be worth a flash
            continue
        clips.append({"start": round(start, 3), "end": round(end, 3), "query": span["query"]})
        last_end = end
    return clips


def _key(word: str) -> str:
    return word.strip(".,!?:;()\"'«»").casefold()


def _looks_like_one_emoji(s: str) -> bool:
    """Reject anything that isn't plausibly a single glyph: an ASCII letter
    means the model answered in words, and long strings are more likely a ZWJ
    sequence than the plain glyph the prompt asked for."""
    return bool(s) and len(s) <= 3 and not any(c.isascii() and c.isalpha() for c in s)


def _resolve_span_times(words: list[dict], start_index, end_index) -> dict | None:
    """A model-given word-index pair -> real start/end seconds.

    Indices are clamped into range and sorted rather than trusted, since a
    model response is an input from outside the program, not a guarantee.
    None if the span doesn't survive that -- out of range entirely, or
    collapsing to a single word once clamped, which the prompt already asked
    the model not to send but a strict schema doesn't stop it from doing.
    """
    n = len(words)
    if n == 0:
        return None
    try:
        i, j = sorted((int(start_index), int(end_index)))
    except (TypeError, ValueError):
        return None
    i, j = max(0, min(i, n - 1)), max(0, min(j, n - 1))
    if j <= i:
        return None
    return {"start": words[i]["start"], "end": words[j]["end"]}


def llm_enrich(plan: dict, model: str = "gemini-3.5-flash", max_retries: int = 3) -> dict:
    """Fill in the hook title and mark semantic keywords the heuristics can't see.

    Mutates and returns the plan. Heuristic keywords (numbers) are kept -- this
    only ever adds. On any API failure the plan is returned unchanged, because a
    missing hook is worth far less than a failed render.
    """
    import os
    from google import genai
    from google.genai import types
    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY not set")

    # Indexed so the model can name a phrase by word position instead of
    # reproducing text -- exact, and immune to a word appearing twice.
    transcript = " ".join(f"{i}:{w['word']}" for i, w in enumerate(plan["words"]))

    client = genai.Client()  # keep a reference; a temporary gets closed mid-call
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=_ENRICH_SCHEMA,
        temperature=0.4,
    )

    result = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.models.generate_content(
                model=model, contents=f"Transkript:\n{transcript}", config=config
            )
            result = json.loads(resp.text)
            break
        except Exception as e:
            # 503/429 are Gemini capacity blips and clear on their own; anything
            # else won't improve by asking twice.
            if attempt == max_retries or not any(c in str(e) for c in ("503", "429", "UNAVAILABLE")):
                print(f"[analyze] llm_enrich failed, keeping heuristic plan: {e}")
                return plan
            time.sleep(2 ** attempt)

    if result is None:
        return plan

    plan["hook"] = {"text": result["hook"].strip(), "start": 0.0, "end": HOOK_END}

    wanted = {}
    for item in result.get("keywords", []):
        emoji = item.get("emoji", "")
        wanted[_key(item.get("word", ""))] = emoji if _looks_like_one_emoji(emoji) else None

    for w in plan["words"]:
        key = _key(w["word"])
        if key in wanted:
            w["keyword"] = True
            if wanted[key]:
                w["emoji"] = wanted[key]

    spans = []
    for item in result.get("emphasis_spans", []):
        resolved = _resolve_span_times(plan["words"], item.get("start_index"), item.get("end_index"))
        if resolved:
            spans.append(resolved)
    plan["emphasis_spans"] = spans
    plan["zooms"] = zooms_from_spans(spans)
    plan["sfx"] = plan_sfx(plan["words"])

    broll_spans = []
    for item in result.get("broll_spans", []):
        resolved = _resolve_span_times(plan["words"], item.get("start_index"), item.get("end_index"))
        query = item.get("query_en", "")
        if resolved and _looks_like_a_query(query):
            broll_spans.append({**resolved, "query": query.strip()})
    plan["broll_spans"] = broll_spans
    video_duration = plan.get("output_duration") or plan.get("source_duration") or 0.0
    plan["broll"] = plan_broll(broll_spans, video_duration)

    n_emoji = sum(1 for w in plan["words"] if w.get("emoji"))
    print(f"[analyze] hook: {plan['hook']['text']!r}, "
          f"{sum(w['keyword'] for w in plan['words'])} keywords, {n_emoji} emoji, "
          f"{len(spans)} emphasis spans, {len(plan['broll'])} broll")
    return plan


def save_plan(plan: dict, path: str):
    Path(path).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
