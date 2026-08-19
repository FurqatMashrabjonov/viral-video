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
ZOOM_DURATION = 1.2       # render ramps ~0.22s in and out, so leave room to hold
ZOOM_SCALE = 1.15
HOOK_END = 3.0
LOW_CONFIDENCE_LOGPROB = -1.0  # below this, Scribe was guessing -- flag for review

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


def plan_zooms(words: list[dict], cuts_on_new_timeline: list[float],
               spacing: float = MIN_ZOOM_SPACING, duration: float = ZOOM_DURATION,
               scale: float = ZOOM_SCALE) -> list[dict]:
    """Punch in on keywords and just after each cut, spaced so it doesn't pulse.

    Pure function of the words plus these three numbers, which is what lets the
    renderer recompute zoom placement from changed settings without going back
    to Scribe.
    """
    candidates = [w["start"] for w in words if w.get("keyword")] + cuts_on_new_timeline
    zooms, last = [], -spacing
    for t in sorted(candidates):
        if t - last < spacing:
            continue
        zooms.append({
            "start": round(t, 3),
            "end": round(t + duration, 3),
            "scale": scale,
        })
        last = t
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
    cut_marks = [remap_time(c["start"], cuts) for c in cuts]

    return {
        "source_duration": round(source_duration, 3),
        "output_duration": round(source_duration - sum(c["end"] - c["start"] for c in cuts), 3),
        "cuts": cuts,
        "words": new_words,
        "zooms": plan_zooms(new_words, cut_marks),
        "sfx": plan_sfx(new_words),
        "hook": None,  # filled by llm_enrich()
    }


SYSTEM_PROMPT = """Sen o'zbek tilidagi qisqa vertikal videolar uchun subtitr muharrirsan.

Senga video transkripti beriladi. Ikki narsa qaytar:

1. hook — videoning birinchi 3 soniyasida ekranda turadigan sarlavha.
   - o'zbek tilida, transkript mazmuniga asoslangan
   - eng ko'pi 6 so'z, qisqaroq bo'lsa yaxshiroq
   - tomoshabinni to'xtatadigan: savol, dadil da'vo yoki aniq raqam
   - clickbait emas, transkriptda yo'q narsani va'da qilma

2. keywords — transkriptdagi urg'u berilishi kerak bo'lgan so'zlar, har biriga bitta emoji bilan.
   - word: faqat transkriptda AYNAN uchraydigan so'zni qaytar, o'zgartirmasdan
   - emoji: shu so'z mazmuniga mos BITTA emoji — teri rangi modifikatori yoki
     ZWJ ketma-ketligi (bir nechta emoji birlashgan turi) ishlatma, faqat oddiy
     yakka belgi (masalan 🚗, 💰, ⚠️, 📈)
   - atamalar, ismlar, muhim tushunchalar, natijani bildiruvchi so'zlar
   - har 8-10 so'zga taxminan bittadan, hammasini belgilama
   - "va", "bu", "shu" kabi yordamchi so'zlarga emoji bermang"""

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
    },
    "required": ["hook", "keywords"],
}


def _key(word: str) -> str:
    return word.strip(".,!?:;()\"'«»").casefold()


def _looks_like_one_emoji(s: str) -> bool:
    """Reject anything that isn't plausibly a single glyph: an ASCII letter
    means the model answered in words, and long strings are more likely a ZWJ
    sequence than the plain glyph the prompt asked for."""
    return bool(s) and len(s) <= 3 and not any(c.isascii() and c.isalpha() for c in s)


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

    transcript = " ".join(w["word"] for w in plan["words"])

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

    cut_marks = [remap_time(c["start"], plan["cuts"]) for c in plan["cuts"]]
    plan["zooms"] = plan_zooms(plan["words"], cut_marks)
    plan["sfx"] = plan_sfx(plan["words"])
    n_emoji = sum(1 for w in plan["words"] if w.get("emoji"))
    print(f"[analyze] hook: {plan['hook']['text']!r}, "
          f"{sum(w['keyword'] for w in plan['words'])} keywords, {n_emoji} emoji")
    return plan


def save_plan(plan: dict, path: str):
    Path(path).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
