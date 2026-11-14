"""KR command handlers for app.py (``--market KR``).  KRW capital is never taken from the USD setting."""
import json
import os
import sys
from pathlib import Path

from markets.storage import runs_dir, tracking_dir
from utils import runtime_config


class KRCapitalNotConfigured(Exception):
    pass


def resolve_capital_krw(cli_value=None):
    """--capital (KRW) wins, else $QPP_CAPITAL_KRW.  QPP_CAPITAL (USD) is deliberately NOT used."""
    if cli_value is not None:
        return runtime_config.parse_capital(cli_value), "command line (--capital, KRW)"
    v = os.getenv("QPP_CAPITAL_KRW", "").strip()
    if v:
        return runtime_config.parse_capital(v), "QPP_CAPITAL_KRW (environment / .env)"
    raise KRCapitalNotConfigured(
        "KR capital is not configured. Pass --capital AMOUNT in KRW, e.g. "
        "`python app.py --market KR scan --capital 10000000`, or set QPP_CAPITAL_KRW. "
        "The USD setting QPP_CAPITAL is never reused for Korea.")


def _latest_run(market_dir: Path):
    dirs = sorted((p for p in market_dir.iterdir() if p.is_dir() and (p / "run_manifest.json").exists()),
                  key=lambda p: p.name) if market_dir.exists() else []
    return dirs[-1] if dirs else None


def cmd_scan(args) -> int:
    from markets.kr.pipeline import run_kr_scan
    cap, src = resolve_capital_krw(args.capital)
    print(f"KR scan (EXPERIMENTAL model KR-EXP) capital {cap:,.0f} KRW [{src}]"
          + (f", bounded to {args.limit} members" if args.limit else ""))
    v = run_kr_scan(cap, limit=args.limit)
    print(f"Run {v['run_id']}: {v['recommendation_status']} ({v['validation_scope']}), latest session "
          f"{v['latest_session']}, scored {v['scored']}")
    for p in v["recommendations"]:
        print(f"  {p['rank']:>2}. {p['ticker']} {p['company_name']:<16} {p['market']:<6} "
              f"{p['shares']:>6} sh @ {p['reference_close_krw']:>10,.0f} KRW  score {p['score']:+.3f}")
    print(f"Tracking: {v.get('tracking')}")
    print(f"Report: {runs_dir('KR') / v['run_id'] / 'report.md'}")
    return 0 if v["recommendation_status"] != "NO VALID RECOMMENDATION" else 1


def cmd_evaluate(args) -> int:
    from markets.kr.pipeline import run_kr_evaluate
    res = run_kr_evaluate([t.strip().upper() for t in args.tickers])
    for it in res["results"]:
        print(json.dumps(it, ensure_ascii=False, default=str))
    return 0


def cmd_status(args) -> int:
    base = runs_dir("KR")
    d = base / args.run_id if getattr(args, "run_id", None) else _latest_run(base)
    if not d or not d.exists():
        print("No KR run recorded yet.")
        return 1
    for n in ("run_manifest.json", "execution_status.json"):
        p = d / n
        if p.exists():
            x = json.loads(p.read_text(encoding="utf-8"))
            print(n, json.dumps({k: x.get(k) for k in ("run_id", "market", "mode", "state", "model_version",
                                                       "model_status") if k in x}, ensure_ascii=False))
    if (d / "report.md").exists():
        print((d / "report.md").read_text(encoding="utf-8")[:4000])
    return 0


def cmd_tracking(args) -> int:
    from markets.kr import tracking as kt
    action = getattr(args, "action", None) or "status"
    if action == "status":
        s = kt.sync_runs()
        obs = kt.observations()
        print(f"KR ledger ({tracking_dir('KR')}): {len(kt.runs())} run(s), {len(obs)} observation(s); "
              f"newly recorded {s['recorded']}")
        return 0
    if action == "update":
        kt.sync_runs()
        r = kt.update(offline_snapshot=None)
        print(json.dumps(r, ensure_ascii=False, default=str))
        kt.write_report()
        return 0
    if action == "report":
        p = kt.write_report()
        print(f"Report: {p} (and latest.html)")
        if getattr(args, "open", False) and sys.platform == "darwin":
            os.system(f"open '{p.with_suffix('.html')}'")
        return 0
    if action == "verify":
        r = kt.verify()
        for c in r["chains"]:
            print(f"  chain {c['file']}: {c['rows']} rows, {'OK' if c['ok'] else 'BROKEN'}")
        for x in r["runs"]:
            print(f"  run {x['run_id']}: artifacts {x['artifacts']}, reconstruction {x.get('reconstruction')}")
        if "latest_replay" in r:
            print(f"  latest update replay: {'MATCH' if r['latest_replay']['match'] else 'MISMATCH'}")
        print("Verify:", "OK" if r["ok"] else "PROBLEMS FOUND")
        return 0 if r["ok"] else 1
    if action == "exclusions":
        # A KR run can be left out of the figures for one reason only: it is a later scan of a session an earlier run already
        # recorded.  ``--add`` appends that event (nothing is deleted); any other run is refused.
        add = getattr(args, "add", None)
        if add:
            r = kt.exclude_run(add, source="user (app.py --market KR tracking exclusions --add)")
            print(json.dumps(r, ensure_ascii=False))
            if not r["excluded"]:
                return 2
        ex, dup = kt.excluded_runs(), kt.duplicate_runs()
        for rid, x in sorted(dup.items()):
            print(f"  {rid}: second scan of session {x['session']} (run {x['kept_run']} counts): "
                  f"{'EXCLUDED from the figures' if rid in ex else 'still counted'}")
        if not dup:
            print("No session was recorded twice; nothing can be excluded.")
        return 0
    print(f"tracking action '{action}' is not available for KR (US-only: replay)")
    return 2


def dispatch(args) -> int:
    try:
        if args.command == "scan":
            return cmd_scan(args)
        if args.command == "evaluate":
            return cmd_evaluate(args)
        if args.command == "status":
            return cmd_status(args)
        if args.command in ("tracking", "track"):
            if args.command == "track":
                cmd_tracking(type(args)(action="update"))
                return cmd_tracking(type(args)(action="report", open=False))
            return cmd_tracking(args)
    except KRCapitalNotConfigured as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"command '{args.command}' has no KR variant")
    return 2
