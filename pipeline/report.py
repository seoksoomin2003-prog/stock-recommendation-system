"""Human-readable run reports (console / Markdown / self-contained HTML).

Unavailable values are printed as "n/a" and never as numbers; the three
top-level outcomes are always visually distinct:
REAL RECOMMENDATION | DATA-INCOMPLETE / NO VALID RECOMMENDATION | LIVE DATA UNAVAILABLE
"""
import html
from typing import Any, Dict, List

DISCLAIMER = ("Quantitative screening output for personal research. Not investment advice; "
              "no orders are placed. Verify prices before acting.")
OPERATIONAL_MEANING = ("REAL RECOMMENDATION = every data and decision gate passed. It does NOT mean the stocks "
                       "will rise, that the ranking predicts returns, or that the strategy is profitable "
                       "(predictive power is unproven; see `python app.py track`).")


def _context_lines(v: Dict[str, Any]) -> List[str]:
    out = [f"Capital: {fmt(v.get('capital'), 'money')} {v.get('currency') or 'USD'} (source: {v.get('capital_source') or 'n/a'})",
           f"SEC EDGAR: {'used' if v.get('sec_user_agent_status') == 'CONFIGURED' else 'NOT queried (SEC_USER_AGENT ' + str(v.get('sec_user_agent_status')) + '); ROE/margin from Yahoo only'}"]
    out += [f"Sector note: {w}" for w in v.get("sector_cap_warnings") or []]
    return out


def fmt(v: Any, kind: str = "num") -> str:
    if v is None:
        return "n/a"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if kind == "pct":
        return f"{x * 100:.1f}%"
    if kind == "money":
        return f"${x:,.2f}"
    if kind == "int":
        return f"{x:,.0f}"
    if kind == "shares":
        return f"{x:,.4f}"
    return f"{x:.3f}"


def _factor_str(f: Dict[str, Any]) -> str:
    if not f:
        return "n/a"
    return " / ".join(f"{k[:3]} {fmt(v)}" for k, v in f.items())


