"""Corporate events for QSF.  US and KR semantics are separate on purpose: 8-K item numbers and Form 4 codes in the US,
report titles from OpenDART in Korea.  An item only counts as negative or positive when its meaning is unambiguous;
earnings releases and most agreements are neutral because the filing itself does not say good or bad."""
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

SEVERE_8K = {"1.03": "파산·회생 절차 (8-K 1.03)", "3.01": "상장 유지 기준 미달·상장폐지 통지 (8-K 3.01)"}
NEGATIVE_8K = {"1.02": "중요 계약 종료 (8-K 1.02)", "2.04": "채무 가속 사유 발생 (8-K 2.04)", "2.05": "구조조정 비용 (8-K 2.05)",
               "2.06": "중요 자산 손상 (8-K 2.06)", "4.02": "과거 재무제표 신뢰 불가 (8-K 4.02)"}
GOV_8K = {"4.01": "감사인 변경 (8-K 4.01)", "4.02": "재무제표 신뢰 불가 (8-K 4.02)"}
GOV_FORMS = {"NT 10-K": "연차보고서 지연 (NT 10-K)", "NT 10-Q": "분기보고서 지연 (NT 10-Q)", "10-K/A": "연차보고서 정정 (10-K/A)"}
KEPT_FORMS = {"4", "8-K", "8-K/A", "NT 10-K", "NT 10-Q", "10-K/A"}
WINDOW = 90
WINDOW_LONG = 365
SEVERE_WINDOW = 180

KR_SEVERE = (("회생절차", "회생절차"), ("파산", "파산"), ("상장폐지", "상장폐지 관련"), ("관리종목", "관리종목"), ("횡령", "횡령·배임"), ("배임", "횡령·배임"), ("감사의견거절", "감사의견 거절"))
KR_SUBSIDIARY = "자회사의주요경영사항"
KR_BENIGN_DELISTING = "이전상장"      # moving from KOSDAQ to KOSPI is filed as a delisting decision
KR_DELISTING_AGENDA = "의안상정"      # a board agenda item, not a decision by the exchange
KR_NEGATIVE = (("유상증자결정", "유상증자"), ("전환사채권발행결정", "전환사채 발행"), ("신주인수권부사채권발행결정", "신주인수권부사채 발행"), ("교환사채권발행결정", "교환사채 발행"),
               ("감자결정", "감자"), ("소송등의제기", "소송 제기"), ("영업정지", "영업 정지"))
KR_POSITIVE = (("자기주식취득결정", "자사주 취득"), ("주식소각결정", "주식 소각"), ("자기주식소각", "자사주 소각"), ("현금ㆍ현물배당결정", "현금·현물 배당"), ("현금배당결정", "현금 배당"))
KR_GOV = (("불성실공시", "불성실공시 법인 지정"), ("사업보고서제출기한연장", "사업보고서 제출 지연"))


def recent_filings(subm: Dict[str, Any]) -> List[Dict[str, str]]:
    r = ((subm.get("filings") or {}).get("recent")) or {}
    forms = r.get("form") or []
    out = []
    for i, form in enumerate(forms):
        def col(k):
            v = r.get(k) or []
            return v[i] if i < len(v) else None
        out.append({"form": form, "date": col("filingDate"), "items": col("items") or "", "accession": col("accessionNumber"), "doc": col("primaryDocument")})
    return out


def listing_item_targets(filings: List[Dict[str, str]], as_of: str) -> List[Dict[str, str]]:
    """8-Ks with Item 3.01 that the severe rule would count, so their text can be read."""
    start = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=SEVERE_WINDOW)).strftime("%Y-%m-%d")
    return [f for f in filings if f["form"] in ("8-K", "8-K/A") and "3.01" in [x.strip() for x in f["items"].split(",")] and f["date"] and start <= f["date"] <= as_of and f.get("doc")]


