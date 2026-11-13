"""KR Automated Market Scan and Direct Ticker Evaluation (KR-EXP-0.1), with durable run artifacts.

Stages: security master -> universe market data -> liquid-300 -> history -> data-quality gate (before
normalisation) -> factors -> winsorised z -> score -> rank -> portfolio -> artifacts.
"""
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from markets.kr import (KR_ACCOUNT_MAPPING_VERSION, KR_DATA_SPEC_VERSION, KR_MODEL_STATUS, KR_MODEL_VERSION,
                        acquisition, model, security_master, universe)
from markets.kr import calendar as krcal
from markets.kr.market_data import YahooKRProvider, select_provider, series_checks
from markets.storage import data_dir, runs_dir, tracking_dir
from pipeline.run_recorder import RunRecorder, to_jsonable

KR_STAGES = ("RUN_STARTED", "SECURITY_MASTER_COMPLETED", "UNIVERSE_MARKET_DATA_COMPLETED", "UNIVERSE_COMPLETED",
             "HISTORY_COMPLETED", "DATA_QUALITY_GATE_COMPLETED", "FACTORS_COMPLETED", "RANKING_COMPLETED",
             "PORTFOLIO_COMPLETED", "RUN_COMPLETED")
HISTORY_CALENDAR_DAYS = 300
UNIVERSE_CALENDAR_DAYS = 70
VERSIONS = {"market": "KR", "market_config_version": "KR-0.1", "data_spec_version": KR_DATA_SPEC_VERSION,
            "account_mapping_version": KR_ACCOUNT_MAPPING_VERSION, "model_version": KR_MODEL_VERSION,
            "model_status": KR_MODEL_STATUS, "currency": "KRW"}


class KRContext:
    """Injectable providers (tests pass fakes; production uses KIND + Yahoo)."""

    def __init__(self, fetch_kind=security_master.fetch_kind, provider_factory=YahooKRProvider, now=None,
                 base_dir=None):
        self.fetch_kind, self.provider_factory = fetch_kind, provider_factory
        self.now = now or datetime.now(timezone.utc)
        self.data_dir = data_dir("KR", base_dir)
        self.runs_dir = runs_dir("KR", base_dir)
        self.tracking_dir = tracking_dir("KR", base_dir)


CALENDAR_ANCHOR = "005930.KS"       # Samsung Electronics: trades on every KRX session


def _prepare(ctx: KRContext, rec: RunRecorder, size: int, limit: Optional[int]) -> Dict:
    m = security_master.load_master(ctx.data_dir, fetch=ctx.fetch_kind, now=ctx.now)
    master = m["master"]
    rec.checkpoint("SECURITY_MASTER_COMPLETED", rows=len(master), eligible=int(master["eligible"].sum()),
                   cache_hit=m["meta"].get("cache_hit"))
    prov = ctx.provider_factory()
    idx = acquisition.index_bars(prov, *acquisition.window(ctx.now, HISTORY_CALENDAR_DAYS), ctx.now)
    if idx["KOSPI"].empty:
        raise RuntimeError("KOSPI index bars unavailable: cannot establish the KRX session calendar")
    sessions = pd.DatetimeIndex(idx["KOSPI"].index)
    try:        # Yahoo's index series can end a session behind the stocks in the morning (2026-11-13: the scan scored the day before
        #         the last one), so a large constituent also marks the calendar, as the score scan does.  Without it: the index alone.
        anchor = prov.fetch_index(CALENDAR_ANCHOR, *acquisition.window(ctx.now, HISTORY_CALENDAR_DAYS))
        if not anchor.empty:
            sessions = sessions.union(pd.DatetimeIndex(krcal.drop_incomplete(anchor.dropna(subset=["Close"]), ctx.now).index))
    except Exception:
        pass
    latest = pd.Timestamp(sessions.max()).normalize()
    elig = master[master["eligible"].astype(bool)]
    if limit:
        elig = elig.head(limit)
    s, e = acquisition.window(ctx.now, UNIVERSE_CALENDAR_DAYS)
    ub = acquisition.bars(prov, elig, s, e, ctx.now, ctx.data_dir / "cache", "universe", fresh_at=latest)    # a file stored before the day was out is fetched again
    rec.checkpoint("UNIVERSE_MARKET_DATA_COMPLETED", requested=len(elig), rows=len(ub["bars"]),
                   cache_hit=ub["cache_hit"], provider=select_provider())
    uni = universe.build(master[master["canonical_ticker"].isin(elig["canonical_ticker"])], ub["bars"],
                         sessions[sessions >= pd.Timestamp(s)], latest, size=size)
    snap = ctx.data_dir / "universe"
    snap.mkdir(parents=True, exist_ok=True)
    rec.checkpoint("UNIVERSE_COMPLETED", **{k: v for k, v in uni["summary"].items() if k != "exclusions"})
    members = master.set_index("canonical_ticker").loc[uni["members"]["ticker"]].reset_index()
    hs, he = acquisition.window(ctx.now, HISTORY_CALENDAR_DAYS)
    hb = acquisition.bars(ctx.provider_factory(), members, hs, he, ctx.now, ctx.data_dir / "cache", "history", fresh_at=latest)
    rec.checkpoint("HISTORY_COMPLETED", requested=len(members), rows=len(hb["bars"]), cache_hit=hb["cache_hit"])
    return {"master": master, "master_meta": m["meta"], "idx": idx, "sessions": sessions, "latest": latest,
            "universe": uni, "members": members, "history": hb["bars"], "windows": {"universe": [s, e],
                                                                                   "history": [hs, he]}}


