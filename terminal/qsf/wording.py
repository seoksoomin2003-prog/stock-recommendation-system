"""The words beside a score (rules R-2, user decision 2026-11-25 after the BT-1 backtest and the five-seat debate).

No band of 70 or more beat the index in the record of any of the four scores (reports/qsf/QSF_BACKTEST_CURRENT_*.json, eleven
of twelve cells below it), and the lowest fifth did not lose in the current universes.  So a band is named by its place, not by
what to do: the codes, the lines of 70 and 80 and the recorded score are unchanged, and the records go on reading the codes.

The word "매수 후보" comes back for one score only when that score's own live verdict (or one of its registered continuation
readings) reads WEAK_POSITIVE_EVIDENCE: rank and money both.  RANK_ONLY earns nothing more than the place name it already has.
At a true rank correlation of 0.05 that verdict passes about 7 to 9% of the time, so the neutral names are likely to stay for
years; that is said in reports/QSF_AFTER_VERDICT_RULES_2026_11_25.md.  The check reads the verdict files: nobody has to act.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

RESTORED = {"STRONG_BUY_CANDIDATE": "강력 매수 후보", "BUY_CANDIDATE": "매수 후보"}
PASS = "WEAK_POSITIVE_EVIDENCE"
CONTINUE_AT = (480, 720, 960)           # live_forward.CONTINUE: the swing verdict's registered later readings
_seen: Dict[Tuple[str, str, str], Tuple[Tuple[float, ...], bool]] = {}


def _files(base: Path, market: str, strategy: str):
    d = Path(base) / "reports" / "qsf"
    yield d / f"QSF_LIVE_FORWARD_{market}_{strategy}.json"
    if strategy == "SWING":
        for n in CONTINUE_AT:
            yield d / f"QSF_LIVE_FORWARD_CONT_{market}_SWING_{n}.json"


def earned(base: Path, market: str, strategy: str) -> bool:
    """Has this score's live verdict, or a continuation reading of it, read rank and money both?  Missing or unreadable: no."""
    files = list(_files(base, market, strategy))
    stamp = tuple(f.stat().st_mtime if f.exists() else 0.0 for f in files)
    key = (str(base), market, strategy)
    if key in _seen and _seen[key][0] == stamp:
        return _seen[key][1]
    ok = False
    for f in files:
        try:
            ok = ok or (f.exists() and json.loads(f.read_text(encoding="utf-8")).get("verdict") == PASS)
        except (OSError, ValueError, AttributeError):
            continue
    _seen[key] = (stamp, ok)
    return ok


def restore(res: Dict[str, Any], base: Path, market: str, strategy: str) -> Dict[str, Any]:
    """The card's band and action words, with "매수 후보" given back when the score has earned it.  Nothing else is touched."""
    word = RESTORED.get(res.get("band") or "")
    if not word or not earned(base, market, strategy):
        return res
    out = dict(res)
    label = str(res.get("band_label") or "")
    for neutral in ("최상위 구간", "상위 구간"):
        if label.startswith(neutral):
            out["band_label"] = word + label[len(neutral):]
            break
    if res.get("action") == "BUY":
        out["action_label"] = "매수 후보"
    out["buy_word_earned"] = True
    return out