def console_summary(v: Dict[str, Any]) -> str:
    lines = ["", "=" * 78, f"  RESULT: {v.get('display_status')}", "=" * 78,
             f"  Run ID            : {v.get('run_id')}",
             f"  Mode              : {v.get('mode')}",
             f"  Executed at (UTC) : {v.get('executed_at')}",
             f"  Execution status  : {v.get('execution_status')}  (pipeline: {v.get('pipeline_status')})",
             f"  Recommendation    : {v.get('recommendation_status')}",
             f"  Model             : {v.get('model_version')} / {v.get('strategy_version')}   regime: {v.get('market_regime')}"]
    lines += [f"  {x}" for x in _context_lines(v)]
    if v.get("error"):
        lines.append(f"  ERROR             : {v['error']}")
    funnel = v.get("funnel") or {}
    if funnel.get("requested"):
        lines.append(f"  Funnel            : requested {funnel.get('requested')} -> provenance {funnel.get('passed_provenance_gate')}"
                     f" -> liquidity/required {funnel.get('passed_liquidity_and_required_data')} -> ranked "
                     f"{funnel.get('model_rank_e_ranked')} -> top5 {funnel.get('top5')}")
        if funnel.get("quarantine_reasons"):
            lines.append(f"  Quarantine reasons: {funnel['quarantine_reasons']}")
    recs = v.get("recommendations") or []
    if recs:
        title = "TOP-5 PORTFOLIO" if v.get("recommendation_status") == "REAL RECOMMENDATION" else \
            "PORTFOLIO-ELIGIBLE (fewer than 5 -> NOT a valid recommendation)"
        lines += ["", f"  {title}", "  " + "-" * 74,
                  f"  {'#':<2} {'Ticker':<7} {'RankE':>5} {'Alpha':>7} {'Pctl':>6} {'Close':>10} {'Weight':>7} {'Shares':>11} {'HardStop':>10} Sector"]
        for r in recs:
            lines.append(f"  {r.get('recommendation_rank', ''):<2} {r['ticker']:<7} {str(r.get('model_rank_e_rank') or 'n/a'):>5} {fmt(r.get('alpha')):>7} "
                         f"{fmt(r.get('alpha_percentile'), 'pct'):>6} {fmt(r.get('close'), 'money'):>10} "
                         f"{fmt(r.get('target_weight'), 'pct'):>7} {fmt(r.get('target_shares'), 'shares'):>11} "
                         f"{fmt(r.get('hard_stop'), 'money'):>10} {r.get('sector')}")
    wl = v.get("watchlist") or []
    if wl:
        lines += ["", "  WATCHLIST: " + ", ".join(f"{r['ticker']} ({','.join(r.get('reason_codes', []))})" for r in wl)]
    for e in v.get("ticker_evaluations") or []:
        ind = e.get("individual_evaluation") or {}
        lines += ["", f"  [{e.get('ticker') or e.get('input')}] {e.get('name') or ''}  ->  {e.get('verdict')}",
                  f"      {e.get('verdict_text', '')}"]
        if ind:
            lines.append(f"      alpha {fmt(ind.get('alpha'))} | percentile {fmt(ind.get('alpha_percentile'), 'pct')} "
                         f"of {ind.get('cross_section_size')} | MODEL_RANK_E rank {ind.get('model_rank_e_rank') or 'n/a'} "
                         f"| ADV20 {fmt(ind.get('adv20'), 'int')} | liquidity {ind.get('liquidity') or 'n/a'}")
            lines.append(f"      factors(z): {_factor_str(ind.get('factors'))} | data {ind.get('data_status')}")
            if ind.get("missing_fundamentals"):
                lines.append(f"      missing fundamentals: {', '.join(ind['missing_fundamentals'])} "
                             "(frozen model requires PER, PBR, ROE and profit margin)")
        if e.get("reasons"):
            lines.append(f"      reasons: {', '.join(e['reasons'])}")
        for lim in e.get("limitations", []):
            lines.append(f"      limitation: {lim}")
    if v.get("no_recommendation_reason") and v.get("recommendation_status") != "REAL RECOMMENDATION":
        lines += ["", f"  Why no recommendation: {v['no_recommendation_reason']}"]
    if (v.get("forward_tracking") or {}).get("recorded_rows"):
        lines.append(f"  Forward tracking  : {v['forward_tracking']['recorded_rows']} positions recorded for prospective observation")
    lines += ["", f"  Artifacts: {v.get('artifact_dir')}", f"  {OPERATIONAL_MEANING}", f"  {DISCLAIMER}", "=" * 78]
    return "\n".join(lines)


