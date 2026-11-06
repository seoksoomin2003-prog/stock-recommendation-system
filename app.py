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
                    "(see README 'Project location').")
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


def cmd_qsf(args) -> int:
    """QSF 1.1 scoring (separate from the frozen P6-11B model; no orders are ever placed)."""
    if args.action in ("insider-prepare", "insider-develop", "insider-test"):
        from terminal.qsf import research_insider
        res = {"insider-prepare": research_insider.prepare, "insider-develop": research_insider.develop, "insider-test": research_insider.test_once}[args.action](PROJECT_ROOT)
        print(json.dumps({k: v for k, v in res.items() if k != "strategies"}, ensure_ascii=False, default=str))
        return 0
    if args.action in ("swing-develop", "swing-test"):
        from terminal.qsf import research_swing
        res = research_swing.develop(PROJECT_ROOT) if args.action == "swing-develop" else research_swing.test_once(PROJECT_ROOT)
        print(json.dumps({"status": res["status"], "report": str(research_swing.DEV_REPORT if args.action == "swing-develop" else research_swing.TEST_REPORT)}, ensure_ascii=False))
        return 0
    if args.action in ("research-develop", "research-test"):
        from terminal.qsf import research_score
        res = research_score.develop(PROJECT_ROOT) if args.action == "research-develop" else research_score.test_once(PROJECT_ROOT)
        print(json.dumps(res["strategies"], ensure_ascii=False, indent=1, default=str))
        return 0
    if args.action in ("oos-prepare", "oos-score", "oos-test"):
        from terminal.qsf import validate_oos
        res = {"oos-prepare": validate_oos.prepare, "oos-score": validate_oos.score, "oos-test": validate_oos.test_once}[args.action](PROJECT_ROOT)
        print(json.dumps(res.get("primary", res), ensure_ascii=False, indent=1, default=str))
        return 0
    if args.action in ("open-prepare", "open-run"):
        from terminal.qsf import validate_open
        res = validate_open.prepare(PROJECT_ROOT) if args.action == "open-prepare" else validate_open.run(PROJECT_ROOT)
        print(json.dumps(res.get("primary", res), ensure_ascii=False, indent=1, default=str))
        return 0
    if args.action in ("pit-prepare", "pit-run"):
        from terminal.qsf import validate_pit
        res = validate_pit.prepare(PROJECT_ROOT) if args.action == "pit-prepare" else validate_pit.run(PROJECT_ROOT)
        print(json.dumps(res.get("primary", res), ensure_ascii=False, indent=1, default=str))
        return 0
    if args.action in ("history-prepare", "history-run"):
        from terminal.qsf import validate
        res = validate.prepare(PROJECT_ROOT) if args.action == "history-prepare" else validate.run(PROJECT_ROOT)
        print(json.dumps(res.get("primary", res), ensure_ascii=False, indent=1, default=str))
        return 0
    from terminal.qsf.service import QSF
    q = QSF(PROJECT_ROOT)
    market = args.market
    if args.action == "scan":
        res = q.scan(market, tickers=args.tickers or None, record=not args.dry_run, progress=lambda st, d, t: print(f"  {st} {d}/{t}", flush=True))
        print(json.dumps({k: v for k, v in res.items() if k != "rows"} | {"errors": len(res["errors"])}, ensure_ascii=False, indent=1, default=str))
        return 0 if res["status"] == "REAL" else 3 if res["status"] == "DATA_NOT_READY" else 2
    if args.action == "validate":
        print(json.dumps(q.validation(), ensure_ascii=False, indent=1, default=str))
        return 0
    if args.action == "verify":
        res = q.ledger.verify()
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if res["status"] == "OK" else 2
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


def cmd_terminal(args) -> int:
    from terminal.server import HOST, serve
    try:
        httpd = serve(port=args.port, base_dir=PROJECT_ROOT)
    except OSError as exc:
        print(f"터미널 서버를 시작할 수 없습니다 (포트 {args.port}): {exc.strerror}. --port 로 다른 포트를 지정하세요.")
        return 2
    url = f"http://{HOST}:{args.port}/"
    print(f"퀀트 터미널: {url}  (이 Mac에서만 접속 가능 · 종료: Ctrl+C)")
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
    qs = sub.add_parser("qsf", help="QSF 1.1: 0-100 stock score with holding-period plan (separate from P6-11B)")
    qs.add_argument("action", choices=["evaluate", "scan", "validate", "verify", "history-prepare", "history-run", "pit-prepare", "pit-run", "open-prepare", "open-run", "oos-prepare", "oos-score", "oos-test", "research-develop", "research-test", "swing-develop", "swing-test", "insider-prepare", "insider-develop", "insider-test"])
    qs.add_argument("tickers", nargs="*")
    qs.add_argument("--dry-run", action="store_true", help="Scan without writing to the ledger")
    au = sub.add_parser("automation", help="Daily job: record, tracking, backup, Telegram/macOS alerts (TERMINAL-4)")
    au.add_argument("action", choices=["status", "run", "install", "uninstall", "test-notify", "telegram-chat"], nargs="?", default="status")
    au.add_argument("--resend", action="store_true", help="Send the summary again even if unchanged")
    tm = sub.add_parser("terminal", help="Personal terminal: local web app on 127.0.0.1 (TERMINAL-1, read-only)")
    tm.add_argument("--port", type=int, default=8765)
    tm.add_argument("--open", action="store_true", help="Open the terminal in the default browser")
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
    if args.command == "lab":
        return cmd_lab(args)
    if args.command == "automation":
        return cmd_automation(args)
    if args.command == "qsf":
        return cmd_qsf(args)
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