def is_listing_transfer(document: str) -> bool:
    """Item 3.01 covers both a delisting notice and a voluntary move between exchanges, and its heading names both.
    Only the body after the heading decides, and only a voluntary transfer of the listing counts as harmless."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", document)))
    found = [m.end() for m in re.finditer(r"Transfer of Listing\.?", text, re.I)]
    if not found:
        return False
    body = text[found[-1]:found[-1] + 1500].lower()
    return "voluntar" in body and bool(re.search(r"transfer(ring)?\b.{0,160}\blisting|transfer(ring)?\b.{0,160}\b(nasdaq|nyse|new york stock exchange)", body))


def classify_us(filings: List[Dict[str, str]], as_of: str, transfers: Iterable[str] = ()) -> Dict[str, Any]:
    """``transfers``: accession numbers whose Item 3.01 text was read and is a voluntary move between exchanges."""
    end = datetime.strptime(as_of, "%Y-%m-%d")

    def within(d, days):
        return d and d <= as_of and datetime.strptime(d, "%Y-%m-%d") >= end - timedelta(days=days)
    severe, neg, gov = [], [], []
    for f in filings:
        if f["form"] in GOV_FORMS and within(f["date"], WINDOW_LONG):
            gov.append({"label": GOV_FORMS[f["form"]], "date": f["date"]})
        if f["form"] not in ("8-K", "8-K/A"):
            continue
        items = [x.strip() for x in f["items"].split(",") if x.strip()]
        for it in items:
            if it == "3.01" and f.get("accession") in transfers:
                continue
            if it in SEVERE_8K and within(f["date"], SEVERE_WINDOW):
                severe.append({"label": SEVERE_8K[it], "date": f["date"]})
            if it in NEGATIVE_8K and within(f["date"], WINDOW):
                neg.append({"label": NEGATIVE_8K[it], "date": f["date"]})
            if it in GOV_8K and within(f["date"], WINDOW_LONG):
                gov.append({"label": GOV_8K[it], "date": f["date"]})
    return {"status": "REAL", "severe": severe, "negative": neg, "positive": [], "governance": gov, "window_days": WINDOW,
            "window_long_days": WINDOW_LONG, "as_of": as_of, "source": "SEC EDGAR submissions (8-K 항목 번호, NT 지연 공시)"}


def parse_form4(xml_text: str) -> Dict[str, float]:
    """Open-market activity only.  Code P = purchase, S = sale.  Awards (A), option exercises (M), tax withholding (F),
    gifts (G) and all derivative-table rows are compensation or mechanics, so they are excluded, not netted."""
    root = ET.fromstring(xml_text)
    buy, sell, other = 0.0, 0.0, 0
    for tx in root.iter("nonDerivativeTransaction"):
        code = (tx.findtext("transactionCoding/transactionCode") or "").strip()
        try:
            shares = float(tx.findtext("transactionAmounts/transactionShares/value") or 0)
            price = float(tx.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        if code == "P":
            buy += shares * price
        elif code == "S":
            sell += shares * price
        else:
            other += 1
    return {"buy": buy, "sell": sell, "excluded": other}


def form4_targets(filings: List[Dict[str, str]], as_of: str, limit: int = 8) -> List[Dict[str, str]]:
    start = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=WINDOW)).strftime("%Y-%m-%d")
    out = [f for f in filings if f["form"] == "4" and f["date"] and start <= f["date"] <= as_of and f.get("doc")]
    return out[:limit]


def raw_form4_doc(doc: str) -> str:
    """EDGAR's primaryDocument points at an XSL-rendered view (``xslF345X05/x.xml``); the data file is ``x.xml``."""
    return doc.split("/")[-1]


def insider_summary(parsed: List[Optional[Dict[str, float]]]) -> Dict[str, Any]:
    good = [p for p in parsed if p]
    if parsed and not good:
        return {"status": "UNAVAILABLE"}
    return {"status": "REAL", "open_market_buy": sum(p["buy"] for p in good), "open_market_sell": sum(p["sell"] for p in good),
            "excluded_transactions": sum(p["excluded"] for p in good), "filings": len(good), "window_days": WINDOW, "source": "SEC Form 4 (거래 코드 P·S만 집계)"}