def render_markdown(v: Dict[str, Any], provider: Dict[str, Any], flow: Dict[str, Dict[str, Any]]) -> str:
    out = [f"# Quant Recommendation Run `{v['run_id']}`", "",
           f"**Result:** {v.get('display_status')}  ", f"**Recommendation status:** {v.get('recommendation_status')}  ",
           f"**Mode:** {v.get('mode')} · **Executed (UTC):** {v.get('executed_at')} · **Regime:** {v.get('market_regime')}  ",
           f"**Model:** {v.get('model_version')} / {v.get('strategy_version')} · **Capital:** {fmt(v.get('capital'), 'money')}", "",
           f"> {DISCLAIMER}", ">", f"> {OPERATIONAL_MEANING}", ""] + [f"- {x}" for x in _context_lines(v)] + [""]
    if v.get("no_recommendation_reason") and v.get("recommendation_status") != "REAL RECOMMENDATION":
        out += [f"**Why no recommendation:** {v['no_recommendation_reason']}", ""]
    recs = v.get("recommendations") or []
    if recs:
        out += ["## Portfolio-eligible positions", "",
                "| # | Ticker | Name | MODEL_RANK_E | Alpha | Pctl | Close | Weight | Shares | Hard stop | Sector | ADV20 / liquidity | Data (last bar) | Factors (z) |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in recs:
            out.append(f"| {r.get('recommendation_rank')} | {r['ticker']} | {r.get('name') or ''} | #{r.get('model_rank_e_rank')} ({fmt(r.get('model_rank_e_score'))}) | {fmt(r.get('alpha'))} | "
                       f"{fmt(r.get('alpha_percentile'), 'pct')} | {fmt(r.get('close'), 'money')} | {fmt(r.get('target_weight'), 'pct')} | "
                       f"{fmt(r.get('target_shares'), 'shares')} | {fmt(r.get('hard_stop'), 'money')} | {r.get('sector')} | "
                       f"{fmt(r.get('adv20'), 'int')} / {r.get('liquidity')} | {r.get('price_status')}/{r.get('volume_status')}/{r.get('fundamental_status')} ({r.get('last_bar')}) | {_factor_str(r.get('factors'))} |")
        out += ["", "Entry: 40% at entry #1, 60% when close > EMA20. Thesis invalidation: close < EMA20. "
                    "Hard stop 2×ATR, dynamic trailing ATR, 30-day re-underwriting (frozen P6-11B rules).", ""]
    if v.get("watchlist"):
        out += ["## Watchlist", ""] + [f"- **{r['ticker']}** — {', '.join(r.get('reason_codes', []))} "
                                       f"(alpha {fmt(r.get('alpha'))}, MODEL_RANK_E #{r.get('model_rank_e_rank')})"
                                       for r in v["watchlist"]] + [""]
    for e in v.get("ticker_evaluations") or []:
        ind = e.get("individual_evaluation") or {}
        out += [f"## Ticker evaluation: {e.get('ticker') or e.get('input')} {('— ' + e['name']) if e.get('name') else ''}", "",
                f"**Verdict:** {e.get('verdict')} — {e.get('verdict_text', '')}", ""]
        if ind:
            out += [f"- Alpha {fmt(ind.get('alpha'))}, percentile {fmt(ind.get('alpha_percentile'), 'pct')} of {ind.get('cross_section_size')}",
                    f"- MODEL_RANK_E rank: {ind.get('model_rank_e_rank') or 'n/a'}",
                    f"- Factors (z): {_factor_str(ind.get('factors'))}",
                    f"- Close {fmt(ind.get('close'), 'money')}, ADV20 {fmt(ind.get('adv20'), 'int')}, liquidity {ind.get('liquidity') or 'n/a'}",
                    f"- Data status: {ind.get('data_status')}, last bar {ind.get('last_bar')}",
                    f"- Fundamentals: {ind.get('fundamentals')}"]
        out += [f"- Reason: {r}" for r in e.get("reasons", [])] + [f"- Limitation: {l}" for l in e.get("limitations", [])] + [""]
    funnel = v.get("funnel") or {}
    out += ["## Candidate funnel", "", "```", str(funnel), "```", "",
            "## Data provenance", "",
            f"- Universe: {provider.get('universe')}",
            f"- CIK map: {(provider.get('cik_map') or {}).get('status')}",
            f"- Market data: {provider.get('market_data', {}).get('price_status_distribution')} (retrieved {provider.get('market_data', {}).get('retrieved_at')})",
            f"- Last bar dates: {provider.get('market_data', {}).get('last_bar_distribution')}",
            f"- Fundamentals: {provider.get('fundamentals', {}).get('status_distribution')}",
            f"- Field sources: {provider.get('fundamentals', {}).get('field_source_distribution')}",
            f"- Provider requests: {provider.get('request_counts')} · events: {provider.get('provider_event_count')}", ""]
    q = [r for r in flow.values() if r.get("final_status") == "QUARANTINED"]
    if q:
        out += ["## Quarantined (first 60)", "", "| Ticker | Reasons | Price | Volume | Fundamentals |", "|---|---|---|---|---|"]
        for r in q[:60]:
            out.append(f"| {r['ticker']} | {', '.join(r.get('reasons', []))} | {r.get('price_status')} | "
                       f"{r.get('volume_status')} | {r.get('fundamental_status')} |")
    return "\n".join(out) + "\n"


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def render_html(v: Dict[str, Any], provider: Dict[str, Any], flow: Dict[str, Dict[str, Any]]) -> str:
    status = v.get("display_status") or ""
    tone = "ok" if status == "REAL RECOMMENDATION" else ("bad" if status == "LIVE DATA UNAVAILABLE" else "warn")
    recs = v.get("recommendations") or []
    rows = "".join(
        f"<tr><td>{_e(r.get('recommendation_rank'))}</td><td><b>{_e(r['ticker'])}</b><br><small>{_e(r.get('name'))}</small></td>"
        f"<td>#{_e(r.get('model_rank_e_rank'))}<br><small>ADV20 {fmt(r.get('adv20'), 'int')} · {_e(r.get('liquidity'))}<br>"
        f"{_e(r.get('price_status'))}/{_e(r.get('fundamental_status'))} · {_e(r.get('last_bar'))}</small></td>"
        f"<td>{fmt(r.get('alpha'))}</td><td>{fmt(r.get('alpha_percentile'), 'pct')}</td><td>{fmt(r.get('close'), 'money')}</td>"
        f"<td>{fmt(r.get('target_weight'), 'pct')}</td><td>{fmt(r.get('target_shares'), 'shares')}</td>"
        f"<td>{fmt(r.get('hard_stop'), 'money')}</td><td>{_e(r.get('sector'))}</td><td><small>{_e(_factor_str(r.get('factors')))}</small></td></tr>"
        for r in recs)
    rec_block = (f"<h2>{'Top-5 portfolio' if status == 'REAL RECOMMENDATION' else 'Portfolio-eligible (incomplete — not a recommendation)'}</h2>"
                 f"<div class=scroll><table><tr><th>#</th><th>Ticker</th><th>MODEL_RANK_E / data</th><th>Alpha</th><th>Pctl</th><th>Close</th><th>Weight</th>"
                 f"<th>Shares</th><th>Hard stop</th><th>Sector</th><th>Factors (z)</th></tr>{rows}</table></div>") if recs else ""
    evals = ""
    for e in v.get("ticker_evaluations") or []:
        ind = e.get("individual_evaluation") or {}
        items = "".join(f"<li>{_e(x)}</li>" for x in e.get("reasons", []) + e.get("limitations", []))
        evals += (f"<div class=card><h3>{_e(e.get('ticker') or e.get('input'))} <small>{_e(e.get('name'))}</small></h3>"
                  f"<p class=verdict>{_e(e.get('verdict'))} — {_e(e.get('verdict_text'))}</p>"
                  + (f"<p>Alpha {fmt(ind.get('alpha'))} · percentile {fmt(ind.get('alpha_percentile'), 'pct')} of {_e(ind.get('cross_section_size'))}"
                     f" · MODEL_RANK_E rank {_e(ind.get('model_rank_e_rank') or 'n/a')} · ADV20 {fmt(ind.get('adv20'), 'int')}"
                     f" · liquidity {_e(ind.get('liquidity') or 'n/a')}</p><p><small>Factors (z): {_e(_factor_str(ind.get('factors')))}"
                     f"<br>Data: {_e(ind.get('data_status'))} · last bar {_e(ind.get('last_bar'))}</small></p>" if ind else "")
                  + (f"<ul>{items}</ul>" if items else "") + "</div>")
    q = [r for r in flow.values() if r.get("final_status") == "QUARANTINED"]
    qrows = "".join(f"<tr><td>{_e(r['ticker'])}</td><td>{_e(', '.join(r.get('reasons', [])))}</td><td>{_e(r.get('price_status'))}</td>"
                    f"<td>{_e(r.get('volume_status'))}</td><td>{_e(r.get('fundamental_status'))}</td></tr>" for r in q[:200])
    funnel = v.get("funnel") or {}
    md = provider.get("market_data", {})
    fd = provider.get("fundamentals", {})
    why = (f"<p><b>Why no recommendation:</b> {_e(v.get('no_recommendation_reason'))}</p>"
           if v.get("recommendation_status") != "REAL RECOMMENDATION" else "")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Quant Run Report</title><style>
:root{{--bg:#fafaf9;--fg:#1c1917;--muted:#57534e;--line:#e7e5e4;--card:#fff;--ok:#166534;--okbg:#dcfce7;--warn:#92400e;--warnbg:#fef3c7;--bad:#991b1b;--badbg:#fee2e2}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0c0a09;--fg:#e7e5e4;--muted:#a8a29e;--line:#292524;--card:#1c1917;--ok:#86efac;--okbg:#14532d;--warn:#fde68a;--warnbg:#78350f;--bad:#fca5a5;--badbg:#7f1d1d}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0;padding:16px;max-width:1100px;margin:auto}}
.badge{{display:inline-block;padding:6px 12px;border-radius:6px;font-weight:700}}.ok{{background:var(--okbg);color:var(--ok)}}
.warn{{background:var(--warnbg);color:var(--warn)}}.bad{{background:var(--badbg);color:var(--bad)}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border-bottom:1px solid var(--line);padding:6px;text-align:left;vertical-align:top}}
.scroll{{overflow-x:auto}}.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin:10px 0}}
small,.meta{{color:var(--muted)}}.verdict{{font-weight:600}}details{{margin:12px 0}}</style></head><body>
<h1>Quant recommendation run</h1>
<p><span class="badge {tone}">{_e(status)}</span></p>
<p class=meta>Run {_e(v.get('run_id'))} · mode {_e(v.get('mode'))} · executed {_e(v.get('executed_at'))} UTC · regime {_e(v.get('market_regime'))}
· model {_e(v.get('model_version'))}/{_e(v.get('strategy_version'))}</p>
<ul class=meta>{''.join(f"<li>{_e(x)}</li>" for x in _context_lines(v))}</ul>
<p class="badge warn" style="font-weight:500">{_e(OPERATIONAL_MEANING)}</p>
{why}{rec_block}{evals}
<h2>Candidate funnel</h2><p>Requested {_e(funnel.get('requested'))} → provenance gate {_e(funnel.get('passed_provenance_gate'))}
→ required data + liquidity {_e(funnel.get('passed_liquidity_and_required_data'))} → MODEL_RANK_E ranked {_e(funnel.get('model_rank_e_ranked'))}
→ top-5 {_e(funnel.get('top5'))} (watchlist {_e(funnel.get('watchlist'))})</p><p><small>Quarantine reasons: {_e(funnel.get('quarantine_reasons'))}</small></p>
<h2>Data provenance &amp; freshness</h2><ul>
<li>Universe: {_e((provider.get('universe') or {}).get('source'))} · {_e((provider.get('universe') or {}).get('status'))} · retrieved {_e((provider.get('universe') or {}).get('retrieved_at'))}</li>
<li>CIK map: {_e((provider.get('cik_map') or {}).get('status'))}</li>
<li>Market data (yfinance): {_e(md.get('price_status_distribution'))} · retrieved {_e(md.get('retrieved_at'))} · last bars {_e(md.get('last_bar_distribution'))}</li>
<li>Fundamentals: {_e(fd.get('status_distribution'))} · sources {_e(fd.get('field_source_distribution'))}</li>
<li>Provider requests: {_e(provider.get('request_counts'))} · events {_e(provider.get('provider_event_count'))}</li></ul>
<details><summary>Quarantined candidates ({len(q)})</summary><div class=scroll><table><tr><th>Ticker</th><th>Reasons</th><th>Price</th><th>Volume</th><th>Fundamentals</th></tr>{qrows}</table></div></details>
<p class=meta>{_e(DISCLAIMER)}</p></body></html>"""
