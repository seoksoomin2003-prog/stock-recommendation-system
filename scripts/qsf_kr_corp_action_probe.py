"""Two small OpenDART reads, no score change.  Saved in the git-ignored research_data/kr_share_probe.
insider: how many insider filings a Korean test would need to download (filing counts only, no names).
actions: spin-off, merger, share exchange, capital reduction and rights issue decisions of the live names, for the share change check.
Run with: python scripts/qsf_kr_corp_action_probe.py insider|actions.  Resumes from saved files.  The key is never printed."""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, ".")
from utils import runtime_config  # noqa: E402

runtime_config.load_local_env()
from markets.kr.dart import OpenDartClient  # noqa: E402
from terminal.qsf.service import QSF  # noqa: E402

OUT = Path("research_data/kr_share_probe")
ACTIONS = ("cmpDvDecsn", "cmpDvmgDecsn", "cmpMgDecsn", "stkExtrDecsn", "crDecsn", "piicDecsn")
BEGIN, END = "20241001", "20261106"


def call(dart, path, endpoint, **params):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        got = dart._get(endpoint, **params).json()
    except Exception as exc:                     # the type only: a message could carry the request address
        return {"status": "ERR", "message": type(exc).__name__}
    if got.get("status") == "020":
        raise SystemExit("daily limit reached, stopping")
    if got.get("status") in ("000", "013"):
        path.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
    return got


def insider(q, dart):
    from terminal.qsf import research_kr as kr
    px = kr._load(Path("."))
    corp = {str(r["stock_code"]).strip(): str(r["corp_code"]) for _, r in dart.corp_codes().iterrows() if str(r["stock_code"]).strip()}
    names = sorted(s for s in px.symbols if s in corp)
    print("price symbols", len(px.symbols), "with a DART code", len(names))
    random.seed(20261108)
    rows, d = [], OUT / "insider"
    d.mkdir(exist_ok=True)
    for c in random.sample(names, 60):
        a = call(dart, d / f"{c}_2018.json", "list.json", corp_code=corp[c], bgn_de="20180101", end_de=END, pblntf_detail_ty="D002", page_count=1, sort="date", sort_mth="asc")
        b = call(dart, d / f"{c}_all.json", "list.json", corp_code=corp[c], bgn_de="19990101", end_de=END, pblntf_detail_ty="D002", page_count=1, sort="date", sort_mth="asc")
        first = ((b.get("list") or [{}])[0]).get("rcept_dt")
        rows.append({"code": c, "n2018": a.get("total_count", 0) if a.get("status") == "000" else 0, "all": b.get("total_count", 0) if b.get("status") == "000" else 0, "first": first, "status": a.get("status")})
    (d / "summary.json").write_text(json.dumps({"names": len(names), "rows": rows}), encoding="utf-8")
    print("done", len(rows))


def actions(q, dart):
    live = json.load(open("data/qsf/latest_KR.json", encoding="utf-8"))
    codes = sorted({r["ticker"] for r in live["rows"]})
    d = OUT / "actions"
    d.mkdir(exist_ok=True)
    bad = 0
    for k, c in enumerate(codes):
        corp = q._corp_code(c)
        if not corp:
            bad += 1
            continue
        for e in ACTIONS:
            got = call(dart, d / f"{c}_{e}.json", f"{e}.json", corp_code=corp, bgn_de=BEGIN, end_de=END)
            if got.get("status") not in ("000", "013"):
                bad += 1
        if k % 50 == 0:
            print(k, "of", len(codes), flush=True)
    print("done", len(codes), "unread", bad)


if __name__ == "__main__":
    q = QSF(Path("."))
    {"insider": insider, "actions": actions}[sys.argv[1]](q, OpenDartClient())
