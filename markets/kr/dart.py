"""OpenDART adapter and Korean financial-statement normalizer (KR-DATA-0.1 §4).

Endpoints (verified against https://opendart.fss.or.kr/guide, 2026-11-04):
  corpCode.xml            ZIP with corp_code / corp_name / stock_code / modify_date
  fnlttSinglAcntAll.json  full statements: corp_code, bsns_year (>= 2015), reprt_code
                          (11013 Q1, 11012 half, 11014 Q3, 11011 annual), fs_div (CFS consolidated / OFS separate)
  Status codes: 000 ok, 013 no data, 020 request limit (normally 20,000/day), 010/011/901 key problems.
The key is read from ``OPENDART_API_KEY``; it is never logged, echoed in errors or written to artifacts.

Normalisation rules
* consolidated (CFS) and separate (OFS) observations are kept apart (``basis``); a metric is never built
  from both.
* income-statement amounts: annual report -> fiscal-year flow; quarterly/half reports -> ``thstrm_amount``
  is the 3-month figure and ``thstrm_add_amount`` the year-to-date figure (both kept, labelled).
* balance-sheet amounts are instants at the period end.
* receipt date = first 8 digits of ``rcept_no`` (OpenDART receipt number); an observation is usable at an
  as-of instant only if its receipt date is strictly before the as-of KST date (no receipt time exists).
* account mapping by XBRL ``account_id`` via ``account_mapping.REGISTRY`` only.
"""
import io
import json
import os
import time
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests

from markets.kr import KR_ACCOUNT_MAPPING_VERSION
from markets.kr.account_mapping import NON_STANDARD_ACCOUNT, REGISTRY

DART_BASE = "https://opendart.fss.or.kr/api"
REPORT_CODES = {"11013": "Q1", "11012": "H1", "11014": "Q3", "11011": "FY"}
FS_BASIS = {"CFS": "CONSOLIDATED", "OFS": "SEPARATE"}


class DartUnavailable(RuntimeError):
    pass


class OpenDartClient:
    def __init__(self, api_key: Optional[str] = None, http=None, pause: float = 0.2, sleep=time.sleep):
        self._key = api_key if api_key is not None else os.getenv("OPENDART_API_KEY", "")
        self.http, self.pause, self.sleep = http or requests, pause, sleep
        self.requests = 0

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _get(self, endpoint: str, **params):
        if not self.configured:
            raise DartUnavailable("OPENDART_API_KEY_MISSING")
        self.requests += 1
        r = self.http.get(f"{DART_BASE}/{endpoint}", params={"crtfc_key": self._key, **params}, timeout=30)
        self.sleep(self.pause)
        if r.status_code != 200:
            raise DartUnavailable(f"HTTP_{r.status_code}")
        return r

    def corp_codes(self) -> pd.DataFrame:
        r = self._get("corpCode.xml")
        return parse_corp_codes(r.content)

    def statements(self, corp_code: str, year: int, reprt_code: str, fs_div: str) -> Dict:
        r = self._get("fnlttSinglAcntAll.json", corp_code=corp_code, bsns_year=str(year),
                      reprt_code=reprt_code, fs_div=fs_div)
        payload = r.json()
        status = payload.get("status")
        if status == "000":
            return {"status": "REAL", "list": payload.get("list") or []}
        if status == "013":
            return {"status": "UNAVAILABLE", "reason": "DART_NO_DATA", "list": []}
        if status == "020":
            raise DartUnavailable("DART_REQUEST_LIMIT_EXCEEDED")
        raise DartUnavailable(f"DART_STATUS_{status}")


