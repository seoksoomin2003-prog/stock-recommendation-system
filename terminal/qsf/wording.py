"""The words beside a score (rules R-2, user decision 2026-11-25 after the BT-1 backtest and the five-seat debate).

No band of 70 or more beat the index in the record of any of the four scores (reports/qsf/QSF_BACKTEST_CURRENT_*.json, eleven
of twelve cells below it), and the lowest fifth did not lose in the current universes.  So a band is named by its place, not by
what to do: the codes, the lines of 70 and 80 and the recorded score are unchanged, and the records go on reading the codes.

The word "매수 후보" comes back for one score only when that score's own live verdict (or one of its registered continuation
readings) reads WEAK_POSITIVE_EVIDENCE: rank and money both.  RANK_ONLY earns nothing more than the place name it already has.
At a true rank correlation of 0.05 that verdict passes about 7 to 9% of the time, so the neutral names are likely to stay for
years; that is said in reports/QSF_AFTER_VERDICT_RULES_2026_11_25.md.  The check reads the verdict files: nobody has to act.

What counts as a passed verdict (tightened the same day after the audit's red team, user decisions 2026-11-25,
reports/score_reliability_audit_2026_11_25/AGENT_08_INDEPENDENT_RED_TEAM.md; fixed before any outcome of the sample matured):
  * the file is the one this program wrote: its hash is in the seal list written with it (a hand-made or edited file is not);
  * it is the right reading: REAL, this market and strategy, the registered horizon, exactly the registered number of sessions,
    a sample that starts at or after the first session of the verdicts;
  * the word in it is backed by its own figures: all five rank conditions, the money condition, t at or over the bar;
  * three more figures the report already carries, for the WORD only (the verdict's conditions are untouched): the band beats the
    index on prices alone too (no dividend on either side), the score effect is positive in both halves, and the median spread
    is positive.  The money condition is a sign test without a bar and is met 14 to 41% of the time with no score effect at all;
  * the formula it read is the formula in force: one model version in the sample, equal to config.MODEL_VERSION.  This is the way
    back down: when the formula changes, the word leaves by itself.  A damaged or missing file takes it away too;
  * a continuation reading counts only with every reading before it on file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RESTORED = {"STRONG_BUY_CANDIDATE": "강력 매수 후보", "BUY_CANDIDATE": "매수 후보"}
PASS = "WEAK_POSITIVE_EVIDENCE"
CONTINUE_AT = (480, 720, 960)           # live_forward.CONTINUE: the swing verdict's registered later readings
SEALS = Path("data") / "qsf" / "verdict_seals.json"
_seen: Dict[Tuple[str, str, str], Tuple[Tuple, bool]] = {}


def _files(base: Path, market: str, strategy: str) -> List[Tuple[Path, Optional[int]]]:
    """(file, sessions of a continuation reading or None for the verdict itself), in the order they are read."""
    d = Path(base) / "reports" / "qsf"
    out: List[Tuple[Path, Optional[int]]] = [(d / f"QSF_LIVE_FORWARD_{market}_{strategy}.json", None)]
    if strategy == "SWING":
        out += [(d / f"QSF_LIVE_FORWARD_CONT_{market}_SWING_{n}.json", n) for n in CONTINUE_AT]
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seals(base: Path) -> Dict[str, str]:
    try:
        got = json.loads((Path(base) / SEALS).read_text(encoding="utf-8"))
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def seal(base: Path, path: Path) -> None:
    """Called by the reading right after it wrote its report: the file's hash, kept apart from the report folder."""
    from utils import durable
    doc = _seals(base)
    doc[Path(path).name] = _sha(Path(path))
    target = Path(base) / SEALS
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True))


def _read(base: Path, path: Path, seals: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """The report when it is whole and is the file the reading wrote; otherwise None."""
    try:
        if not path.exists() or seals.get(path.name) != _sha(path):
            return None
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _is_reading(doc: Optional[Dict[str, Any]], market: str, strategy: str) -> bool:
    return bool(doc) and doc.get("status") == "REAL" and doc.get("market") == market and doc.get("strategy") == strategy


def why_not(doc: Optional[Dict[str, Any]], market: str, strategy: str, sessions: Optional[int] = None) -> List[str]:
    """The checks a report fails as codes; an empty list means it gives the word back.  ``sessions``: a continuation reading's count."""
    from terminal.qsf import config, live_forward as lf
    if not _is_reading(doc, market, strategy):
        return ["NOT_THIS_READING"]
    gt = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0      # noqa: E731
    out = []
    if doc.get("horizon") != lf.PRIMARY[strategy] or doc.get("sessions_used") != (sessions or lf.NEED[strategy]) or str(doc.get("first") or "") < lf.FIRST:
        out.append("NOT_THE_REGISTERED_SAMPLE")
    primary, a = doc.get("primary") or {}, doc.get("condition_a") or {}
    t, bar = primary.get("t"), primary.get("t_bar")
    if not (doc.get("verdict") == PASS and len(a) >= 5 and all(v is True for v in a.values()) and doc.get("condition_b") is True and gt(bar) and isinstance(t, (int, float)) and t >= bar):
        out.append("VERDICT_NOT_BACKED")
    ms = doc.get("money_split") or {}
    if not (ms.get("condition_b_price_only") is True and gt((ms.get("early") or {}).get("score_effect")) and gt((ms.get("late") or {}).get("score_effect"))
            and gt((primary.get("all") or {}).get("spread_median"))):
        out.append("MONEY_CHECKS")
    versions = list(doc.get("by_version") or {}) if sessions is None else list(doc.get("versions") or [])
    if versions != [config.MODEL_VERSION]:
        out.append("ANOTHER_FORMULA")
    return out


def earned(base: Path, market: str, strategy: str) -> bool:
    """Has this score's live verdict, or a continuation reading of it, earned the word by every check above?  Anything missing,
    unreadable, unsealed or of another formula: no."""
    from terminal.qsf import config
    files = _files(base, market, strategy)
    seal_file = Path(base) / SEALS
    stamp = (config.MODEL_VERSION, seal_file.stat().st_mtime if seal_file.exists() else 0.0, *(f.stat().st_mtime if f.exists() else 0.0 for f, _ in files))
    key = (str(base), market, strategy)
    if key in _seen and _seen[key][0] == stamp:
        return _seen[key][1]
    seals, ok, before = _seals(base), False, True
    for path, n in files:
        doc = _read(base, path, seals)
        if before and not why_not(doc, market, strategy, n):          # every earlier reading is on file and whole
            ok = True
            break
        before = before and _is_reading(doc, market, strategy)
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


# A scan stored before R-2 keeps the labels of its day in its rows (the ledger keeps codes only).  The screen names a band by
# today's rules whenever it reads a stored row: the stored file is not rewritten.
BEFORE_R2 = (("강력 매수 후보", "최상위 구간"), ("매수 후보", "상위 구간"), ("약세·축소 후보", "하위 구간"), ("매도·회피 후보", "최하위 구간"))


def relabel(row: Dict[str, Any], base: Path, market: str) -> Dict[str, Any]:
    """``row`` of a stored scan with its band and action named by the rules in force (and the buy word, where earned)."""
    from terminal.qsf import config
    out = dict(row)
    label = out.get("band_label")
    if isinstance(label, str):
        for old, new in BEFORE_R2:
            label = label.replace(old, new)
        out["band_label"] = label
    if out.get("action") in config.ACTION_LABELS:
        out["action_label"] = config.ACTION_LABELS[out["action"]]
    return restore(out, base, market, str(out.get("strategy") or ""))