KR_LIST_PAGES = 60      # 100 filings a page.  Measured 2026-11-17 on the 300 scanned stocks: the longest year is 2,918 filings (a
                        # securities firm's ELS issues), five lists pass 1,000.  Twice the longest is room, not a target


def kr_filings(get, corp: str, bgn: str, end: str, max_pages: int = KR_LIST_PAGES) -> Dict[str, Any]:
    """Every page of a company's OpenDART filing list between two dates (YYYYMMDD): {"rows", "complete", "pages", "total_pages"}.
    ``get`` is the client's request (endpoint, **params).  Until QSF-1.4.1 only the first page was read and taken for the whole
    year: 105 of 420 stored lists were cut at 100 rows, the shortest covering 16 days.  A provider status other than "no data"
    is an error, never an empty list: a request-limit answer used to read as "no filings"."""
    rows: List[Dict[str, str]] = []
    page = total = 1
    while page <= min(total, max_pages):
        got = get("list.json", corp_code=corp, bgn_de=bgn, end_de=end, page_no=page, page_count=100).json()
        status = got.get("status")
        if status == "013":             # no filing in the range
            break
        if status not in (None, "000"):
            raise RuntimeError(f"DART_STATUS_{status}")
        rows += got.get("list") or []
        total = int(got.get("total_page") or 1)
        page += 1
    return {"rows": rows, "complete": total <= max_pages, "pages": min(total, max_pages), "total_pages": total}


def classify_kr_list(listing: Optional[Dict[str, Any]], as_of: str) -> Dict[str, Any]:
    """``classify_kr`` on a whole list.  A failed request or a list that does not reach back the long window is UNAVAILABLE:
    filings not seen are not filings that did not happen."""
    if listing is None:
        return {"status": "UNAVAILABLE", "reason": "DART 공시 조회 실패"}
    if not listing.get("complete"):
        return {"status": "UNAVAILABLE", "reason": f"DART 공시 목록이 {WINDOW_LONG}일을 덮지 못합니다(공시 {listing.get('total_pages')}쪽 중 {listing.get('pages')}쪽만 읽음)."}
    return classify_kr(listing["rows"], as_of)


def classify_kr(reports: List[Dict[str, str]], as_of: str) -> Dict[str, Any]:
    """``reports``: OpenDART list.json rows (report_nm, rcept_dt 'YYYYMMDD').  Insider direction is not in the title,
    so insider status stays UNAVAILABLE rather than guessing from the filing's existence."""
    severe, neg, pos, gov = [], [], [], []
    cut = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=WINDOW)).strftime("%Y%m%d")
    severe_cut = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=SEVERE_WINDOW)).strftime("%Y%m%d")
    today = as_of.replace("-", "")
    for r in reports:
        name, d = (r.get("report_nm") or "").replace(" ", ""), r.get("rcept_dt") or ""
        if not d or d > today:
            continue
        iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        for key, label in KR_SEVERE:
            if key not in name:
                continue
            if key == "상장폐지" and KR_BENIGN_DELISTING in name:
                break
            if key == "상장폐지" and KR_DELISTING_AGENDA in name:
                gov.append({"label": "상장폐지 안건 상정", "date": iso})
            elif KR_SUBSIDIARY in name:
                if d >= cut:
                    neg.append({"label": f"자회사 {label}", "date": iso})
            elif d >= severe_cut:
                severe.append({"label": label, "date": iso})
            break
        for key, label in KR_GOV:
            if key in name:
                gov.append({"label": label, "date": iso})
        if d >= cut:
            for key, label in KR_NEGATIVE:
                if key in name:
                    neg.append({"label": label, "date": iso})
            for key, label in KR_POSITIVE:
                if key in name:
                    pos.append({"label": label, "date": iso})
    return {"status": "REAL", "severe": severe, "negative": neg, "positive": pos, "governance": gov, "window_days": WINDOW, "window_long_days": WINDOW_LONG,
            "as_of": as_of, "source": "OpenDART 공시 목록 (보고서명 분류)", "insider": {"status": "UNAVAILABLE"}}