def _cross_section(prep: Dict) -> Dict:
    """Gate BEFORE normalisation: only members with REAL, fresh, sufficient history are standardised."""
    hist, sessions, latest = prep["history"], prep["sessions"], prep["latest"]
    by = {t: g.sort_values("date") for t, g in hist.groupby("ticker")} if not hist.empty else {}
    adj = acquisition.wide_adjusted(hist).reindex(sessions[sessions >= hist["date"].min()]) if not hist.empty \
        else pd.DataFrame()
    raw = model.raw_factors(adj, list(model.FACTOR_CANDIDATES)) if not adj.empty else pd.DataFrame()
    flow = {}
    gated = []
    for r in prep["members"].itertuples():
        t = r.canonical_ticker
        g = by.get(t)
        chk = series_checks(g, sessions, latest) if g is not None else {"status": "UNAVAILABLE", "flags": ["NO_BARS"]}
        rec = {"security_key": r.security_key, "ticker": t, "company_name": r.company_name, "market": r.market,
               "industry": r.industry, "industry_class": r.industry_class, "data_checks": chk}
        reasons = []
        if chk.get("status") != "REAL":
            reasons.append(f"DATA_{chk.get('status')}")
        if t not in raw.index or raw.loc[t, model.ACTIVE_FACTORS].isna().any():
            reasons.append("INSUFFICIENT_HISTORY_FOR_REQUIRED_FACTORS")
        rec["raw_factors"] = {f: (None if t not in raw.index or pd.isna(raw.loc[t, f]) else float(raw.loc[t, f]))
                              for f in model.FACTOR_CANDIDATES}
        rec["close"] = float(g[g["quality_status"] == "REAL"]["close"].iloc[-1]) if g is not None and \
            (g["quality_status"] == "REAL").any() else None
        if reasons:
            rec.update(final_status="QUARANTINED", reasons=reasons)
        else:
            gated.append(t)
            rec["final_status"] = "SCORED"
        flow[t] = rec
    raw_g = raw.loc[gated, model.ACTIVE_FACTORS] if gated else pd.DataFrame(columns=model.ACTIVE_FACTORS)
    z = model.standardize(raw_g)
    sc = model.score(z)
    keys = pd.Series({t: flow[t]["security_key"] for t in gated})
    ranked = model.rank(sc, keys)
    for t in gated:
        flow[t]["z"] = {f: float(z.loc[t, f]) for f in model.ACTIVE_FACTORS}
        flow[t]["score"] = float(sc[t]) if pd.notna(sc[t]) else None
        flow[t]["rank"] = int(ranked.loc[t, "rank"]) if t in ranked.index else None
        flow[t]["contributions"] = {f: float(z.loc[t, f] * model.WEIGHTS[f]) for f in model.ACTIVE_FACTORS}
    return {"flow": flow, "raw": raw, "raw_gated": raw_g, "z": z, "ranked": ranked, "gated": gated}