def parse_corp_codes(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        xml = z.read(z.namelist()[0])
    root = ET.fromstring(xml)
    rows = [{k: (el.findtext(k) or "").strip() for k in ("corp_code", "corp_name", "stock_code", "modify_date")}
            for el in root.iter("list")]
    df = pd.DataFrame(rows)
    return df[df["stock_code"] != ""].reset_index(drop=True)


def _amount(v) -> float:
    if v is None:
        return np.nan
    s = str(v).replace(",", "").strip()
    if s in ("", "-"):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def fiscal_period(year: int, reprt_code: str, fiscal_month: int = 12) -> Dict[str, str]:
    """Period dates derived from the settlement month (KIND 결산월); recorded as DERIVED."""
    fy_end = pd.Timestamp(year=year, month=fiscal_month, day=1) + pd.offsets.MonthEnd(0)
    fy_start = (fy_end - pd.DateOffset(years=1) + pd.Timedelta(days=1)).normalize()
    months = {"11013": 3, "11012": 6, "11014": 9, "11011": 12}[reprt_code]
    end = (fy_start + pd.DateOffset(months=months) - pd.Timedelta(days=1))
    q_start = (end - pd.DateOffset(months=3) + pd.Timedelta(days=1))
    return {"fiscal_year": year, "fiscal_period": REPORT_CODES[reprt_code],
            "fy_start": str(fy_start.date()), "period_end": str(end.date()),
            "quarter_start": str(q_start.normalize().date()), "derivation": "settlement month (KIND 결산월)"}


def normalize_statements(rows: List[Dict], *, corp_code: str, ticker: str, year: int, reprt_code: str,
                         fs_div: str, fiscal_month: int = 12, retrieved_at: str = "") -> List[Dict]:
    """One observation per (account row, amount type).  Nothing is mapped here except by account_id."""
    per = fiscal_period(year, reprt_code, fiscal_month)
    annual = reprt_code == "11011"
    obs = []
    for r in rows:
        sj = r.get("sj_div")
        acc_id = r.get("account_id") or ""
        rcept = str(r.get("rcept_no") or "")
        base = {"market": "KR", "ticker": ticker, "corp_code": corp_code, "provider": "opendart",
                "endpoint": "fnlttSinglAcntAll", "rcept_no": rcept or None,
                "receipt_date": f"{rcept[:4]}-{rcept[4:6]}-{rcept[6:8]}" if len(rcept) >= 8 else None,
                "basis": FS_BASIS.get(fs_div, fs_div), "fs_div": fs_div, "reprt_code": reprt_code,
                **per, "statement": sj, "account_id": acc_id, "account_name": r.get("account_nm"),
                "account_detail": r.get("account_detail"), "currency": r.get("currency") or "KRW",
                "unit": "KRW/share" if "EarningsLossPerShare" in acc_id else "KRW",
                "retrieved_at": retrieved_at, "mapping_version": KR_ACCOUNT_MAPPING_VERSION}
        if sj == "BS":
            obs.append({**base, "amount_type": "INSTANT", "period_start": None,
                        "value": _amount(r.get("thstrm_amount"))})
        elif sj in ("IS", "CIS", "CF"):
            if annual:
                obs.append({**base, "amount_type": "FY", "period_start": per["fy_start"],
                            "value": _amount(r.get("thstrm_amount"))})
            else:
                if sj != "CF":   # CF in quarterly reports is year-to-date
                    obs.append({**base, "amount_type": "QUARTER_3M", "period_start": per["quarter_start"],
                                "value": _amount(r.get("thstrm_amount"))})
                ytd = r.get("thstrm_add_amount") if sj != "CF" else r.get("thstrm_amount")
                obs.append({**base, "amount_type": "YTD", "period_start": per["fy_start"], "value": _amount(ytd)})
        # SCE (statement of changes in equity) rows are not used for concepts in KR-ACCT-0.1
    return obs


def extract_concepts(observations: List[Dict], industry_class: str, amount_type: str = "FY",
                     as_of_date: Optional[str] = None) -> Dict[str, Dict]:
    """Map normalised observations to registry concepts for ONE (filing, basis).  Returns
    concept -> {status, value, ...provenance} with status REAL / UNAVAILABLE / NOT_APPLICABLE."""
    bases = {o["basis"] for o in observations}
    if len(bases) > 1:
        raise ValueError("extract_concepts requires observations of a single basis (never CFS+OFS mixed)")
    out = {}
    for concept, d in REGISTRY.items():
        if industry_class not in d["applicability"]:
            out[concept] = {"status": "NOT_APPLICABLE", "reason": f"NOT_APPLICABLE_FOR_{industry_class}"}
            continue
        want = "INSTANT" if d["kind"] == "INSTANT" else amount_type
        cands = [o for o in observations if o["account_id"] in d["account_ids"] and o["statement"] in d["statements"]
                 and o["amount_type"] == want and o["account_id"] != NON_STANDARD_ACCOUNT]
        if as_of_date:
            cands = [o for o in cands if o.get("receipt_date") and o["receipt_date"] < as_of_date]
        finite = [o for o in cands if np.isfinite(o["value"])]
        if not finite:
            reason = "NOT_REPORTED_UNDER_STANDARD_ACCOUNT" if not cands else "VALUE_MISSING"
            if as_of_date and not cands and any(o["account_id"] in d["account_ids"] for o in observations):
                reason = "RECEIVED_ON_OR_AFTER_AS_OF"
            out[concept] = {"status": "UNAVAILABLE", "reason": reason}
            continue
        # statement precedence (IS before CIS) then a single value; conflicting duplicates -> UNAVAILABLE
        pref = sorted(finite, key=lambda o: d["statements"].index(o["statement"]))
        vals = {o["value"] for o in pref if o["statement"] == pref[0]["statement"]}
        if len(vals) > 1:
            out[concept] = {"status": "UNAVAILABLE", "reason": "AMBIGUOUS_DUPLICATE_ACCOUNT_ROWS"}
            continue
        o = pref[0]
        out[concept] = {"status": "REAL", "value": o["value"], "account_id": o["account_id"],
                        "account_name": o["account_name"], "statement": o["statement"], "basis": o["basis"],
                        "amount_type": o["amount_type"], "period_start": o["period_start"],
                        "period_end": o["period_end"], "fiscal_year": o["fiscal_year"],
                        "fiscal_period": o["fiscal_period"], "rcept_no": o["rcept_no"],
                        "receipt_date": o["receipt_date"], "currency": o["currency"], "unit": o["unit"],
                        "confidence": d["confidence"], "mapping_version": o["mapping_version"]}
    return out


def choose_basis(fetch_result: Dict[str, Dict]) -> Dict:
    """CFS when available and non-empty, otherwise OFS (labelled).  Never combined."""
    cfs, ofs = fetch_result.get("CFS") or {}, fetch_result.get("OFS") or {}
    if cfs.get("status") == "REAL" and cfs.get("list"):
        return {"fs_div": "CFS", "basis": "CONSOLIDATED", "rows": cfs["list"]}
    if ofs.get("status") == "REAL" and ofs.get("list"):
        return {"fs_div": "OFS", "basis": "SEPARATE", "rows": ofs["list"],
                "note": "consolidated statements unavailable; separate basis used and labelled"}
    return {"fs_div": None, "basis": None, "rows": [], "status": "UNAVAILABLE"}
