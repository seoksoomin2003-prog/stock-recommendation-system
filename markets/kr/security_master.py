"""Korean security master from the KRX KIND listed-company list (KR-DATA-0.1 §2).

Source: https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=
{stockMkt|kosdaqMkt} -- a public KRX disclosure-system download (EUC-KR HTML table; no key).  It lists
*listed corporations* with their common-stock issue code; ETFs, ETNs and preferred-share lines are not
companies and do not appear in it (recorded as a coverage property, not inferred).

Every row is kept.  Rows not eligible for the initial operating-company model carry an explicit
``exclusion_reason``; nothing is silently dropped.
"""
import hashlib
import io
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd
import requests

from markets.identity import kr_security

KIND_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType={m}"
KIND_MARKETS = {"KOSPI": "stockMkt", "KOSDAQ": "kosdaqMkt"}
KIND_MARKET_LABEL = {"유가": "KOSPI", "코스닥": "KOSDAQ"}
KOREAN_REGIONS = ("특별시", "광역시", "도", "특별자치시", "특별자치도", "특별시")
USER_AGENT = "Mozilla/5.0 (Macintosh) QuantStockEngine/1.0 (personal research)"

# KSIC-based KIND industries (업종) that identify financial firms.  "기타 금융업" mixes non-financial
# holding companies with card/capital companies, so it is its own class (not silently "bank").
FINANCIAL_CLASSES = {
    "은행 및 저축기관": "BANK",
    "보험업": "INSURANCE", "재 보험업": "INSURANCE", "보험 및 연금관련 서비스업": "INSURANCE",
    "금융 지원 서비스업": "SECURITIES_AND_FINANCIAL_SERVICES",
    "기타 금융업": "HOLDING_OR_OTHER_FINANCIAL",
    "신탁업 및 집합투자업": "TRUST_AND_COLLECTIVE_INVESTMENT",
}

COLUMNS = ["security_key", "canonical_ticker", "company_name", "market", "exchange", "currency",
           "instrument_type", "listing_date", "delisting_date", "listing_status", "industry", "sector",
           "industry_class", "fiscal_month", "region", "shares_outstanding", "market_cap",
           "yahoo_symbol", "dart_corp_code", "eligible", "exclusion_reason", "source", "last_verified_utc"]


def fetch_kind(market: str, session=None, timeout: int = 30) -> bytes:
    url = KIND_URL.format(m=KIND_MARKETS[market])
    http = session or requests
    last = None
    for attempt in range(3):
        try:
            r = http.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if r.status_code == 200 and r.content:
                return r.content
            last = f"HTTP_{r.status_code}"
        except Exception as exc:  # network failure -> no data, never fabricated
            last = type(exc).__name__
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"KIND download failed for {market}: {last}")


def parse_kind(raw: bytes) -> pd.DataFrame:
    text = raw.decode("euc-kr", errors="replace")
    df = pd.read_html(io.StringIO(text), converters={"종목코드": str})[0]
    expected = {"회사명", "시장구분", "종목코드", "업종", "상장일", "결산월", "지역"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"KIND layout changed; missing columns {sorted(missing)}")
    return df


def _classify(row) -> Dict[str, Optional[str]]:
    name, industry, region = str(row["회사명"]), str(row.get("업종") or ""), str(row.get("지역") or "")
    code = str(row["종목코드"]).strip()
    ind_class = FINANCIAL_CLASSES.get(industry, "NON_FINANCIAL")
    if "스팩" in name or "기업인수목적" in name:
        return {"instrument_type": "SPAC", "industry_class": ind_class, "reason": "SPAC_EXCLUDED"}
    if "리츠" in name or "REIT" in name.upper():
        return {"instrument_type": "REIT", "industry_class": "REIT", "reason": "REIT_EXCLUDED_SEPARATE_TREATMENT"}
    if industry == "신탁업 및 집합투자업":
        return {"instrument_type": "FUND_VEHICLE", "industry_class": ind_class,
                "reason": "COLLECTIVE_INVESTMENT_VEHICLE_EXCLUDED"}
    if region and not region.endswith(KOREAN_REGIONS):
        return {"instrument_type": "FOREIGN_ISSUER_COMMON", "industry_class": ind_class,
                "reason": "FOREIGN_ISSUER_EXCLUDED_INITIAL_MODEL"}
    if len(code) != 6:
        return {"instrument_type": "UNKNOWN", "industry_class": ind_class, "reason": "INVALID_ISSUE_CODE"}
    return {"instrument_type": "COMMON_STOCK", "industry_class": ind_class, "reason": None}


