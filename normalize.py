"""Text Normalization Layer: apostrophe unification + Uzbek-Russian code-switching safety."""
import re

CANONICAL_APOSTROPHE = "ʻ"  # ʻ MODIFIER LETTER TURNED COMMA (used by Oʻ, Gʻ)
_APOSTROPHE_VARIANTS = ["'", "’", "‘", "`", "´", "ʼ", "ʹ"]
_APOSTROPHE_RE = re.compile("[" + "".join(re.escape(c) for c in _APOSTROPHE_VARIANTS) + "]")


def normalize_apostrophes(text: str) -> str:
    """Collapse all apostrophe-like chars to U+02BB. Cyrillic text passes through untouched."""
    return _APOSTROPHE_RE.sub(CANONICAL_APOSTROPHE, text)


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def transliterate(text: str, direction: str | None = None) -> str:
    """Latin<->Cyrillic transliteration. Off by default (direction=None passthrough).

    # ponytail: full Uzbek Latin<->Cyrillic lookup table not built yet, add when a
    # style actually needs it (direction="lat2cyr" / "cyr2lat")
    """
    if direction is None:
        return text
    raise NotImplementedError(f"transliteration direction={direction!r} not implemented yet")


def normalize_word(word: str, transliterate_direction: str | None = None) -> str:
    word = normalize_apostrophes(word)
    word = clean_whitespace(word)
    word = transliterate(word, transliterate_direction)
    return word


def normalize_words(words: list[dict], transliterate_direction: str | None = None) -> list[dict]:
    """Apply normalize_word to each {"word", "start", "end"} dict; drops words that go empty."""
    out = []
    for w in words:
        text = normalize_word(w["word"], transliterate_direction)
        if not text:
            continue
        out.append({**w, "word": text})
    return out
