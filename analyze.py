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


def plan_zooms(words: list[dict], cuts_on_new_timeline: list[float]) -> list[dict]:
    """Punch in on keywords and just after each cut, spaced so it doesn't pulse."""
    candidates = [w["start"] for w in words if w.get("keyword")] + cuts_on_new_timeline
    zooms, last = [], -MIN_ZOOM_SPACING
    for t in sorted(candidates):
        if t - last < MIN_ZOOM_SPACING:
            continue
        zooms.append({
            "start": round(t, 3),
            "end": round(t + ZOOM_DURATION, 3),
            "scale": ZOOM_SCALE,
        })
        last = t
    return zooms


def build_edit_plan(words: list[dict], source_duration: float, cut_silence: bool = True) -> dict:
    cuts = find_silences(words) if cut_silence else []
    new_words = mark_keywords(remap_words(words, cuts))
    cut_marks = [remap_time(c["start"], cuts) for c in cuts]

    return {
        "source_duration": round(source_duration, 3),
        "output_duration": round(source_duration - sum(c["end"] - c["start"] for c in cuts), 3),
        "cuts": cuts,
        "words": new_words,
        "zooms": plan_zooms(new_words, cut_marks),
        "hook": None,  # filled by llm_enrich()
    }


SYSTEM_PROMPT = """Sen o'zbek tilidagi qisqa vertikal videolar uchun subtitr muharrirsan.

Senga video transkripti beriladi. Ikki narsa qaytar:

1. hook — videoning birinchi 3 soniyasida ekranda turadigan sarlavha.
   - o'zbek tilida, transkript mazmuniga asoslangan
   - eng ko'pi 6 so'z, qisqaroq bo'lsa yaxshiroq
   - tomoshabinni to'xtatadigan: savol, dadil da'vo yoki aniq raqam
   - clickbait emas, transkriptda yo'q narsani va'da qilma

2. keywords — transkriptdagi urg'u berilishi kerak bo'lgan so'zlar.
   - faqat transkriptda AYNAN uchraydigan so'zlarni qaytar, o'zgartirmasdan
   - atamalar, ismlar, muhim tushunchalar, natijani bildiruvchi so'zlar
   - har 8-10 so'zga taxminan bittadan, hammasini belgilama
   - "va", "bu", "shu" kabi yordamchi so'zlarni belgilama"""

_ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["hook", "keywords"],
}


def _key(word: str) -> str:
    return word.strip(".,!?:;()\"'«»").casefold()


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

    wanted = {_key(k) for k in result.get("keywords", [])}
    for w in plan["words"]:
        if _key(w["word"]) in wanted:
            w["keyword"] = True

    plan["zooms"] = plan_zooms(plan["words"], [remap_time(c["start"], plan["cuts"]) for c in plan["cuts"]])
    print(f"[analyze] hook: {plan['hook']['text']!r}, {sum(w['keyword'] for w in plan['words'])} keywords")
    return plan


def save_plan(plan: dict, path: str):
    Path(path).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
