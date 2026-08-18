"""Self-check for normalize.py. Run: python test_normalize.py"""
from normalize import normalize_apostrophes, normalize_words


def test_straight_apostrophe():
    assert normalize_apostrophes("O'zbek") == "Oʻzbek"


def test_typographic_apostrophe():
    assert normalize_apostrophes("G’isht") == "Gʻisht"


def test_grave_apostrophe():
    assert normalize_apostrophes("o`quvchi") == "oʻquvchi"


def test_modifier_letter_apostrophe():
    assert normalize_apostrophes("Gʼala") == "Gʻala"


def test_already_canonical_untouched():
    assert normalize_apostrophes("Oʻzbekiston") == "Oʻzbekiston"


def test_cyrillic_untouched():
    text = "Привет, бу дарс жуда яхши"
    assert normalize_apostrophes(text) == text


def test_mixed_uzbek_russian_sentence():
    mixed = "Bugun spasibo aytaman, o'zbekcha va пожалуйста rus tilida gaplashamiz"
    expected = "Bugun spasibo aytaman, oʻzbekcha va пожалуйста rus tilida gaplashamiz"
    assert normalize_apostrophes(mixed) == expected


def test_normalize_words_drops_empty():
    words = [
        {"word": "O'zbek", "start": 0.0, "end": 0.3},
        {"word": "  ", "start": 0.3, "end": 0.3},
        {"word": "tili", "start": 0.4, "end": 0.6},
    ]
    result = normalize_words(words)
    assert [w["word"] for w in result] == ["Oʻzbek", "tili"]


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
