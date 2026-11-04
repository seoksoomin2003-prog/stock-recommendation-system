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
        return {"runs": len(kt.runs()), "observations": len(kt.observations()),
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


def _panel(m: str, d: Dict) -> str:
    e = html.escape
    model = d["model"]
    badge = model.get("status", "")
    rows = "".join(f"<tr><td><code>{e(r['run_id'])}</code></td><td>{e(str(r['mode']))}</td><td>{e(str(r['state']))}"
                   f"</td><td>{e(str(r['status']))}</td><td>{e(str(r['scope']))}</td><td>{e(', '.join(map(str, r['picks'])))}"
                   f"</td></tr>" for r in d["runs"]) or "<tr><td colspan=6>No runs yet.</td></tr>"
    t = d["tracking"]
    return (f"<section id='{m}' class='panel'><h2>{m} <span class='badge {e(badge.lower())}'>{e(badge)}</span></h2>"
            f"<p>Config <b>{e(d['config_version'])}</b> · model <b>{e(str(model.get('version')))}</b> · currency "
            f"<b>{e(d['currency'])}</b> · tracking <code>{e(d['tracking_dir'])}</code></p>"
            f"<h3>Paper tracking ({e(d['currency'])} only)</h3><p>{e(json.dumps(t, ensure_ascii=False))}</p>"
            f"<h3>Recent runs</h3><table><tr><th>Run</th><th>Mode</th><th>State</th><th>Status</th><th>Scope</th>"
            f"<th>Picks</th></tr>{rows}</table></section>")


def render(data: Dict) -> str:
    panels = "".join(_panel(m, d) for m, d in data["markets"].items())
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width,initial-scale=1'><title>Quant Platform Dashboard</title><style>"
            ":root{--bg:#fff;--fg:#1b1b1b;--mut:#666;--line:#ddd;--exp:#b35c00;--ok:#1d6b35}"
            "@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#e8e8e8;--mut:#9a9a9a;--line:#333;"
            "--exp:#f0a050;--ok:#6fcf8f}}body{background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,"
            "system-ui,sans-serif;margin:0;padding:16px;max-width:1100px}nav button{font:inherit;padding:6px 14px;"
            "margin-right:6px;border:1px solid var(--line);background:none;color:inherit;border-radius:6px;"
            "cursor:pointer}nav button.on{border-color:var(--fg)}.panel{display:none}.panel.on{display:block}"
            "table{border-collapse:collapse;width:100%;display:block;overflow-x:auto}td,th{border-bottom:1px solid "
            "var(--line);padding:4px 8px;text-align:left;white-space:nowrap}.badge{font-size:12px;padding:2px 8px;"
            "border-radius:10px;border:1px solid}.experimental{color:var(--exp)}.frozen,.approved{color:var(--ok)}"
            "small{color:var(--mut)}</style></head><body><h1>Quant Platform Dashboard</h1>"
            f"<small>Generated {html.escape(data['generated_at'])}. Read-only; research information, not advice. "
            "Markets are never aggregated and currencies are never mixed.</small>"
            "<nav><button data-m='US' class='on'>United States</button><button data-m='KR'>South Korea</button></nav>"
            f"{panels}<script>const b=[...document.querySelectorAll('nav button')];function s(m){{b.forEach(x=>"
            "x.classList.toggle('on',x.dataset.m===m));document.querySelectorAll('.panel').forEach(p=>"
            "p.classList.toggle('on',p.id===m));}b.forEach(x=>x.onclick=()=>s(x.dataset.m));s('US');</script>"
            "</body></html>")


def write(out: Path = None) -> Path:
    out = Path(out) if out else Path("tracking") / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(collect()), encoding="utf-8")
    return out
