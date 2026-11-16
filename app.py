#!/usr/bin/env python3
"""Quant Stock Recommendation — command-line application (P6-18).

    python app.py                      interactive menu
    python app.py scan                 Mode A: Automated Market Scan (current S&P 500)
    python app.py scan --limit 25      bounded scan (first 25 constituents) for a quick check
    python app.py evaluate NVDA PLTR   Mode B: Direct Ticker Evaluation (same canonical pipeline)
    python app.py status [RUN_ID]      show a previous run (default: latest)
    python app.py doctor               environment / provider self-check
    python app.py tracking status      prospective ledger, cohorts and latest outcome update (P6-20)
    python app.py tracking update      fetch completed daily bars and recompute paper outcomes
    python app.py tracking report      write tracking/reports/latest.md / latest.html
    python app.py tracking verify      hash chains, artifact integrity, reconstruction, replay
    python app.py track                alias: tracking update + tracking report

Multi-market (P6-21..25): ``--market`` selects the market (default US, unchanged behaviour).
    python app.py --market KR scan --capital 10000000   KR liquid-300 scan (EXPERIMENTAL model, KRW)
    python app.py --market KR evaluate 005930 035720    KR direct evaluation against the liquid-300 reference
    python app.py --market KR tracking update|report|status|verify
    python app.py qsf evaluate AAPL    QSF 1.1 score and holding plan (also: scan, validate, verify; --market KR)
    python app.py automation [status|run|install|uninstall|test-notify|telegram-chat]   daily job and alerts
    python app.py dashboard [--open]   unified US/KR dashboard (read-only, tracking/dashboard.html)
    python app.py migrate-storage      idempotent, additive storage layout v2 (backs up tracking/ first)
    python app.py terminal [--open]    personal terminal, local web app at http://127.0.0.1:8765 (TERMINAL-1..3)
    python app.py terminal-agent [status|install|uninstall]   keep the terminal running (start at login, restart on exit)
    python app.py lab update           refresh the lab price panel and record today's challenger signals (TERMINAL-3)
    python app.py lab status           challenger ledger and panel status

Capital is REQUIRED (no default): pass --capital AMOUNT or set QPP_CAPITAL in .env.

Every run writes a durable artifact directory under ``runs/<run_id>/``.
No orders are ever placed; output is research information, not advice.
"""
import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("QPP_LOG_LEVEL", "WARNING")

from utils import runtime_config  # noqa: E402  (stdlib-only; loads before utils.config reads the env)

runtime_config.load_local_env()


def _print_result(result) -> int:
    from pipeline.report import console_summary
    print(console_summary(result))
    if result.get("artifact_dir"):
        print(f"  HTML report: {Path(result['artifact_dir']) / 'report.html'}")
    return 0 if result.get("execution_status") != "FAILED" else 2


def _open(path: Path):
    if sys.platform == "darwin" and path.exists():
        os.system(f'open "{path}"')


def _preflight(args) -> None:
    sec = runtime_config.sec_user_agent_status()
    print(f"Capital: ${args.capital:,.2f} USD  (source: {args.capital_source})")
    if sec["status"] != "CONFIGURED":
        print(f"NOTE: SEC EDGAR disabled — {sec['reason']} ROE/profit margin will come from Yahoo only.\n"
              "      Set SEC_USER_AGENT='<AppName>/1.0 <your e-mail>' in .env (see README).")


def cmd_scan(args) -> int:
    from pipeline.service import run_market_scan
    scope = f"first {args.limit} constituents" if args.limit else "full S&P 500 (~500 symbols)"
    print(f"Automated Market Scan — {scope}. Fundamentals are cached for "
          f"{_ttl()}h; a cold full scan can take 10-30 minutes on public providers.")
    _preflight(args)
    result = run_market_scan(capital=args.capital, limit=args.limit, capital_source=args.capital_source)
    code = _print_result(result)
    if args.open and result.get("artifact_dir"):
        _open(Path(result["artifact_dir"]) / "report.html")
    return code


def cmd_evaluate(args) -> int:
    from pipeline.service import run_direct_evaluation
    print(f"Direct Ticker Evaluation for {' '.join(args.tickers)} — scored inside the canonical "
          f"S&P 500 comparison cross-section{' (bounded to ' + str(args.comparison_limit) + ')' if args.comparison_limit else ''}.")
    _preflight(args)
    result = run_direct_evaluation(args.tickers, capital=args.capital, comparison_limit=args.comparison_limit,
                                   capital_source=args.capital_source)
    code = _print_result(result)
    if args.open and result.get("artifact_dir"):
        _open(Path(result["artifact_dir"]) / "report.html")
    return code


def cmd_status(args) -> int:
    from utils import config as cfg
    root = Path(cfg.RUNS_DIR)
    run_id = args.run_id or ((root / "LATEST").read_text().strip() if (root / "LATEST").exists() else None)
    if not run_id:
        print("No runs recorded yet.")
        return 1
    d = root / run_id
    status = json.loads((d / "execution_status.json").read_text())
    print(f"Run {run_id}: state={status['state']} last_checkpoint={status['last_checkpoint']} "
          f"elapsed={status['elapsed_seconds']}s peak_rss={status['peak_rss_mb']}MB")
    if (d / "validation_result.json").exists():
        from pipeline.report import console_summary
        v = json.loads((d / "validation_result.json").read_text())
        v["artifact_dir"] = str(d)
        print(console_summary(v))
    if (d / "failure.json").exists():
        f = json.loads((d / "failure.json").read_text())
        print(f"FAILURE after {f['failed_after_checkpoint']}: {f['error_type']}: {f['error']}")
    return 0


def _ttl():
    from utils import config as cfg
    return cfg.FINANCIAL_CACHE_TTL_HOURS


def offloaded_files(root: Path = PROJECT_ROOT, limit: int = 2000):
    """Files evicted by iCloud 'Optimize Mac Storage' (SF_DATALESS) block imports until re-downloaded."""
    SF_DATALESS = 0x40000000
    found = []
    for base in ("app.py", "main.py", "core", "data", "pipeline", "utils", "contracts", "tests", ".venv/lib"):
        p = root / base
        paths = [p] if p.is_file() else (p.rglob("*.py") if p.exists() else [])
        for f in paths:
            try:
                if getattr(os.stat(f, follow_symlinks=True), "st_flags", 0) & SF_DATALESS:
                    found.append(str(f.relative_to(root)))
            except OSError:
                continue
            if len(found) >= limit:
                return found
    return found


