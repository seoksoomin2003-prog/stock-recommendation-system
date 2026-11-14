"""The 모델 tab's side of the terminal: the newest stored scans (US P6-11B, Korean KR-EXP), the stored scores a list can show,
risk settings, the capital box and the button that starts a Korean model scan.

These methods were part of ``Terminal`` in ``services.py`` until 2026-11-14 and are unchanged; ``Terminal`` inherits them.  They
read files the scans wrote and the user's own settings; nothing here scores a stock.
"""
import json
import os
from typing import Any, Dict, Optional

from terminal import portfolio as pf


class ModelViews:
    """Mixed into ``Terminal``; see the module text."""

    def _scan_scores(self, market: str) -> Dict[str, Any]:
        """Swing and long scores from the newest recorded scan, as stored.  Nothing is scored here; a stock outside the scan gets nothing."""
        try:
            latest = self.qsf.latest(market)
        except Exception:
            latest = {"status": "UNAVAILABLE"}
        found: Dict[str, Dict[str, Any]] = {}
        if latest.get("status") == "REAL":
            for r in latest.get("rows") or []:
                found.setdefault(r.get("ticker"), {})[r.get("strategy")] = {k: r.get(k) for k in ("score", "action", "action_label", "actionability", "confidence")}
        return {"status": latest.get("status") or "UNAVAILABLE", "session": latest.get("session"), "model_version": latest.get("model_version"), "by_ticker": found}

    # ---------------------------------------------------------------- model (read-only)
    def _latest_scan(self) -> Optional[Dict[str, Any]]:
        """Latest full US market scan written by the frozen P6-11B pipeline (read-only)."""
        runs = self.base / "runs"
        if not runs.exists():
            return None
        for d in sorted((p for p in runs.iterdir() if p.is_dir()), reverse=True):
            v = d / "validation_result.json"
            if not v.exists():
                continue
            try:
                x = json.loads(v.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if x.get("mode") == "market_scan" and x.get("validation_scope") == "full":
                return x
        return None

    def _model_kr(self) -> Dict[str, Any]:
        base = {"name": "KR-EXP-0.1", "status": "EXPERIMENTAL", "role": "한국 실험 모델, 예측력 미검증"}
        root, latest, empty = self.base / "runs" / "KR", None, None
        for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True) if root.exists() else []:
            try:
                x = json.loads((d / "validation_result.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if x.get("validation_scope") != "full":
                continue
            if x.get("recommendation_status") == "NO VALID RECOMMENDATION" and not x.get("recommendations"):
                empty = empty or x            # a newer scan that scored nothing does not replace the last list; it is named beside it
                continue
            latest = x
            break
        latest, newer_empty = (latest or empty), (empty if latest and empty else None)
        if latest:
            if newer_empty:
                base["newer_empty_scan"] = {"executed_at": newer_empty.get("executed_at"), "latest_session": newer_empty.get("latest_session")}
            base.update(run_id=latest.get("run_id"), executed_at=latest.get("executed_at"), recommendation_status=latest.get("recommendation_status"), latest_session=latest.get("latest_session"),
                        capital=latest.get("capital_krw"), currency=latest.get("currency"),
                        top5=[{"recommendation_rank": r.get("rank"), "ticker": r.get("ticker"), "name": r.get("company_name"), "sector": r.get("industry"), "close": r.get("reference_close_krw"),
                               "alpha": r.get("score"), "target_weight": r.get("target_weight")} for r in latest.get("recommendations") or []])
        try:
            from markets.kr import tracking as krt
            d = self.base / "tracking" / "kr"
            trk = {"status": "REAL", "runs": len(krt.runs(d)), "observations": len(krt.observations(d))}
        except Exception as exc:
            trk = {"status": "UNAVAILABLE", "error": type(exc).__name__}
        return {"market": "KR", "baseline": base, "tracking": trk, "challengers": [], "challenger_note": "도전자 모델과 연구실은 아직 미국 전용입니다."}

    def model(self, market: str = "US") -> Dict[str, Any]:
        if market == "KR":
            return self._model_kr()
        latest = self._latest_scan()
        base = {"name": "P6-11B (MODEL_RANK_E)", "status": "FROZEN", "role": "기준 모델"}
        if latest:
            base.update(run_id=latest["run_id"], executed_at=latest.get("executed_at"),
                        recommendation_status=latest.get("recommendation_status"),
                        regime=latest.get("market_regime"), capital=latest.get("capital"),
                        currency=latest.get("currency"),
                        top5=[{k: r.get(k) for k in ("recommendation_rank", "ticker", "name", "sector", "close",
                                                     "alpha", "target_weight", "target_shares", "hard_stop",
                                                     "entry_1_weight", "entry_2_weight", "horizon_days",
                                                     "explanation")} for r in latest.get("recommendations") or []],
                        watchlist=[{k: r.get(k) for k in ("ticker", "name", "sector", "alpha", "final_status")}
                                   for r in (latest.get("watchlist") or [])[:10]])
        trk = {"status": "UNAVAILABLE"}
        try:
            from pipeline import prospective_tracking as pt
            s = pt.status(str(self.base / "tracking"))
            trk = {"status": "REAL", "runs": s["runs"], "observations": s["observations"],
                   "outcome_states": s.get("outcome_states"),
                   "latest_update": (s.get("latest_update") or {}).get("update_id")}
        except Exception as exc:
            trk = {"status": "UNAVAILABLE", "error": type(exc).__name__}
        return {"baseline": base, "tracking": trk, "challengers": [],
                "challenger_note": "도전자 모델 비교는 아래 표에 있습니다. 기준 모델(P6-11B)은 변경하지 않습니다."}

    # ---------------------------------------------------------------- portfolio (TERMINAL-2)
    def settings(self) -> Dict[str, float]:
        try:
            raw = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return pf.clean_settings(raw, dict(pf.DEFAULT_SETTINGS))
        except (OSError, ValueError):
            return dict(pf.DEFAULT_SETTINGS)

    def settings_set(self, raw: Dict[str, Any]) -> Dict[str, float]:
        new = pf.clean_settings(raw or {}, self.settings())
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({**new, "updated_at": self.now().isoformat()}), encoding="utf-8")
        tmp.replace(self.settings_file)
        return new

    def capital(self, market: str = "US") -> Dict[str, Any]:
        """The capital the next scan will use.  An unusable value reads as not configured, never as a number."""
        from utils.runtime_config import CAPITAL_KEYS, CapitalNotConfigured, parse_capital
        raw = os.getenv(CAPITAL_KEYS[market], "").strip()
        try:
            amount = parse_capital(raw) if raw else None
        except CapitalNotConfigured:
            amount = None
        return {"market": market, "amount": amount, "currency": "KRW" if market == "KR" else "USD", "invalid": bool(raw) and amount is None}

    def capital_set(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        from utils.runtime_config import CapitalNotConfigured, set_capital
        market = (raw or {}).get("market", "US")
        if market not in ("US", "KR"):
            raise ValueError("시장은 US 또는 KR이어야 합니다.")
        try:
            set_capital(market, (raw or {}).get("amount"), self.base / ".env")
        except CapitalNotConfigured:
            raise ValueError("자본금은 0보다 큰 숫자로 입력하세요.") from None
        return self.capital(market)

    def model_scan_start(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Start the Korean model scan from the screen.  The US scan belongs to the daily job; a scan without saved capital is refused."""
        from terminal import model_scan
        if (raw or {}).get("market", "KR") != "KR":
            raise ValueError("미국 스캔은 일일 작업이 실행합니다. 이 버튼은 한국 스캔만 실행합니다.")
        if self.capital("KR")["amount"] is None:
            return {"status": "NO_CAPITAL"}
        return model_scan.start(self.base)