def _render(v: Dict) -> str:
    L = [f"# KR Automated Market Scan — {v['run_id']}", "",
         f"**Market:** South Korea (KOSPI + KOSDAQ) · **Model:** {v['model_version']} "
         f"(**{v['model_status']}** — not validated; paper observation only) · **Data spec:** {v['data_spec_version']}",
         f"**Status:** {v['recommendation_status']} · **Currency:** KRW · **Executed:** {v['executed_at']}",
         f"**Market data:** {v['provider']['provider']} ({v['provider']['basis']}; {v['provider']['status']})", "",
         "## Universe (dynamic liquid-300)", "",
         "| Item | Value |", "|---|---|"]
    for k, val in v["universe"].items():
        L.append(f"| {k} | {val} |")
    L += ["", "## TOP-10 (equal weight, ≤3 per KRX industry)", "",
          "| # | Ticker | Company | Market | Industry | Score | Close (KRW) | Shares | Allocated (KRW) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for p in v["recommendations"]:
        L.append(f"| {p['rank']} | {p['ticker']} | {p['company_name']} | {p['market']} | {p['industry']} | "
                 f"{p['score']:.3f} | {p['reference_close_krw']:,.0f} | {p['shares']} | {p['allocated_krw']:,.0f} |")
    if v.get("unfunded_positions"):
        L += ["", f"**Capital warning:** {', '.join(v['unfunded_positions'])} cost more per share than the 10% "
              "slice of the stated capital, so 0 shares are allocated (KRX has no fractional shares). The signal "
              "is still recorded; the paper portfolio holds cash for that slice."]
    L += ["", f"Quarantined before normalisation: {v['quarantine_counts']}", "",
          "Scores are KR-model scores; they are not comparable with US P6-11B alpha. EXPERIMENTAL output for "
          "personal research — not investment advice, no orders are placed."]
    return "\n".join(L) + "\n"


def run_kr_scan(capital_krw: float, size: int = universe.DEFAULT_SIZE, limit: Optional[int] = None,
                ctx: Optional[KRContext] = None) -> Dict:
    ctx = ctx or KRContext()
    rec = RunRecorder("kr_market_scan", {"capital_krw": capital_krw, "size": size, "limit": limit},
                      runs_dir=str(ctx.runs_dir), market="KR", stages=KR_STAGES, manifest_extra=VERSIONS)
    try:
        prep = _prepare(ctx, rec, size, limit)
        prep["universe"]["table"].to_csv(rec.dir / "universe_snapshot.csv.gz", index=False, compression="gzip")
        cs = _cross_section(prep)
        rec.checkpoint("DATA_QUALITY_GATE_COMPLETED", scored=len(cs["gated"]),
                       quarantined=len(cs["flow"]) - len(cs["gated"]))
        rec.checkpoint("FACTORS_COMPLETED", factors=model.ACTIVE_FACTORS)
        rec.checkpoint("RANKING_COMPLETED", ranked=len(cs["ranked"]))
        info = prep["members"].set_index("canonical_ticker")
        closes = pd.Series({t: cs["flow"][t]["close"] for t in cs["gated"]})
        port = model.portfolio(cs["ranked"], info, capital_krw, closes)
        rec.checkpoint("PORTFOLIO_COMPLETED", positions=len(port["positions"]))
        recs = [{**p, "company_name": info.loc[p["ticker"], "company_name"], "market": info.loc[p["ticker"], "market"],
                 "industry": info.loc[p["ticker"], "industry"], "security_key": info.loc[p["ticker"], "security_key"],
                 "industry_class": info.loc[p["ticker"], "industry_class"],
                 "z": cs["flow"][p["ticker"]]["z"], "raw_factors": cs["flow"][p["ticker"]]["raw_factors"]}
                for p in port["positions"]]
        full = size == universe.DEFAULT_SIZE and not limit
        status = "REAL RECOMMENDATION" if port["complete"] and full and len(prep["universe"]["members"]) >= size \
            else ("PARTIAL RECOMMENDATION" if port["positions"] else "NO VALID RECOMMENDATION")
        qc = {}
        for f in cs["flow"].values():
            for r in f.get("reasons", []):
                qc[r] = qc.get(r, 0) + 1
        v = {**VERSIONS, "run_id": rec.run_id, "mode": "kr_market_scan", "executed_at": rec.started_at.isoformat(),
             "recommendation_status": status, "validation_scope": "full" if full else "bounded",
             "capital_krw": capital_krw, "provider": select_provider(), "universe": prep["universe"]["summary"],
             "latest_session": str(prep["latest"].date()), "windows": prep["windows"],
             "master": {k: prep["master_meta"].get(k) for k in ("retrieved_at", "rows", "eligible", "source_sha256",
                                                                 "cache_hit")},
             "factors": {"active": model.ACTIVE_FACTORS, "weights": model.WEIGHTS, "winsor": model.WINSOR},
             "recommendations": recs, "industry_exposure": port["industry_exposure"],
             "industry_cap_skips": port["industry_cap_skips"], "cash_krw": port["cash_krw"],
             "unfunded_positions": port["unfunded_positions"],
             "quarantine_counts": qc, "scored": len(cs["gated"])}
        rec.write("candidate_flow.json", to_jsonable({"candidates": cs["flow"]}))
        rec.write("validation_result.json", to_jsonable(v))
        rec.write_text("report.md", _render(v))
        rec.complete(recommendation_status=status)
        from markets.kr import tracking as krtrack
        v["tracking"] = krtrack.record_run(rec.dir, ctx.tracking_dir)
        return v
    except Exception as exc:
        rec.fail(exc)
        raise


def run_kr_evaluate(codes: List[str], ctx: Optional[KRContext] = None) -> Dict:
    """Score requested codes against the current liquid-300 reference distribution (the evaluated
    securities never influence that distribution).  Diagnostic only; not recorded for tracking."""
    ctx = ctx or KRContext()
    rec = RunRecorder("kr_direct_evaluation", {"codes": codes}, runs_dir=str(ctx.runs_dir), market="KR",
                      stages=KR_STAGES, manifest_extra=VERSIONS)
    try:
        prep = _prepare(ctx, rec, universe.DEFAULT_SIZE, None)
        cs = _cross_section(prep)
        rec.checkpoint("DATA_QUALITY_GATE_COMPLETED", scored=len(cs["gated"]))
        master = prep["master"].set_index("canonical_ticker")
        out = []
        extra = [c for c in codes if c in master.index and c not in cs["flow"]]
        extra_hist = pd.DataFrame()
        if extra:
            hs, he = prep["windows"]["history"]
            extra_hist = acquisition.bars(ctx.provider_factory(), master.loc[extra].reset_index(), hs, he, ctx.now,
                                          ctx.data_dir / "cache", "evaluate")["bars"]
        for c in codes:
            item = {"input": c}
            if c not in master.index:
                item.update(verdict="NOT_FOUND", reason="NOT_IN_KRX_KIND_LISTED_COMPANY_LIST")
                out.append(item)
                continue
            row = master.loc[c]
            item.update(security_key=row["security_key"], company_name=row["company_name"], market=row["market"],
                        industry=row["industry"], industry_class=row["industry_class"],
                        eligible=bool(row["eligible"]), exclusion_reason=row["exclusion_reason"])
            ut = prep["universe"]["table"].set_index("ticker")
            if c in ut.index:
                item.update(universe_status=ut.loc[c, "status"], liquidity_rank=ut.loc[c, "liquidity_rank"],
                            adtv20_krw=ut.loc[c, "adtv20"], universe_reason=ut.loc[c, "reason"])
            if c in cs["flow"]:
                f = cs["flow"][c]
                item.update(verdict="IN_UNIVERSE_SCORED" if f["final_status"] == "SCORED" else "IN_UNIVERSE_QUARANTINED",
                            score=f.get("score"), rank=f.get("rank"), ranked_of=len(cs["ranked"]), z=f.get("z"),
                            reasons=f.get("reasons"))
            elif not extra_hist.empty and c in set(extra_hist["ticker"]):
                g = extra_hist[extra_hist["ticker"] == c]
                adj = acquisition.wide_adjusted(g).reindex(prep["sessions"][prep["sessions"] >= g["date"].min()])
                rawp = model.raw_factors(adj, model.ACTIVE_FACTORS)
                if rawp.loc[c].isna().any():
                    item.update(verdict="OUTSIDE_UNIVERSE_INSUFFICIENT_HISTORY")
                else:
                    zp = model.standardize_against(rawp, cs["raw_gated"])
                    s = float(model.score(zp).loc[c])
                    pct = float((cs["ranked"]["score"] < s).mean())
                    item.update(verdict="OUTSIDE_UNIVERSE_SCORED_AGAINST_REFERENCE", score=s,
                                percentile_vs_universe=pct, z={k: float(v) for k, v in zp.loc[c].items()})
            else:
                item.update(verdict="OUTSIDE_UNIVERSE_NO_MARKET_DATA")
            out.append({k: (None if isinstance(v, float) and v != v else v) for k, v in item.items()})
        v = {**VERSIONS, "run_id": rec.run_id, "mode": "kr_direct_evaluation", "executed_at": rec.started_at.isoformat(),
             "results": out, "latest_session": str(prep["latest"].date())}
        rec.write("validation_result.json", to_jsonable(v))
        rec.complete(evaluated=len(codes))
        return v
    except Exception as exc:
        rec.fail(exc)
        raise