def cmd_doctor(args) -> int:
    import platform
    ok = True
    print(f"Python {sys.version.split()[0]} ({platform.machine()}) at {sys.executable}")
    if sys.version_info < (3, 10):
        ok = False
        print("  FAIL: Python >= 3.10 required")
    for mod in ("numpy", "pandas", "yfinance", "requests", "bs4"):
        try:
            m = __import__(mod)
            print(f"  ok  {mod} {getattr(m, '__version__', '')}")
        except Exception as exc:
            ok = False
            print(f"  FAIL {mod}: {exc}")
    off = offloaded_files()
    if off:
        print(f"  WARN {len(off)} project files are offloaded to iCloud (dataless), e.g. {off[:3]}.\n"
              "       Startup/imports can hang. In Finder right-click the project folder -> 'Keep Downloaded',\n"
              "       or move the project outside Desktop/Documents.")
    else:
        print("  ok  no iCloud-offloaded project files")
    from utils import config as cfg
    loc = project_location_warning()
    print(f"  {'WARN' if loc else 'ok  '} project location {PROJECT_ROOT}" + (f"\n       {loc}" if loc else ""))
    try:
        import shutil
        du = shutil.disk_usage(PROJECT_ROOT)
        pct = du.used / du.total * 100
        print(f"  {'WARN' if pct > 90 else 'ok  '} disk {du.free / 1e9:.1f} GB free ({pct:.0f}% used)")
    except OSError:
        pass
    print(f"  {'ok  ' if runtime_config.ENV_FILE.exists() else 'info'} .env "
          f"{'found' if runtime_config.ENV_FILE.exists() else 'not found (copy .env.example to .env)'}")
    sec = runtime_config.sec_user_agent_status()
    print(f"  {'ok  ' if sec['status'] == 'CONFIGURED' else 'WARN'} SEC_USER_AGENT {sec['status']}"
          + ("" if sec["status"] == "CONFIGURED" else f" — {sec['reason']} SEC EDGAR will not be queried."))
    try:
        cap, src = runtime_config.resolve_capital(None)
        print(f"  ok   capital ${cap:,.0f} from {src}")
    except runtime_config.CapitalNotConfigured:
        print("  info capital not configured: pass --capital on each run or set QPP_CAPITAL in .env")
    print(f"  {'ok  ' if not cfg.NEWS_API_KEY else 'info'} NEWS_API_KEY "
          f"{'not set (optional; not used by the recommendation pipeline)' if not cfg.NEWS_API_KEY else 'set (optional)'}")
    if args.network:
        import requests
        checks = {
            "Wikipedia S&P 500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                                  {"User-Agent": runtime_config.http_user_agent()}),
        }
        if sec["status"] == "CONFIGURED":
            checks["SEC CompanyFacts"] = ("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                                          {"User-Agent": cfg.SEC_USER_AGENT})
        else:
            print("  skip SEC CompanyFacts: not queried without a valid SEC_USER_AGENT")
        for name, (url, headers) in checks.items():
            try:
                r = requests.get(url, headers=headers, timeout=15)
                print(f"  {'ok  ' if r.status_code == 200 else 'FAIL'} {name}: HTTP {r.status_code}")
                ok &= r.status_code == 200
            except Exception as exc:
                ok = False
                print(f"  FAIL {name}: {type(exc).__name__}")
        try:
            import yfinance as yf
            d = yf.download("AAPL", period="5d", progress=False, auto_adjust=True)
            print(f"  {'ok  ' if not d.empty else 'FAIL'} yfinance download: {len(d)} bars, last {d.index[-1].date() if not d.empty else 'n/a'}")
            ok &= not d.empty
        except Exception as exc:
            ok = False
            print(f"  FAIL yfinance: {type(exc).__name__}")
    print("Doctor:", "OK" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1


def project_location_warning() -> str:
    """iCloud 'Desktop & Documents' sync can offload files; running from there can hang imports."""
    home = Path.home()
    for synced in (home / "Desktop", home / "Documents", home / "Library" / "Mobile Documents"):
        try:
            PROJECT_ROOT.resolve().relative_to(synced.resolve())
            return (f"inside {synced} (iCloud-synced on many Macs). Move the project to ~/Developer "
                    "(see README 1절 '프로젝트 위치').")
        except ValueError:
            continue
    return ""


def _print_tracking_status(st) -> None:
    print(f"Prospective ledger: {st['runs']} run(s), {st['observations']} observation(s)")
    for k, n in sorted(st["by_class_and_cohort"].items()):
        print(f"  {k:<48} {n}")
    for rid, c in sorted(st["run_cohorts"].items()):
        print(f"  run {rid}: {c}")
    u = st.get("latest_update")
    if u:
        print(f"Latest update: {u['update_id']} {u['status']} as of session {u['as_of_session']}"
              + (f" (missing: {', '.join(u['missing_tickers'])})" if u.get("missing_tickers") else ""))
        print(f"  TOP-5 outcome states: {st.get('outcome_states')}")
    else:
        print("No outcome update yet: run `python app.py tracking update`.")


def cmd_tracking(args) -> int:
    """P6-20 prospective tracking: status | update | report | exclusions | verify | replay."""
    from pipeline import prospective_ledger as ledger
    from pipeline import prospective_tracking as tracking
    action = getattr(args, "action", None) or "status"
    if action == "status":
        ledger.sync_runs("runs")
        _print_tracking_status(tracking.status())
        return 0
    if action == "update":
        res = tracking.update(runs_dir="runs", offline=getattr(args, "offline", False))
        if res.get("sync", {}).get("recorded_runs"):
            print(f"Recorded runs from artifacts: {', '.join(res['sync']['recorded_runs'])}")
        print(f"Update {res.get('update_id')}: {res['status']}"
              + (f" as of session {res['as_of_session']}" if res.get("as_of_session") else "")
              + (f" - {res['error']}" if res.get("error") else ""))
        if res.get("missing_tickers"):
            print(f"  missing price data (left missing, never estimated): {', '.join(res['missing_tickers'])}")
        if res["status"] in ("COMPLETE", "PARTIAL", "NO_CHANGE"):
            _print_tracking_status(tracking.status())
            print("Report: tracking/reports/latest.md (and latest.html)")
        return 0 if res["status"] not in ("FAILED",) else 1
    if action == "report":
        path = tracking.write_report()
        if not path:
            print("No outcome update yet: run `python app.py tracking update`.")
            return 1
        res = tracking.load_latest_result()
        s = res["summary"]
        print(f"As of session {res['as_of_session']}: {s['valid_observations']} valid TOP-5 observations, "
              f"{s['completed_observations']} completed, states {s['outcome_states']}")
        if s["completed_observations"]:
            pr, ex = s["price_return"], s["excess_vs_spy"]
            print(f"  price return mean {pr['mean']:+.2%} median {pr['median']:+.2%} win {pr['win_rate']:.0%}; "
                  f"excess vs SPY mean {ex['mean']:+.2%}" if ex["mean"] is not None else "")
        print(f"  [{s['sample_status']}] {s['statistical_caution']}")
        print(f"Report: {path} (and latest.html)")
        if getattr(args, "open", False) and sys.platform == "darwin":
            os.system(f"open '{path.with_suffix('.html')}'")
        return 0
    if action == "exclusions":
        if getattr(args, "add", None):
            ok = ledger.append_event("EXCLUSION", {"run_id": args.add}, args.reason or "", args.category,
                                     source="user (app.py tracking exclusions --add)")
            print("Exclusion event appended." if ok else "Identical exclusion already recorded.")
        idx = ledger.exclusions_index()
        if not idx:
            print("No exclusions.")
        for target, events in sorted(idx.items()):
            for e in events:
                print(f"  {target}: {e.get('category')} - {e.get('reason')} [{e.get('source')}]")
        return 0
    if action == "verify":
        res = ledger.verify(runs_dir="runs")
        for c in res["chains"]:
            print(f"  chain {c['file']}: {c['rows']} rows, {'OK' if c['ok'] else 'BROKEN ' + str(c['problems'][:3])}")
        for rid, r in sorted(res["runs"].items()):
            print(f"  run {rid}: artifacts {r['artifacts']}, reconstruction {r['reconstruction']}")
        rp = tracking.replay_update()
        if rp.get("match") is not None:
            print(f"  latest update {rp['update_id']}: replay from stored snapshot "
                  f"{'MATCH' if rp['match'] else 'MISMATCH'}")
        print("Verify:", "OK" if res["ok"] and rp.get("match") is not False else "PROBLEMS FOUND")
        return 0 if res["ok"] and rp.get("match") is not False else 1
    if action == "replay":
        rp = tracking.replay_update(getattr(args, "update_id", None))
        print(json.dumps(rp, indent=1))
        return 0 if rp.get("match") else 1
    print(f"unknown tracking action {action}")
    return 2


def cmd_track(args) -> int:
    """Backward-compatible alias (P6-19): update outcomes, then print the report summary."""
    rc = cmd_tracking(argparse.Namespace(action="update", offline=False))
    if rc:
        return rc
    return cmd_tracking(argparse.Namespace(action="report", open=False))


def _ask_capital() -> tuple:
    try:
        return runtime_config.resolve_capital(None)
    except runtime_config.CapitalNotConfigured:
        pass
    while True:
        raw = input("Investment capital in USD for position sizing (e.g. 50000; q to quit): ").strip()
        if raw.lower() in ("q", "quit", ""):
            raise SystemExit(1)
        try:
            return runtime_config.parse_capital(raw), "interactive prompt"
        except runtime_config.CapitalNotConfigured as exc:
            print(f"  {exc}")


def interactive() -> int:
    print("\nQuant Stock Recommendation (frozen P6-11B model, public data only)\n"
          "  1) Automated Market Scan (full S&P 500)\n"
          "  2) Quick bounded scan (first 25 constituents — validation only)\n"
          "  3) Evaluate specific tickers\n"
          "  4) Show latest run\n"
          "  5) Environment check\n"
          "  6) Forward performance observation\n"
          "  q) Quit")
    choice = input("Select: ").strip().lower()
    if choice in ("1", "2", "3"):
        capital, source = _ask_capital()
    if choice == "1":
        return cmd_scan(argparse.Namespace(capital=capital, capital_source=source, limit=None, open=True))
    if choice == "2":
        return cmd_scan(argparse.Namespace(capital=capital, capital_source=source, limit=25, open=True))
    if choice == "3":
        tickers = input("Tickers (e.g. NVDA AAPL TSLA PLTR): ").split()
        if not tickers:
            print("No tickers entered.")
            return 1
        return cmd_evaluate(argparse.Namespace(tickers=tickers, capital=capital, capital_source=source,
                                               comparison_limit=None, open=True))
    if choice == "4":
        return cmd_status(argparse.Namespace(run_id=None))
    if choice == "5":
        return cmd_doctor(argparse.Namespace(network=True))
    if choice == "6":
        return cmd_track(argparse.Namespace())  # update + report
    return 0


def cmd_lab(args) -> int:
    from terminal.lab.service import Lab, LabError
    lab = Lab(PROJECT_ROOT)
    try:
        if args.action == "update":
            print("가격 데이터 갱신 중 (S&P 500 약 500종목, 처음에는 몇 분 걸립니다)…", flush=True)
            res = lab.update(lambda d, t: print(f"  {d}/{t}", flush=True))
        elif args.action == "status":
            res = lab.status()
        else:
            c = lab.comparison()
            res = {m: {h: {k: v for k, v in a.items() if k in ("matured", "independent", "mean_excess", "hit_rate", "verdict")}
                       for h, a in c["results"][m]["horizons"].items()} for m in c["order"]}
    except LabError as exc:
        print(f"실패: {exc}")
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0


def _without(key):
    return lambda res, mod: {k: v for k, v in res.items() if k != key}


def _primary(res, mod):
    return res.get("primary", res)


# One-shot QSF research and validation runs: action -> (module in terminal.qsf, function, what to print, json indent).
# Each was run once under a protocol in reports/; the commands stay so the methods remain readable and runnable.
QSF_ONE_SHOT = {
    **{a: ("validate_corrected", f, lambda r, m: {k: r[k] for k in ("status", "companies", "failed") if k in r}, None) for a, f in (
        ("corrected-prepare", "prepare"), ("corrected-open", "run_open"), ("corrected-oos", "run_oos"), ("corrected-research", "run_research"),
        ("corrected-swing", "run_swing"), ("sue-test", "test_sue"))},
    **{a: ("research_short", f, _without("strategies"), None) for a, f in (("short-download", "fetch_all"), ("short-develop", "develop"), ("short-test", "test_once"))},
    **{a: ("research_sentiment", f, _without("strategies"), None) for a, f in (("sentiment-download", "fetch_vix"), ("sentiment-run", "run_once"))},
    "kr-forward-evaluate-events": ("kr_events_forward", "evaluate_once", _without("buckets"), None),
    **{a: ("research_kr_live", f, lambda r, m: {k: v for k, v in r.items() if k not in ("tables", "reference_2022", "domains", "top3", "fidelity", "no_dart_code")}, 1)
       for a, f in (("kr-live-download", "download"), ("kr-live-prepare", "prepare"), ("kr-live-fidelity", "fidelity"), ("kr-live-run", "run_once"),
                    ("kr-universe-download", "download_cap"), ("kr-universe-prepare", "prepare_cap"), ("kr-universe-run", "run_universe_once"))},
    **{a: ("research_us_13f", f, lambda r, m: {k: v for k, v in r.items() if k not in ("scores", "quarters", "money_20d", "link_attempts")}, 1)
       for a, f in (("us-13f-reduce", "reduce_all"), ("us-13f-prepare", "prepare"), ("us-13f-run", "run_once"))},
    "picks-sim": ("sim_picks", "run_once", lambda r, m: {"primary": r["picks"]["primary"], "report": str(m.REPORT)}, 1),
    **{a: ("research_kr_events", f, _without("scores"), None) for a, f in (("kr-events-download", "download"), ("kr-events-prepare", "prepare"), ("kr-events-run", "run_once"))},
    **{a: ("research_kr_fund", f, _without("scores"), None) for a, f in (("kr-fund-download", "download"), ("kr-fund-prepare", "prepare"), ("kr-fund-run", "run_once"))},
    **{a: ("research_kr", f, _without("strategies"), None) for a, f in (("kr-download", "download"), ("kr-prepare", "prepare"), ("kr-run", "run_once"), ("kr-diagnose", "diagnose"))},
    **{a: ("research_ensemble", f, _without("strategies"), None) for a, f in (("ensemble-prepare", "prepare"), ("ensemble-run", "run_once"))},
    **{a: ("research_news", f, _without("strategies"), None) for a, f in (("news-prepare", "prepare"), ("news-develop", "develop"), ("news-test", "test_once"))},
    **{a: ("research_insider", f, _without("strategies"), None) for a, f in (("insider-prepare", "prepare"), ("insider-develop", "develop"), ("insider-test", "test_once"))},
    "swing-develop": ("research_swing", "develop", lambda r, m: {"status": r["status"], "report": str(m.DEV_REPORT)}, None),
    "swing-test": ("research_swing", "test_once", lambda r, m: {"status": r["status"], "report": str(m.TEST_REPORT)}, None),
    "research-develop": ("research_score", "develop", lambda r, m: r["strategies"], 1),
    "research-test": ("research_score", "test_once", lambda r, m: r["strategies"], 1),
    **{a: ("validate_oos", f, _primary, 1) for a, f in (("oos-prepare", "prepare"), ("oos-score", "score"), ("oos-test", "test_once"))},
    **{a: ("validate_open", f, _primary, 1) for a, f in (("open-prepare", "prepare"), ("open-run", "run"))},
    **{a: ("validate_pit", f, _primary, 1) for a, f in (("pit-prepare", "prepare"), ("pit-run", "run"))},
    **{a: ("validate", f, _primary, 1) for a, f in (("history-prepare", "prepare"), ("history-run", "run"))},
}
QSF_ACTIONS = ["evaluate", "scan", "validate", "verify", "top3-freeze", "top3-report", "price-archive", "kr-etf-holdings", "kr-forward-record", "kr-forward-evaluate", "kr-forward-evaluate-fund",
               "us-challenger-record", "us-challenger-evaluate-swing", "us-challenger-evaluate-long",
               "kr-swing-challenger-record", "kr-swing-challenger-status", "kr-swing-challenger-evaluate",
               "kr-swing-prior-record", "kr-swing-prior-status", "kr-swing-prior-evaluate",
               "kr-method-record", "kr-method-status", "kr-method-select", "kr-method-evaluate-120", "kr-method-evaluate-240", "kr-risk-grade-run",
               "regime-weights-run", "regime-weights-record", "regime-weights-status", "regime-weights-evaluate", "lookahead-audit", "paper-book-record", "paper-book-status", "turnover-book-record", "turnover-book-status", "rank-book-record", "rank-book-status",
               "forecast-test", "forecast-record", "forecast-status", "forecast-touch-test", "score-split-record", "score-split-status", "score-split-evaluate",
               "kr-cap-universe-record", "kr-cap-universe-status", "kr-cap-universe-evaluate", "kr-traded-universe-record", "kr-traded-universe-status", "kr-traded-universe-evaluate", "kr-tech-early-prepare", "kr-tech-early-run", "kr-long-early-download", "kr-long-early-prepare", "kr-long-early-run", "kr-holder-download", "kr-holder-prepare", "kr-holder-run", "kr-sue-prepare", "kr-sue-run",
               "backup-check", "cache-report", "cache-prune", "price-audit", "us-earnings-gap", "stability",
               "live-forward-status", "live-forward-evaluate-swing", "live-forward-evaluate-long", "kr-avoid-marks-evaluate", *QSF_ONE_SHOT]


def _regime_weights_record(market: str):
    """One market's regime-weight record.  The index is the scan's own SPY for the US and, for Korea, the KOSPI index built from
    the KRX price files (the past test's construction; Yahoo's index is a day behind at the time of the morning run)."""
    from terminal.qsf import regime_weights
    if market == "US":
        from terminal.qsf.service import QSF
        q = QSF(PROJECT_ROOT)
        bars = lambda: q._loader("US")("SPY")                                                   # noqa: E731
    else:
        bars = lambda: regime_weights.kr_index_bars(PROJECT_ROOT)                               # noqa: E731
    return regime_weights.record(PROJECT_ROOT, market, bars)


def _paper_book_record(market: str):
    """One market's paper book up to the newest ledger session.  Prices are the scan's own; nothing is asked of a broker."""
    from terminal.qsf import paper_book
    from terminal.qsf.service import QSF
    q = QSF(PROJECT_ROOT)
    info = lambda: {r["ticker"]: {"name": r.get("name"), "sector": r.get("sector")} for r in q.screen_rows(market).get("rows") or []}        # noqa: E731
    bench = (lambda: (q._history(["^KS11"], "2y")["data"] or {}).get("^KS11") or []) if market == "KR" else None                                # noqa: E731
    from terminal.qsf import rank_book
    rules, version = rank_book.paper_rules(PROJECT_ROOT, market)    # rule sets in force only after their reading said ADOPT, or by the user's .env switches
    res = paper_book.record(PROJECT_ROOT, market, q._loader(market), info=info, bench=bench, rules=rules, version=version)
    res["turnover_book"] = _turnover_book_record(market, q, info, bench)      # the comparison book (TO-1), right after the paper book every time
    res["rank_book"] = _rank_book_record(market, q, info, bench)              # and the rank rules' comparison book (RK-1)
    return res


def _turnover_book_record(market: str, q, info, bench):
    """The comparison book under the turnover rules (TO-1), on the same prices as the paper book.  reports/QSF_TURNOVER_RULES_PROTOCOL.md.
    Never raises: a failure is a FAILED result with the error's type name, and the paper book's own result stands."""
    from terminal.qsf import turnover_book
    try:
        return {k: v for k, v in turnover_book.record(PROJECT_ROOT, market, q._loader(market), info=info, bench=bench).items() if k != "market"}
    except Exception as exc:
        return {"status": "FAILED", "reason": type(exc).__name__}


def _forecast_record(market: str):
    """One market's forecast record (FC-1) up to the newest ledger session, on the scan's own prices, then the view file."""
    from terminal.qsf import forecast
    from terminal.qsf.service import QSF
    q = QSF(PROJECT_ROOT)
    res = forecast.record(PROJECT_ROOT, market, q._loader(market))
    try:                        # the view reads both stores; a failure here never fails the record
        forecast.write_status(PROJECT_ROOT, {m: q._loader(m) for m in forecast.FOLDERS})
    except Exception as exc:
        res["view"] = type(exc).__name__
    return res


# ----------------------------------------------------------------------------- qsf actions, one function each
# Each was a branch of one 300-line function until 2026-11-14; the bodies are unchanged.
def _qsf_kr_sue(args) -> int:
    from terminal.qsf import research_kr_sue as sue
    res = {"kr-sue-prepare": sue.prepare, "kr-sue-run": sue.run_once}[args.action](PROJECT_ROOT)
    if args.action == "kr-sue-run":
        res = {"status": res["status"], "reading": res["reading"], "conditions": res["conditions"], "partial": res["partial"],
               "primary": {k: res["scores"]["SUE"][sue.PRIMARY].get(k) for k in ("ic", "t", "top_excess", "spread_net", "verdict", "dates", "mean_stocks")}}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0


def _qsf_kr_holder(args) -> int:
    from terminal.qsf import research_kr_holder as rh
    if args.action == "kr-holder-download":
        res = rh.download(PROJECT_ROOT, rh.plan(PROJECT_ROOT))
    else:
        res = {"kr-holder-prepare": rh.prepare, "kr-holder-run": rh.run_once}[args.action](PROJECT_ROOT)
    print(json.dumps(res, ensure_ascii=False, default=str))
    return 0 if res.get("status") in ("DONE", "PAUSED", "PREPARED", "TESTED") else 1


def _qsf_backup_check(args) -> int:
    from terminal import automation
    res = automation.check_backup()
    print(json.dumps({**automation.backup_status(), **res}, ensure_ascii=False, default=str))
    return 0 if res["status"] == "OK" else 1


def _qsf_price_audit(args) -> int:
    from terminal.qsf import price_audit
    from utils import nyse_calendar
    res = price_audit.run(PROJECT_ROOT, nyse_calendar.sessions_between)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


def _qsf_cache(args) -> int:
    from terminal import storage
    res = storage.prune_cache(PROJECT_ROOT, apply=args.action == "cache-prune" and args.apply)
    print(json.dumps({"disk": storage.disk(PROJECT_ROOT), **res}, ensure_ascii=False))
    return 0


def _qsf_kr_forward(args) -> int:
    from terminal.qsf import kr_forward
    if args.action in ("kr-forward-evaluate", "kr-forward-evaluate-fund"):
        res = kr_forward.evaluate_once(PROJECT_ROOT, store=kr_forward.FUND_FOLDER if args.action.endswith("fund") else kr_forward.FOLDER)
        print(json.dumps({k: v for k, v in res.items() if k != "buckets"}, ensure_ascii=False, default=str))
        return 0
    res = kr_forward.record(PROJECT_ROOT)
    try:                        # the swing challenger reads the ledger only; a failure here never fails the forward step
        from terminal.qsf import kr_swing_challenger
        res["swing_challenger"] = kr_swing_challenger.record(PROJECT_ROOT)
    except Exception as exc:
        res["swing_challenger"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the former swing formula next to the live score, from the ledger only; it never fails the step either
        from terminal.qsf import kr_swing_prior
        res["swing_prior"] = kr_swing_prior.record(PROJECT_ROOT)
    except Exception as exc:
        res["swing_prior"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the market-value universe record scores with a scan that writes no live file; it never fails the step either
        from terminal.qsf import kr_cap_universe
        from terminal.qsf.service import QSF
        res["cap_universe"] = kr_cap_universe.record(PROJECT_ROOT, QSF(PROJECT_ROOT))
    except Exception as exc:
        res["cap_universe"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the former live universe (the 300 most traded), scored the same way; it never fails the step either
        from terminal.qsf import kr_traded_universe
        from terminal.qsf.service import QSF
        res["traded_universe"] = kr_traded_universe.record(PROJECT_ROOT, QSF(PROJECT_ROOT))
    except Exception as exc:
        res["traded_universe"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the own trading method (KR-M1) reads the ledger, the day's marks and the price files; it never fails the step either
        from terminal.qsf import kr_method
        res["method"] = kr_method.record(PROJECT_ROOT)
        kr_method.write_status(PROJECT_ROOT)
    except Exception as exc:
        res["method"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the regime-weight challenger reads the ledger and the index; it never fails the step either
        res["regime_weights"] = _regime_weights_record("KR")
    except Exception as exc:
        res["regime_weights"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the paper book follows the day's plan on the scan's prices; it never fails the step either
        res["paper_book"] = {k: v for k, v in _paper_book_record("KR").items() if k != "market"}
    except Exception as exc:
        res["paper_book"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the former formula beside the split score (QSF-1.4.0), from the ledger only; it never fails the step either
        from terminal.qsf import score_split
        res["score_split"] = {k: v for k, v in score_split.record(PROJECT_ROOT, "KR").items() if k != "market"}
    except Exception as exc:
        res["score_split"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the forecast layer reads the ledger and the scan's prices; it never fails the step either
        res["forecast"] = {k: v for k, v in _forecast_record("KR").items() if k != "market"}
    except Exception as exc:
        res["forecast"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the look-ahead audit reads prices and record indexes and writes one view file; it never fails the step
        from terminal.qsf import lookahead
        audit = lookahead.run(PROJECT_ROOT)
        res["lookahead"] = {"status": audit["status"], "problems": audit["problems"]}
    except Exception as exc:
        res["lookahead"] = {"status": "FAILED", "reason": type(exc).__name__}
    print(json.dumps(res, ensure_ascii=False, default=str))
    return {"OK": 0, "WAITING": 3, "NO_KEY": 4}.get(res["status"], 1)


def _qsf_kr_long_early(args) -> int:      # reports/QSF_KR_LONG_EARLY_PROTOCOL.md
    from terminal.qsf import research_kr_long_early as le
    res = le.download(PROJECT_ROOT) if args.action.endswith("download") else le.prepare(PROJECT_ROOT) if args.action.endswith("prepare") else le.run_once(PROJECT_ROOT)
    if args.action.endswith("run"):
        p = res["primary"]
        res = {"status": res["status"], "days": res["days"], "reading": p["reading"], "dates": p.get("dates"), "ic": p.get("ic"), "t": p.get("t"), "condition_a": p["condition_a"], "condition_b": p["condition_b"]}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in ("REAL", "OK", "DONE") else 3


def _qsf_kr_tech_early(args) -> int:      # one confirmation run (reports/QSF_KR_TECH_EARLY_PROTOCOL.md)
    from terminal.qsf import research_kr_tech as rt
    res = rt.prepare(PROJECT_ROOT) if args.action.endswith("prepare") else rt.run_once(PROJECT_ROOT)
    keep = ("status", "days", "first", "last", "records", "mean_universe", "technical_scored_share", "fund_present", "technical", "risk_minus_composite")
    print(json.dumps({k: res[k] for k in keep if k in res}, ensure_ascii=False, indent=1, default=str))
    return 0


def _qsf_kr_cap_universe(args) -> int:
    from terminal.qsf import kr_cap_universe as cu
    if args.action.endswith("record"):
        from terminal.qsf.service import QSF
        res = cu.record(PROJECT_ROOT, QSF(PROJECT_ROOT))
    else:
        res = cu.status(PROJECT_ROOT) if args.action.endswith("status") else {k: v for k, v in cu.evaluate_once(PROJECT_ROOT).items() if k != "long_reference"}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in (None, "OK", "REAL") else 3 if res.get("status") == "WAITING" else 1


def _qsf_kr_swing_challenger(args) -> int:
    from terminal.qsf import kr_swing_challenger as sc
    res = sc.evaluate_once(PROJECT_ROOT) if args.action.endswith("evaluate") else sc.status(PROJECT_ROOT) if args.action.endswith("status") else sc.record(PROJECT_ROOT)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in (None, "OK", "REAL") else 3 if res.get("status") == "WAITING" else 1


def _qsf_kr_traded_universe(args) -> int:
    from terminal.qsf import kr_traded_universe as tu
    if args.action.endswith("record"):
        from terminal.qsf.service import QSF
        res = tu.record(PROJECT_ROOT, QSF(PROJECT_ROOT))
    else:
        res = tu.status(PROJECT_ROOT) if args.action.endswith("status") else {k: v for k, v in tu.evaluate_once(PROJECT_ROOT).items() if k != "former_long_reference"}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in (None, "OK", "REAL") else 3 if res.get("status") == "WAITING" else 1


def _qsf_kr_method(args) -> int:      # reports/QSF_KR_METHOD_PROTOCOL.md
    from terminal.qsf import kr_method as km
    if args.action.endswith("record"):
        res = km.record(PROJECT_ROOT)
        km.write_status(PROJECT_ROOT)
    elif args.action.endswith("status"):
        res = {k: v for k, v in km.status(PROJECT_ROOT).items() if k not in ("pool_codes", "names", "family")}
    elif args.action.endswith("select"):
        res = {k: v for k, v in km.select_once(PROJECT_ROOT).items() if k != "pools"}
    else:
        res = km.evaluate_once(PROJECT_ROOT, int(args.action.rsplit("-", 1)[-1]))
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in (None, "OK", "REAL", "ALREADY_RUN") else 3 if res.get("status") in ("WAITING", "NOT_READY", "NO_RECORD") else 1


def _qsf_kr_risk_grade_run(args) -> int:      # one run (reports/QSF_KR_RISK_GRADE_PROTOCOL.md); a stored result is printed as it is
    from terminal.qsf import kr_risk_grade
    res = kr_risk_grade.run_once(PROJECT_ROOT)
    print(json.dumps({k: res[k] for k in ("status", "verdict", "primary") if k in res}, ensure_ascii=False, indent=1, default=str))
    return 0


def _qsf_kr_swing_prior(args) -> int:
    from terminal.qsf import kr_swing_prior as sp
    res = sp.evaluate_once(PROJECT_ROOT) if args.action.endswith("evaluate") else sp.status(PROJECT_ROOT) if args.action.endswith("status") else sp.record(PROJECT_ROOT)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in (None, "OK", "REAL") else 3 if res.get("status") == "WAITING" else 1


def _qsf_stability(args) -> int:      # read only: how much the live score moves between sessions of one model version
    from terminal.qsf import stability
    print(json.dumps(stability.report(PROJECT_ROOT), ensure_ascii=False, indent=1))
    return 0


def _qsf_us_earnings_gap(args) -> int:      # read only: the count the daily job takes once on or after earnings_gap.DUE
    from terminal.qsf import earnings_gap
    res = earnings_gap.count(PROJECT_ROOT)
    print(json.dumps(res if res else {"status": "NO_US_SESSION"}, ensure_ascii=False))
    return 0 if res else 3


def _qsf_paper_book(args) -> int:      # reports/PAPER_BOOK_RULES.md
    from terminal.qsf import paper_book
    if args.action.endswith("record"):
        res = _paper_book_record(args.market)
    else:
        res = {k: v for k, v in paper_book.status(PROJECT_ROOT, args.market).items() if k not in ("curve", "exit_labels", "unfilled_labels", "binding_labels", "skip_labels")}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in ("OK", "REAL") else 3 if res.get("status") in ("WAITING", "NO_RECORD") else 1


def _rank_book_record(market: str, q, info, bench):
    """The comparison book under the rank rules (RK-1), on the same prices as the paper book.  reports/QSF_RANK_RULES_PROTOCOL.md.
    Never raises: a failure is a FAILED result with the error's type name, and the paper book's own result stands."""
    from terminal.qsf import rank_book
    try:
        return {k: v for k, v in rank_book.record(PROJECT_ROOT, market, q._loader(market), info=info, bench=bench).items() if k != "market"}
    except Exception as exc:
        return {"status": "FAILED", "reason": type(exc).__name__}


def _qsf_turnover_book(args) -> int:      # the two comparison books (TO-1, RK-1); their readings run in the daily job's wrap-up
    from terminal.qsf import rank_book, turnover_book
    book, key = (rank_book, "rank_book") if args.action.startswith("rank") else (turnover_book, "turnover_book")
    res = _paper_book_record(args.market)[key] if args.action.endswith("record") else book.status(PROJECT_ROOT, args.market)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in ("OK", "DONE", "RECORDING", "DECIDED") else 3 if res.get("status") in ("WAITING", "NO_RECORD") else 1


def _qsf_forecast(args) -> int:      # reports/QSF_FORECAST_PROTOCOL.md
    from terminal.qsf import forecast
    if args.action.endswith("test"):             # one run; a stored result is printed as it is
        doc = forecast.run_once(PROJECT_ROOT)
        res = {"status": doc["status"], "markets": {m: {"verdict": v["verdict"], "days": v["days"], "first": v["first"], "last": v["last"], "failed": v["failed"],
                                                        "cover": {h: {"80": x["cover80"], "50": x["cover50"]} for h, x in v["horizons"].items()}} for m, v in doc["markets"].items()}}
    elif args.action.endswith("record"):
        res = _forecast_record(args.market)
    else:
        res = {k: v for k, v in forecast.status(PROJECT_ROOT).items() if k != "limits"}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in ("OK", "REAL", "ALREADY_RUN") else 3 if res.get("status") in ("WAITING", "NO_RECORD") else 1


def _qsf_forecast_touch(args) -> int:      # reports/QSF_FORECAST_TOUCH_PROTOCOL.md; one run, a stored result is printed as it is
    from terminal.qsf import forecast_touch
    doc = forecast_touch.run_once(PROJECT_ROOT)
    res = {"status": doc["status"], "markets": {m: {"verdict": v["verdict"], "days": v["days"], "first": v["first"], "last": v["last"], "failed": v["failed"]} for m, v in doc["markets"].items()}}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in ("REAL", "ALREADY_RUN") else 1


def _qsf_lookahead_audit(args) -> int:      # read-only on records; writes data/qsf/lookahead_audit.json
    from terminal.qsf import lookahead
    res = lookahead.run(PROJECT_ROOT)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res["status"] == "OK" else 3 if res["status"] == "NO_PRICES" else 1


def _qsf_regime_weights_evaluate(args) -> int:      # the one forward reading at 240 matured sessions; refused before that and after a report exists
    from terminal.qsf import regime_weights as rw
    if args.market == "KR":
        from terminal.qsf import research_kr_live
        px = research_kr_live.ensure_panel(PROJECT_ROOT, print)
    else:
        from terminal.qsf import us_challenger
        from terminal.qsf.service import QSF
        docs = [rw.kf._read_day(PROJECT_ROOT / rw.FOLDERS["US"], r["session"]) for r in rw.kf.read_index(PROJECT_ROOT, rw.FOLDERS["US"])]
        px = us_challenger.build_panel(sorted({r["ticker"] for d in docs for r in d["rows"]}), QSF(PROJECT_ROOT)._loader("US"), {})
    res = rw.evaluate_forward_once(PROJECT_ROOT, args.market, px)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0


def _qsf_score_split(args) -> int:      # reports/QSF_SCORE_SPLIT_PROTOCOL.md
    from terminal.qsf import score_split as ss
    if args.action.endswith("record"):
        res = ss.record(PROJECT_ROOT, args.market)
    elif args.action.endswith("status"):
        res = {"status": "OK", **ss.status(PROJECT_ROOT)}
    else:                                    # the one reading at 240 matured sessions; refused before that and after a report exists
        if args.market == "KR":
            from terminal.qsf import research_kr_live
            px = research_kr_live.ensure_panel(PROJECT_ROOT, print)
        else:
            from terminal.qsf import us_challenger
            from terminal.qsf.service import QSF
            docs = [ss.kf._read_day(PROJECT_ROOT / ss.FOLDERS["US"], r["session"]) for r in ss.kf.read_index(PROJECT_ROOT, ss.FOLDERS["US"])]
            px = us_challenger.build_panel(sorted({r["ticker"] for d in docs for r in d["rows"]}), QSF(PROJECT_ROOT)._loader("US"), {})
        res = ss.evaluate_once(PROJECT_ROOT, args.market, px)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in ("OK", "REAL") else 3 if res.get("status") == "WAITING" else 1


def _qsf_regime_weights(args) -> int:      # reports/QSF_REGIME_WEIGHTS_PROTOCOL.md
    from terminal.qsf import regime_weights as rw
    if args.action.endswith("run"):              # one run; a stored result is printed as it is
        doc = rw.run_once(PROJECT_ROOT)
        res = {"status": doc["status"], "markets": {m: {k: v.get(k) for k in ("verdict", "tested", "ic", "ic_diff", "ic_diff_t", "ic_over_control", "spread_net", "final_table")} for m, v in doc["markets"].items()}}
    elif args.action.endswith("record"):
        res = _regime_weights_record(args.market)
    else:
        res = rw.status(PROJECT_ROOT)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if res.get("status") in ("OK", "REAL", "ALREADY_RUN") else 3 if res.get("status") in ("WAITING", "NO_TABLE", "NO_RECORD") else 1


def _qsf_us_challenger_record(args) -> int:
    from terminal.qsf import us_challenger
    res = us_challenger.record(PROJECT_ROOT)
    try:                        # the regime-weight challenger reads the ledger and the index; it never fails the step
        res["regime_weights"] = _regime_weights_record("US")
    except Exception as exc:
        res["regime_weights"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the paper book follows the day's plan on the scan's prices; it never fails the step
        res["paper_book"] = {k: v for k, v in _paper_book_record("US").items() if k != "market"}
    except Exception as exc:
        res["paper_book"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the former formula beside the split score (QSF-1.4.0), from the ledger only; it never fails the step
        from terminal.qsf import score_split
        res["score_split"] = {k: v for k, v in score_split.record(PROJECT_ROOT, "US").items() if k != "market"}
    except Exception as exc:
        res["score_split"] = {"status": "FAILED", "reason": type(exc).__name__}
    try:                        # the forecast layer reads the ledger and the scan's prices; it never fails the step
        res["forecast"] = {k: v for k, v in _forecast_record("US").items() if k != "market"}
    except Exception as exc:
        res["forecast"] = {"status": "FAILED", "reason": type(exc).__name__}
    print(json.dumps(res, ensure_ascii=False, default=str))
    return {"OK": 0, "WAITING": 3}.get(res["status"], 1)


def _qsf_scan(args, q, market) -> int:
    res = q.scan(market, tickers=args.tickers or None, record=not args.dry_run, progress=lambda st, d, t: print(f"  {st} {d}/{t}", flush=True),
                 publish=not args.tickers)          # named stocks are scored (and recorded) without replacing the whole-universe scan on file
    print(json.dumps({k: v for k, v in res.items() if k != "rows"} | {"errors": len(res["errors"])}, ensure_ascii=False, indent=1, default=str))
    if res["status"] == "REAL" and not args.dry_run and not args.tickers:
        try:                    # the top three are frozen right after a full scan; a failure here never fails the scan
            from terminal.qsf import top_picks
            print("top3:", json.dumps(top_picks.freeze(PROJECT_ROOT, market), ensure_ascii=False, default=str))
        except Exception as exc:
            print("top3: FAILED", type(exc).__name__)
        try:                    # prices of recorded stocks, kept after they leave the scan; never fails the scan either
            print("prices:", json.dumps({k: v for k, v in q.archive_prices(market).items() if k != "not_in_scan"}, ensure_ascii=False))
        except Exception as exc:
            print("prices: FAILED", type(exc).__name__)
    if res["status"] == "DATA_NOT_READY":           # 4: price requests failed outright (no connection, the Mac asleep); 3: the day is not out yet
        if res.get("reason") == "KR_BEHIND" and res.get("recorded_before"):
            return 5                                # no session newer than the one already in the ledger (the day after a Korean holiday)
        return 4 if res.get("reason") == "DOWNLOAD_FAILED" else 3
    return 0 if res["status"] == "REAL" else 2


def _qsf_kr_etf_holdings(args, q, market) -> int:
    from terminal import kr_etf_holdings
    res = kr_etf_holdings.refresh(PROJECT_ROOT)
    print(json.dumps(res, ensure_ascii=False, default=str))
    return 0 if res["status"] == "OK" else 2


def _qsf_price_archive(args, q, market) -> int:
    res = q.archive_prices(market)
    from terminal.qsf import price_archive
    print(json.dumps({**res, "now": price_archive.status(PROJECT_ROOT, market)}, ensure_ascii=False, default=str))
    return 0


def _qsf_top3_freeze(args, q, market) -> int:
    from terminal.qsf import top_picks
    res = top_picks.freeze(PROJECT_ROOT, market)
    print(json.dumps(res, ensure_ascii=False, default=str))
    return {"OK": 0, "WAITING": 3}.get(res["status"], 1)


def _qsf_top3_report(args, q, market) -> int:
    res = q.top3(market)
    for st, part in (res.get("strategies") or {}).items():
        for d in part["days"][:5]:
            print(st, d["session"], "→", d["entry_session"], [(p["ticker"], round(p["score"], 1), None if not p["so_far"] else round(p["so_far"]["relative_net"] * 100, 2) if p["so_far"]["relative_net"] is not None else None) for p in d["top"]])
        print(st, json.dumps(part["summary"], ensure_ascii=False, default=str))
    if res["status"] != "REAL":
        print(json.dumps(res, ensure_ascii=False, default=str))
    return 0


def _qsf_us_challenger_evaluate(args, q, market) -> int:
    from datetime import date
    from terminal.qsf import us_challenger
    from utils import nyse_calendar
    index = us_challenger.kf.read_index(PROJECT_ROOT, us_challenger.FOLDER)
    first = date.fromisoformat(index[0]["session"]) if index else date.fromisoformat(us_challenger.FIRST)
    calendar = [d.isoformat() for d in nyse_calendar.sessions_between(first, nyse_calendar.latest_completed_session())]
    res = us_challenger.evaluate_once(PROJECT_ROOT, "SWING" if args.action.endswith("swing") else "LONG_TERM", q._loader("US"), calendar)
    print(json.dumps({k: res[k] for k in ("status", "strategy", "horizon", "dates", "supports_challenger", "paired_ic")}, ensure_ascii=False, default=str))
    return 0


def _qsf_live_forward(args, q, market) -> int:
    # the one forward verdict of the live score (reports/QSF_LIVE_FORWARD_PROTOCOL.md); the status only counts sessions
    from terminal.qsf import live_forward

    def bench_of(m):
        return q._loader("US")("SPY") if m == "US" else (q._history(["^KS11"])["data"] or {}).get("^KS11") or []
    if args.action == "live-forward-status":
        res = live_forward.status(PROJECT_ROOT, {m: sorted(b["date"] for b in bench_of(m)) for m in ("US", "KR")})
    elif args.action == "kr-avoid-marks-evaluate":          # read once at the Korean swing verdict's sample (reports/QSF_KR_AVOID_MARKS_PROTOCOL.md)
        from terminal.qsf import kr_avoid_marks
        res = kr_avoid_marks.evaluate_once(PROJECT_ROOT, q._loader("KR"), bench_of("KR"))
        res = {k: res.get(k) for k in ("status", "sessions_used", "days", "verdict", "reading_1", "reading_2", "buy_band_filter")}
    else:
        res = live_forward.evaluate_once(PROJECT_ROOT, market, "SWING" if args.action.endswith("swing") else "LONG_TERM", q._loader(market), bench_of(market))
        res = {k: res.get(k) for k in ("status", "market", "strategy", "horizon", "sessions_used", "verdict", "condition_a", "condition_b", "pooled")}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0


def _qsf_validate(args, q, market) -> int:
    print(json.dumps(q.validation(), ensure_ascii=False, indent=1, default=str))
    return 0


def _qsf_verify(args, q, market) -> int:
    res = q.ledger.verify()
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["status"] == "OK" else 2


QSF_HANDLERS = {
    "kr-sue-prepare": _qsf_kr_sue,
    "kr-sue-run": _qsf_kr_sue,
    "kr-holder-download": _qsf_kr_holder,
    "kr-holder-prepare": _qsf_kr_holder,
    "kr-holder-run": _qsf_kr_holder,
    "backup-check": _qsf_backup_check,
    "price-audit": _qsf_price_audit,
    "cache-report": _qsf_cache,
    "cache-prune": _qsf_cache,
    "kr-forward-record": _qsf_kr_forward,
    "kr-forward-evaluate": _qsf_kr_forward,
    "kr-forward-evaluate-fund": _qsf_kr_forward,
    "kr-long-early-download": _qsf_kr_long_early,
    "kr-long-early-prepare": _qsf_kr_long_early,
    "kr-long-early-run": _qsf_kr_long_early,
    "kr-tech-early-prepare": _qsf_kr_tech_early,
    "kr-tech-early-run": _qsf_kr_tech_early,
    "kr-cap-universe-record": _qsf_kr_cap_universe,
    "kr-cap-universe-status": _qsf_kr_cap_universe,
    "kr-cap-universe-evaluate": _qsf_kr_cap_universe,
    "kr-swing-challenger-record": _qsf_kr_swing_challenger,
    "kr-swing-challenger-status": _qsf_kr_swing_challenger,
    "kr-swing-challenger-evaluate": _qsf_kr_swing_challenger,
    "kr-traded-universe-record": _qsf_kr_traded_universe,
    "kr-traded-universe-status": _qsf_kr_traded_universe,
    "kr-traded-universe-evaluate": _qsf_kr_traded_universe,
    "kr-method-record": _qsf_kr_method,
    "kr-method-status": _qsf_kr_method,
    "kr-method-select": _qsf_kr_method,
    "kr-method-evaluate-120": _qsf_kr_method,
    "kr-method-evaluate-240": _qsf_kr_method,
    "kr-risk-grade-run": _qsf_kr_risk_grade_run,
    "kr-swing-prior-record": _qsf_kr_swing_prior,
    "kr-swing-prior-status": _qsf_kr_swing_prior,
    "kr-swing-prior-evaluate": _qsf_kr_swing_prior,
    "stability": _qsf_stability,
    "us-earnings-gap": _qsf_us_earnings_gap,
    "paper-book-record": _qsf_paper_book,
    "paper-book-status": _qsf_paper_book,
    "turnover-book-record": _qsf_turnover_book,
    "turnover-book-status": _qsf_turnover_book,
    "rank-book-record": _qsf_turnover_book,
    "rank-book-status": _qsf_turnover_book,
    "lookahead-audit": _qsf_lookahead_audit,
    "forecast-test": _qsf_forecast,
    "forecast-record": _qsf_forecast,
    "forecast-status": _qsf_forecast,
    "forecast-touch-test": _qsf_forecast_touch,
    "regime-weights-evaluate": _qsf_regime_weights_evaluate,
    "regime-weights-run": _qsf_regime_weights,
    "regime-weights-record": _qsf_regime_weights,
    "regime-weights-status": _qsf_regime_weights,
    "score-split-record": _qsf_score_split,
    "score-split-status": _qsf_score_split,
    "score-split-evaluate": _qsf_score_split,
    "us-challenger-record": _qsf_us_challenger_record,
}

QSF_LIVE_HANDLERS = {
    "scan": _qsf_scan,
    "kr-etf-holdings": _qsf_kr_etf_holdings,
    "price-archive": _qsf_price_archive,
    "top3-freeze": _qsf_top3_freeze,
    "top3-report": _qsf_top3_report,
    "us-challenger-evaluate-swing": _qsf_us_challenger_evaluate,
    "us-challenger-evaluate-long": _qsf_us_challenger_evaluate,
    "live-forward-status": _qsf_live_forward,
    "live-forward-evaluate-swing": _qsf_live_forward,
    "live-forward-evaluate-long": _qsf_live_forward,
    "kr-avoid-marks-evaluate": _qsf_live_forward,
    "validate": _qsf_validate,
    "verify": _qsf_verify,
}


def cmd_qsf(args) -> int:
    """QSF 1.1 scoring (separate from the frozen P6-11B model; no orders are ever placed)."""
    spec = QSF_ONE_SHOT.get(args.action)
    if spec:                        # the one-shot research and validation runs: each prints its own summary
        import importlib
        module, func, view, indent = spec
        mod = importlib.import_module(f"terminal.qsf.{module}")
        print(json.dumps(view(getattr(mod, func)(PROJECT_ROOT), mod), ensure_ascii=False, indent=indent, default=str))
        return 0
    handler = QSF_HANDLERS.get(args.action)         # actions that need no scorer
    if handler:
        return handler(args)
    from terminal.qsf.service import QSF
    q = QSF(PROJECT_ROOT)
    market = args.market
    handler = QSF_LIVE_HANDLERS.get(args.action)    # actions that read the live scorer
    if handler:
        return handler(args, q, market)
    if not args.tickers:
        print("종목을 지정하세요: python app.py qsf evaluate AAPL")
        return 2
    rc = 0
    for t in args.tickers:
        res = q.evaluate(t.upper(), market)
        if res["status"] != "REAL":
            print(f"{t}: 평가 불가 - {res['reason']}")
            rc = 2
            continue
        print(f"\n{res['ticker']} {res.get('name') or ''} [{market}] " + (f"(P6-11B 참고: {'상위 5 포함' if res['p6_reference'].get('in_top5') else '상위 5 아님'}, 점수와 합치지 않음)" if res.get("p6_reference") else ""))
        for s, c in res["cards"].items():
            score = "없음" if c["score"] is None else f"{c['score']:.1f}"
            print(f"  {s}: {score}점 · {c['action_label']} · {c['actionability']} · 반영률 {c['coverage'] * 100:.0f}% · 신뢰도 {c['confidence']} · 진입 {c['entry_status']}")
            print("    " + " / ".join(f"{v['label']} {'-' if v['score_100'] is None else format(v['score_100'], '.0f')}" for v in c["domains"].values()))
            print(f"    {c['why_summary']}")
            print(f"    게이트: {', '.join(g['code'] for g in c['gates']) or '없음'} · 첫 재평가 {c['holding']['first_review']}")
    return rc


def cmd_automation(args) -> int:
    from terminal import automation, notify
    if args.action == "install":
        res = automation.install(PROJECT_ROOT)
    elif args.action == "uninstall":
        res = automation.uninstall()
    elif args.action == "run":
        res = automation.Daily(PROJECT_ROOT).run(resend=args.resend)
    elif args.action == "test-notify":
        res = {"telegram": notify.send_telegram("퀀트 터미널 테스트 알림입니다."),
               "macos": notify.send_macos("퀀트 터미널", "테스트 알림입니다.")}
    elif args.action == "telegram-chat":
        res = notify.find_chats()
    else:
        res = automation.status(PROJECT_ROOT)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0


def cmd_terminal_agent(args) -> int:
    from terminal import server_agent
    if args.action == "install":
        res = server_agent.install(PROJECT_ROOT)
    elif args.action == "uninstall":
        res = server_agent.uninstall()
    else:
        res = server_agent.status(PROJECT_ROOT)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if args.action != "install" or res["installed"] else 1


def cmd_terminal(args) -> int:
    from terminal.server import HOST, serve, setup_error_log
    try:
        httpd = serve(port=args.port, base_dir=PROJECT_ROOT)
        setup_error_log(PROJECT_ROOT)
    except OSError as exc:
        print(f"터미널 서버를 시작할 수 없습니다 (포트 {args.port}): {exc.strerror}. --port 로 다른 포트를 지정하세요.", flush=True)
        return 2
    url = f"http://{HOST}:{args.port}/"
    from terminal.server_agent import LABEL
    how = "자동 재시작으로 실행 중 · 끄기: python app.py terminal-agent uninstall" if os.environ.get("XPC_SERVICE_NAME") == LABEL else "종료: Ctrl+C"
    print(f"퀀트 터미널: {url}  (이 Mac에서만 접속 가능 · {how})", flush=True)
    if args.open and sys.platform == "darwin":
        os.system(f"open '{url}'")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n터미널을 종료합니다.")
    finally:
        httpd.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app.py", description="Quant stock recommendation (frozen P6-11B, public data).")
    p.add_argument("--market", choices=["US", "KR"], default="US",
                   help="Market (default US; KR = separate experimental Korean engine, KRW)")
    sub = p.add_subparsers(dest="command")
    db = sub.add_parser("dashboard", help="Unified read-only US/KR dashboard (tracking/dashboard.html)")
    db.add_argument("--open", action="store_true")
    lb = sub.add_parser("lab", help="Challenger models beside the frozen P6-11B (TERMINAL-3)")
    lb.add_argument("action", choices=["update", "status", "compare"])
    nw = sub.add_parser("news", help="Record free news headlines of the scanned stocks (feeds no score)")
    nw.add_argument("action", choices=["record"])
    qs = sub.add_parser("qsf", help="QSF 1.1: 0-100 stock score with holding-period plan (separate from P6-11B)")
    qs.add_argument("action", choices=QSF_ACTIONS)
    qs.add_argument("tickers", nargs="*")
    qs.add_argument("--dry-run", action="store_true", help="Scan without writing to the ledger")
    qs.add_argument("--apply", action="store_true", help="cache-prune only: remove the files instead of listing them")
    au = sub.add_parser("automation", help="Daily job: record, tracking, backup, Telegram/macOS alerts (TERMINAL-4)")
    au.add_argument("action", choices=["status", "run", "install", "uninstall", "test-notify", "telegram-chat"], nargs="?", default="status")
    au.add_argument("--resend", action="store_true", help="Send the summary again even if unchanged")
    tm = sub.add_parser("terminal", help="Personal terminal: local web app on 127.0.0.1 (TERMINAL-1, read-only)")
    tm.add_argument("--port", type=int, default=8765)
    tm.add_argument("--open", action="store_true", help="Open the terminal in the default browser")
    ta = sub.add_parser("terminal-agent", help="launchd agent that starts the terminal at login and restarts it when it stops")
    ta.add_argument("action", choices=["status", "install", "uninstall"], nargs="?", default="status")
    sub.add_parser("migrate-storage", help="Additive storage layout v2 (idempotent; backs up tracking/ first)")
    s = sub.add_parser("scan", help="Automated Market Scan of the current S&P 500")
    s.add_argument("--capital", default=None,
                   help="REQUIRED unless QPP_CAPITAL is set: capital in USD used for position sizing, e.g. 50000")
    s.add_argument("--limit", type=int, default=None, help="Evaluate only the first N constituents (bounded validation)")
    s.add_argument("--open", action="store_true", help="Open the HTML report when done (macOS)")
    s.add_argument("--research", action="store_true", help=argparse.SUPPRESS)  # legacy flag from main.py; ignored
    e = sub.add_parser("evaluate", help="Direct Ticker Evaluation")
    e.add_argument("tickers", nargs="+")
    e.add_argument("--capital", default=None, help="REQUIRED unless QPP_CAPITAL is set (USD)")
    e.add_argument("--comparison-limit", type=int, default=None,
                   help="Bound the comparison universe (testing only; changes the cross-section)")
    e.add_argument("--open", action="store_true")
    st = sub.add_parser("status", help="Show a recorded run (default latest)")
    st.add_argument("run_id", nargs="?")
    d = sub.add_parser("doctor", help="Environment / provider self-check")
    d.add_argument("--network", action="store_true", help="Also check provider reachability")
    sub.add_parser("track", help="Alias: tracking update + tracking report")
    tr = sub.add_parser("tracking", help="Prospective paper tracking (P6-20)")
    tsub = tr.add_subparsers(dest="action")
    tsub.add_parser("status", help="Ledger contents, cohorts and latest update")
    tu = tsub.add_parser("update", help="Fetch completed daily bars and recompute outcomes (safe to rerun)")
    tu.add_argument("--offline", action="store_true", help="Reuse the current snapshot only; never download")
    trp = tsub.add_parser("report", help="Write tracking/reports/latest.md and latest.html")
    trp.add_argument("--open", action="store_true")
    te = tsub.add_parser("exclusions", help="List exclusions, or append one (never deletes records)")
    te.add_argument("--add", metavar="RUN_ID")
    te.add_argument("--category", choices=["PRE_FIX", "DATA_INVALID"], default="DATA_INVALID")
    te.add_argument("--reason")
    tsub.add_parser("verify", help="Hash chains, artifact integrity, reconstruction and replay")
    tre = tsub.add_parser("replay", help="Recompute an update from its stored price snapshot")
    tre.add_argument("update_id", nargs="?")
    return p


def main(argv=None) -> int:
    os.chdir(PROJECT_ROOT)  # relative cache/report paths are project-relative (at run time, not import time)
    args = build_parser().parse_args(argv)
    if args.command == "dashboard":
        from markets import dashboard
        out = dashboard.write()
        print(f"Dashboard: {out}")
        if args.open and sys.platform == "darwin":
            os.system(f"open '{out}'")
        return 0
    if args.command == "terminal":
        return cmd_terminal(args)
    if args.command == "terminal-agent":
        return cmd_terminal_agent(args)
    if args.command == "lab":
        return cmd_lab(args)
    if args.command == "automation":
        return cmd_automation(args)
    if args.command == "qsf":
        return cmd_qsf(args)
    if args.command == "news":
        from terminal import news
        res = news.record(PROJECT_ROOT, args.market)
        print(json.dumps(res, ensure_ascii=False))
        return {"OK": 0, "NO_UNIVERSE": 3}.get(res["status"], 1)
    if args.command == "migrate-storage":
        from markets import storage
        print(json.dumps(storage.migrate(PROJECT_ROOT), indent=1, default=str))
        return 0
    if args.market == "KR" and args.command:
        from markets.kr import cli as kr_cli
        return kr_cli.dispatch(args)
    if args.command in ("scan", "evaluate"):
        try:
            args.capital, args.capital_source = runtime_config.resolve_capital(args.capital)
        except runtime_config.CapitalNotConfigured as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    if getattr(args, "research", False):
        print("Note: --research is ignored; the canonical live route never uses research engines.")
    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "evaluate":
        return cmd_evaluate(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "track":
        return cmd_track(args)
    if args.command == "tracking":
        return cmd_tracking(args)
    return interactive()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Partial diagnostics are kept in the run directory (see `python app.py status`).")
        sys.exit(130)
