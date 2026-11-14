"""Unified static dashboard (P6-24): one HTML page with a US tab and a KR tab.

Read-only.  It never runs a scan and never writes into either market's ledger.  Each market panel shows
its own currency, model version and status; nothing is aggregated across markets.
"""
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from markets.config import market_config
from markets.storage import runs_dir, tracking_dir


def _runs(market: str, limit: int = 15) -> List[Dict]:
    base = runs_dir(market)
    out = []
    if not base.exists():
        return out
    for d in sorted((p for p in base.iterdir() if p.is_dir() and (p / "run_manifest.json").exists()),
                    key=lambda p: p.name, reverse=True):
        man = json.loads((d / "run_manifest.json").read_text(encoding="utf-8"))
        if man.get("market", "US") != market:
            continue
        v = {}
        if (d / "validation_result.json").exists():
            v = json.loads((d / "validation_result.json").read_text(encoding="utf-8"))
        st = json.loads((d / "execution_status.json").read_text(encoding="utf-8")) \
            if (d / "execution_status.json").exists() else {}
        recs = v.get("recommendations") or v.get("top_5") or []
        tick = [r.get("ticker") for r in recs if isinstance(r, dict)][:10]
        out.append({"run_id": d.name, "mode": v.get("mode") or man.get("mode"), "state": st.get("state"),
                    "status": v.get("recommendation_status"), "scope": v.get("validation_scope"),
                    "model": v.get("model_version") or man.get("model_version") or "P6-11B (frozen)",
                    "picks": tick})
        if len(out) >= limit:
            break
    return out


def _us_tracking() -> Dict:
    try:
        from pipeline import prospective_tracking as t
        s = t.status()
        return {"runs": s["runs"], "observations": s["observations"], "states": s.get("outcome_states"),
                "latest_update": (s.get("latest_update") or {}).get("update_id")}
    except Exception as exc:  # dashboard must never fail because a panel is unavailable
        return {"error": type(exc).__name__}


def _kr_tracking() -> Dict:
    try:
        from markets.kr import tracking as kt
        from pipeline.prospective_ledger import read_jsonl
        log = read_jsonl(tracking_dir("KR") / "updates.jsonl")
        return {**kt.counts(),
                "states": log[-1]["states"] if log else None,
                "latest_update": log[-1]["update_id"] if log else None}
    except Exception as exc:
        return {"error": type(exc).__name__}


def collect() -> Dict:
    data = {"generated_at": datetime.now(timezone.utc).isoformat(), "markets": {}}
    for m, tr in (("US", _us_tracking), ("KR", _kr_tracking)):
        c = market_config(m)
        data["markets"][m] = {"config_version": c["config_version"], "currency": c["currency"],
                              "model": dict(c["model"]), "runs": _runs(m), "tracking": tr(),
                              "tracking_dir": str(tracking_dir(m))}
    return data


MARKET_NAME = {"US": "미국", "KR": "한국"}
BADGE_KO = {"FROZEN": "동결(FROZEN)", "EXPERIMENTAL": "실험 단계(EXPERIMENTAL)", "APPROVED": "승인(APPROVED)"}
STATE_KO = {"PENDING_ENTRY": "진입 대기", "PENDING_OUTCOME": "보유 중(결과 대기)", "COMPLETED_OUTCOME": "완료",
            "INCOMPLETE": "데이터 불완전", "VALID_PROSPECTIVE": "유효", "PRE_FIX_EXCLUDED": "수정 전 제외",
            "DATA_INVALID": "데이터 무효"}
STATUS_KO = {"REAL RECOMMENDATION": "정상 추천", "PARTIAL RECOMMENDATION": "부분 추천",
             "NO VALID RECOMMENDATION": "유효 추천 없음", "COMPLETED": "완료", "FAILED": "실패", "RUNNING": "실행 중",
             "full": "전체", "bounded": "제한(검증용)"}
MODE_KO = {"market_scan": "전체 시장 스캔", "direct_evaluation": "종목 직접 평가", "kr_market_scan": "전체 시장 스캔",
           "kr_direct_evaluation": "종목 직접 평가"}


def _ko(table, v):
    return table.get(str(v), "-" if v is None else str(v))


def _states_ko(states) -> str:
    if not states:
        return "업데이트 없음"
    parts = []
    for k, n in states.items():
        label = " / ".join(_ko(STATE_KO, x) for x in str(k).split("/"))
        parts.append(f"{label} {n}건")
    return ", ".join(parts)


