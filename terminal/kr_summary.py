"""Korean company descriptions in Korean (2026-11-26, user request).

Yahoo gives every Korean company's description in English only.  The 300 stocks of the Korean scan (market-value top 300 on
2026-11-26) plus the held and watched Korean stocks were translated once from Yahoo's own English text and kept in
``kr_summary_ko.json`` beside this module, so the translation ships with the program and needs no service or key.  Each entry
keeps a fingerprint of the English text it was made from: when Yahoo's text changes later the Korean one is still shown, with a
note that the English original is newer.  A stock without an entry shows Yahoo's English text, labelled as such.
This is a reading aid: no score, label or rule reads it."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

FILE = Path(__file__).with_name("kr_summary_ko.json")
SOURCE = "Yahoo 영문 회사 설명을 한국어로 옮긴 것"


def fingerprint(text: Optional[str]) -> Optional[str]:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:16] if text else None


@lru_cache(maxsize=1)
def _table() -> Dict[str, Dict[str, Any]]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8")).get("items") or {}
    except (OSError, ValueError):
        return {}


def meta() -> Dict[str, Any]:
    try:
        doc = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: doc.get(k) for k in ("made_on", "count")}


def for_ticker(ticker: str, english: Optional[str]) -> Optional[Dict[str, Any]]:
    """{"ko", "made_on", "english_changed", "source"} or None when this stock has no Korean text."""
    row = _table().get(ticker)
    if not row or not row.get("ko"):
        return None
    now = fingerprint(english)
    return {"ko": row["ko"], "made_on": meta().get("made_on"), "english_changed": bool(now and row.get("en_fp") and now != row["en_fp"]), "source": SOURCE}