def build_master(raw_by_market: Dict[str, bytes], verified_at: Optional[str] = None) -> pd.DataFrame:
    verified_at = verified_at or datetime.now(timezone.utc).isoformat()
    rows = []
    for market, raw in raw_by_market.items():
        df = parse_kind(raw)
        for _, r in df.iterrows():
            label = KIND_MARKET_LABEL.get(str(r["시장구분"]).strip())
            code = str(r["종목코드"]).strip()
            c = _classify(r)
            reason = c["reason"]
            if label != market:
                reason = reason or "MARKET_LABEL_MISMATCH"
            exch = label or market
            sid = kr_security(code, exch) if exch in ("KOSPI", "KOSDAQ") else None
            rows.append({
                "security_key": sid.key if sid else f"KR:{exch}:{code}",
                "canonical_ticker": code, "company_name": str(r["회사명"]).strip(), "market": exch,
                "exchange": exch, "currency": "KRW", "instrument_type": c["instrument_type"],
                "listing_date": str(r.get("상장일") or "") or None, "delisting_date": None,
                "listing_status": "LISTED", "industry": (str(r.get("업종")).strip() if pd.notna(r.get("업종")) else None),
                "sector": None, "industry_class": c["industry_class"],
                "fiscal_month": str(r.get("결산월") or "") or None, "region": str(r.get("지역") or "") or None,
                "shares_outstanding": None, "market_cap": None,
                "yahoo_symbol": sid.identifiers["yahoo"] if sid else None, "dart_corp_code": None,
                "eligible": reason is None, "exclusion_reason": reason,
                "source": "KRX KIND corpList", "last_verified_utc": verified_at})
    out = pd.DataFrame(rows, columns=COLUMNS)
    dup = out.duplicated("security_key", keep="first")
    out.loc[dup, ["eligible", "exclusion_reason"]] = [False, "DUPLICATE_SECURITY_KEY"]
    return out.sort_values(["market", "canonical_ticker"]).reset_index(drop=True)


def load_master(data_dir: Path, fetch: Callable[[str], bytes] = fetch_kind, max_age_hours: float = 20.0,
                now: Optional[datetime] = None) -> Dict:
    """Fetch (or reuse a fresh snapshot of) the master; every fetch is snapshotted with its source hash."""
    now = now or datetime.now(timezone.utc)
    sdir = Path(data_dir) / "security_master"
    sdir.mkdir(parents=True, exist_ok=True)
    meta_path = sdir / "LATEST.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        age = (now - datetime.fromisoformat(meta["retrieved_at"])).total_seconds() / 3600
        if age <= max_age_hours and (sdir / meta["file"]).exists():
            df = pd.read_csv(sdir / meta["file"], dtype={"canonical_ticker": str, "dart_corp_code": str})
            return {"master": df, "meta": {**meta, "cache_hit": True, "status": "CACHED"}}
    raws = {m: fetch(m) for m in KIND_MARKETS}
    df = build_master(raws, verified_at=now.isoformat())
    fname = f"master_{now:%Y%m%dT%H%M%SZ}.csv.gz"
    df.to_csv(sdir / fname, index=False, compression="gzip")
    meta = {"file": fname, "retrieved_at": now.isoformat(), "source": "KRX KIND corpList",
            "source_sha256": {m: hashlib.sha256(raw).hexdigest() for m, raw in raws.items()},
            "rows": int(len(df)), "eligible": int(df["eligible"].sum()),
            "by_market": {k: int(v) for k, v in df["market"].value_counts().items()},
            "exclusions": {k: int(v) for k, v in df["exclusion_reason"].value_counts().items()}}
    tmp = meta_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, meta_path)
    return {"master": df, "meta": {**meta, "cache_hit": False, "status": "REAL"}}
