"""Korean company descriptions in Korean (2026-11-26): the shipped table, the reply field and the screen's fallback."""
import json
import re
from pathlib import Path

from terminal import kr_summary

ROOT = Path(__file__).resolve().parents[1]


def test_the_shipped_table_is_korean_and_names_its_english_source():
    doc = json.loads(kr_summary.FILE.read_text(encoding="utf-8"))
    items = doc["items"]
    assert doc["made_on"] and doc["count"] == len(items) >= 250
    for code, row in items.items():
        assert re.fullmatch(r"[0-9A-Z]{6}", code) and row["en_fp"] and len(row["en_fp"]) == 16
        hangul = sum("가" <= ch <= "힣" for ch in row["ko"])
        assert hangul >= 0.3 * len(row["ko"].replace(" ", "")), code              # Korean text, not the English one copied


def test_a_changed_english_text_keeps_the_korean_one_and_says_so(monkeypatch):
    monkeypatch.setattr(kr_summary, "_table", lambda: {"064350": {"ko": "철도 차량을 만듭니다.", "en_fp": kr_summary.fingerprint("Makes trains.")}})
    same = kr_summary.for_ticker("064350", "Makes  trains.")                     # spacing alone is not a change
    assert same["ko"] == "철도 차량을 만듭니다." and same["english_changed"] is False
    assert kr_summary.for_ticker("064350", "Makes trains and tanks.")["english_changed"] is True
    assert kr_summary.for_ticker("005930", "x") is None


def test_the_screen_shows_korean_first_and_english_when_there_is_none():
    js = (ROOT / "terminal" / "static" / "app.js").read_text(encoding="utf-8")
    assert "function coSummary(p)" in js and "영문 원문 보기" in js and "Yahoo 영문 원문" in js
    assert "kr_summary" in (ROOT / "terminal" / "services.py").read_text(encoding="utf-8")
