"""One stock's recorded scores, session by session, read from the ledger.  Read only: nothing is recomputed or written.

A score recorded under one model version is not directly comparable with one recorded under another, so every row
carries its version and the reply says where the version changed.
"""
from typing import Any, Dict

from terminal.qsf import config

DOMAINS = ("TECHNICAL", "FUNDAMENTAL", "RISK", "EVENTS", "REGIME")


def _row(session: str, s: Dict[str, Any]) -> Dict[str, Any]:
    dom = s.get("domains") or {}
    return {"session": session, "model_version": s.get("model_version"), "score": s.get("score"), "band": s.get("band"), "action": s.get("action"), "action_label": config.ACTION_LABELS.get(s.get("action"), s.get("action")),
            "actionability": s.get("actionability"), "confidence": s.get("confidence"), "entry_status": s.get("entry_status"), "price": s.get("price"),
            "data_date": s.get("data_date"), "domains": {d: (dom.get(d) or {}).get("score_100") for d in DOMAINS}}


def history(ledger: Any, market: str, ticker: str) -> Dict[str, Any]:
    if ledger.verify()["status"] != "OK":
        return {"status": "UNAVAILABLE", "reason": "점수 원장 검사에 실패해 이력을 보여 주지 않습니다.", "strategies": {}}
    found: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in ledger._live_rows():
        if r["market"] != market:
            continue
        for s in ledger._load(r):
            if s.get("ticker") == ticker:
                found.setdefault(s["strategy"], {}).setdefault(r["session"], _row(r["session"], s))   # the first record of a session stands, as in the ledger
    out = {}
    for strategy, by_session in found.items():
        rows = [by_session[k] for k in sorted(by_session)]
        for prev, cur in zip(rows, rows[1:]):
            cur["model_changed"] = cur["model_version"] != prev["model_version"]
        if rows:
            rows[0]["model_changed"] = False
        out[strategy] = rows
    return {"status": "REAL" if out else "NO_RECORD", "market": market, "ticker": ticker, "strategies": out,
            "reason": None if out else "이 종목은 아직 점수 원장에 기록된 적이 없습니다."}
