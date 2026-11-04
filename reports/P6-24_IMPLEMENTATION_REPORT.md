# P6-24 Implementation Report: Unified Application

Date: 2026-11-04 · Status: **IMPLEMENTED**. The CLI remains the application: it is local, has no server, and runs no web service.

| Capability | Command | Notes |
|---|---|---|
| Market selector | `python app.py --market {US,KR} …` | default US. Every pre-existing command and its exit codes are unchanged (tested). |
| KR scan | `--market KR scan --capital <KRW> [--limit N]` | KRW capital from `--capital` or `QPP_CAPITAL_KRW`; refuses to reuse the USD `QPP_CAPITAL` (tested) |
| KR direct evaluation | `--market KR evaluate CODE …` | verdicts per `KR_MODEL_SPECIFICATION.md` §4 |
| KR history / status | `--market KR status [RUN_ID]` | `runs/KR/` |
| KR tracking | `--market KR tracking status\|update\|report\|verify`, `--market KR track` | separate ledger |
| Unified dashboard | `python app.py dashboard [--open]` | static `tracking/dashboard.html`: US and KR tabs; per market, the config and model version, status badge (FROZEN / EXPERIMENTAL), currency, tracking summary and recent runs; light and dark themes; read-only, nothing aggregated across markets |
| Storage migration | `python app.py migrate-storage` | idempotent (`ALREADY_CURRENT` on the live tree) |
| Reports | per-run `report.md` (US also `.html`); `tracking/reports/latest.html` (US); `tracking/kr/reports/latest.html` (KR) | |

`README.md` has been updated with the KR section, the variables and the paths. `.env.example` has three new empty placeholders: `QPP_CAPITAL_KRW`, `OPENDART_API_KEY` and `KRX_API_KEY`.

Live check:

- `app.py dashboard` wrote the page with US (14 recent runs listed; ledger with 6 runs and 60 observations) and KR (3 runs listed, 1 tracked with 10 observations);
- the US `scan`, `tracking update` and `tracking verify` all worked unchanged.

Tests: `tests/test_p6_24_app.py`, 7 of 7.