def _panel(m: str, d: Dict) -> str:
    e = html.escape
    model = d["model"]
    badge = model.get("status", "")
    rows = "".join(f"<tr><td><code>{e(r['run_id'])}</code></td><td>{e(_ko(MODE_KO, r['mode']))}</td>"
                   f"<td>{e(_ko(STATUS_KO, r['state']))}</td><td>{e(_ko(STATUS_KO, r['status']))}</td>"
                   f"<td>{e(_ko(STATUS_KO, r['scope']))}</td><td>{e(', '.join(map(str, r['picks'])))}</td></tr>"
                   for r in d["runs"]) or "<tr><td colspan=6>아직 실행 기록이 없습니다.</td></tr>"
    t = d["tracking"]
    if "error" in t:
        trk = f"<p>트래킹 정보를 읽을 수 없습니다 ({e(t['error'])}).</p>"
    else:
        trk = ("<table><tr><th>항목</th><th>값</th></tr>"
               f"<tr><td>기록된 실행 수</td><td>{t.get('runs')}</td></tr>"
               f"<tr><td>관측 수</td><td>{t.get('observations')}</td></tr>"
               + (f"<tr><td>집계에서 제외 (같은 거래일을 두 번 스캔)</td><td>실행 {t.get('excluded_runs')}개, "
                  f"관측 {t.get('excluded_observations')}건</td></tr>" if t.get("excluded_runs") else "") +
               f"<tr><td>상태별 건수</td><td>{e(_states_ko(t.get('states')))}</td></tr>"
               f"<tr><td>최신 업데이트</td><td><code>{e(str(t.get('latest_update') or '없음'))}</code></td></tr></table>")
    note = ("<p class='warn'>실험 단계 모델입니다. 검증되지 않았으며 예측력 근거가 없습니다. "
            "페이퍼 관찰 용도로만 사용하세요.</p>" if badge == "EXPERIMENTAL" else "")
    return (f"<section id='{m}' class='panel'><h2>{MARKET_NAME.get(m, m)} "
            f"<span class='badge {e(badge.lower())}'>{e(BADGE_KO.get(badge, badge))}</span></h2>{note}"
            f"<p>설정 버전 <b>{e(d['config_version'])}</b> · 모델 <b>{e(str(model.get('version')))}</b> · 통화 "
            f"<b>{e(d['currency'])}</b> · 트래킹 폴더 <code>{e(d['tracking_dir'])}</code></p>"
            f"<h3>페이퍼 트래킹 ({e(d['currency'])} 전용)</h3>{trk}"
            f"<h3>최근 실행</h3><table><tr><th>실행 ID</th><th>모드</th><th>실행 상태</th><th>추천 상태</th>"
            f"<th>범위</th><th>선정 종목</th></tr>{rows}</table></section>")


def render(data: Dict) -> str:
    panels = "".join(_panel(m, d) for m, d in data["markets"].items())
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width,initial-scale=1'><title>퀀트 플랫폼 대시보드</title><style>"
            ":root{--bg:#fff;--fg:#1b1b1b;--mut:#666;--line:#ddd;--exp:#b35c00;--ok:#1d6b35}"
            "@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#e8e8e8;--mut:#9a9a9a;--line:#333;"
            "--exp:#f0a050;--ok:#6fcf8f}}body{background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,"
            "'Apple SD Gothic Neo',system-ui,sans-serif;margin:0;padding:16px;max-width:1100px}"
            "nav button{font:inherit;padding:6px 14px;"
            "margin-right:6px;border:1px solid var(--line);background:none;color:inherit;border-radius:6px;"
            "cursor:pointer}nav button.on{border-color:var(--fg)}.panel{display:none}.panel.on{display:block}"
            "table{border-collapse:collapse;width:100%;display:block;overflow-x:auto}td,th{border-bottom:1px solid "
            "var(--line);padding:4px 8px;text-align:left;white-space:nowrap}.badge{font-size:12px;padding:2px 8px;"
            "border-radius:10px;border:1px solid}.experimental,.warn{color:var(--exp)}.frozen,.approved{color:var(--ok)}"
            "small{color:var(--mut)}</style></head><body><h1>퀀트 플랫폼 대시보드</h1>"
            f"<small>생성 시각 {html.escape(data['generated_at'])} (UTC). 읽기 전용 화면이며, 연구용 정보일 뿐 투자 "
            "조언이 아닙니다. 주문은 실행되지 않습니다. 두 시장의 수치는 합산하지 않고 통화도 섞지 않습니다.</small>"
            "<nav><button data-m='US' class='on'>미국</button><button data-m='KR'>한국</button></nav>"
            f"{panels}<script>const b=[...document.querySelectorAll('nav button')];function s(m){{b.forEach(x=>"
            "x.classList.toggle('on',x.dataset.m===m));document.querySelectorAll('.panel').forEach(p=>"
            "p.classList.toggle('on',p.id===m));}b.forEach(x=>x.onclick=()=>s(x.dataset.m));s('US');</script>"
            "</body></html>")


def write(out: Path = None) -> Path:
    out = Path(out) if out else Path("tracking") / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(collect()), encoding="utf-8")
    return out
