# Git Setup Report (P6-20 addendum B)

Date: 2026-11-04 · Repository: `~/Developer/quant-stock-engine` · **Local only**: no remote, nothing pushed.

## 1. Inspection before acting

- No `.git` directory existed in the project or in any parent directory, so nothing was reinitialised.
- The Desktop original (`~/Desktop/퀀트 예측 프로그램`) was not touched.

## 2. Initialisation and baseline

| Item | Value |
|---|---|
| Command | `git init -b main` (Apple Git 2.39.5) |
| Branch | `main` |
| Baseline commit | **`1e9472f0020d6071e6b63764dcc0f3bcd09c20c5`**: "chore: establish verified baseline (P6-19 + P6-20 tracking infrastructure)" |
| Why not a pure P6-19 tree | The P6-20 tracking infrastructure was written before the addendum arrived, so a pure P6-19 working tree could not be reproduced without destroying work. The baseline therefore contains the verified P6-19 code **plus** the tested P6-20 tracking layer (full suite at that point: 806 passed, 6 skipped, 5 xfailed, 0 failed). This is stated in the commit message. |
| Author identity | the existing global git identity (user name `seoksoomin2003-prog`); not changed |
| Tracked files | 515 at baseline (2.9 MB); 516 after the A1–A6 commit |
| Remote | none (`git remote -v` is empty) |

Subsequent local commits:

| Commit | Content |
|---|---|
| `63c283d` | feat(data): P6-20 addendum A1–A6 approved data-input rules (836 passed, 0 failed) |
| next commit | docs/tracking: spec P6-20-A, this report, roadmap, tracking summary by spec version (837 passed, 0 failed) |

## 3. .gitignore review

Kept: `.env`, `.env.*` (with `!.env.example`), virtualenvs, Python caches, `runs/`, `data/*.db`,
`scratch/`, `cache.nosync`, OS files.

Added in P6-20:

| Pattern | Reason |
|---|---|
| `tracking/` | Personal prospective ledger, price snapshots and reports. User data, and append-only by design. |
| `data/*.json`, `data/**/*.json` | Provider caches (SEC ticker map, fundamentals cache, universe cache) |
| `*.sqlite`, `*.sqlite3`, `*.parquet`, `*.csv.gz` | Local data stores and snapshots |
| `reports/*_pytest_junit.xml` | Generated test output (contains local paths) |
| `*.log`, `*.tmp`, `.*.tmp-*`, `nohup.out` | Logs and atomic-write temporaries |
| `.idea/`, `*.swp` | Editor files |

`.vscode/settings.json` is tracked on purpose. It holds only workspace-relative settings and no secrets.

Verified as ignored (`git check-ignore`): `.env`, `.env.local`, `data/tickers.db`,
`data/historical_data.db`, `data/sp500_universe_cache.json`, `data/sec_cache/company_tickers.json`,
`runs/LATEST`, `tracking/ledger/observations.jsonl`, `.venv/`, `cache.nosync`, `scratch`,
`reports/P6-20_pytest_junit.xml`. No tracked path matches `.env`, `*.db`, `tracking/`, `runs/` or a
secret or key file name.

## 4. Secret scan (before staging; values not reproduced)

- Scope: all 515 files to be staged.
- Patterns: 32-hex API-key shapes; AWS access keys; GitHub tokens (`ghp_`, `github_pat_`); `sk-` keys;
  Slack tokens; PEM private keys; assignments such as `api_key=`, `secret=`, `token=`, `password=` with
  literal values; e-mail addresses; the user's own e-mail local part.
- The previously exposed NewsAPI key: **0 occurrences** in tracked files.
- `.env.example` contains only empty placeholders.
- One finding: a third-party e-mail address in an example User-Agent string (`docs/data_stability.md`),
  replaced with `<contact e-mail>` before the baseline commit.
- The `SEC_USER_AGENT` contact e-mail lives only in the user's shell profile. It is not in any tracked file.
- The same scan ran on the files staged for `63c283d`, with no findings. The only hex strings are
  SHA-256 hashes and accession-number-like test literals.

## 5. Frozen-core hashes

Each was compared with `tests/fixtures/frozen_source_sha256_p6_19.json`. At HEAD (via `git show`) and in
the working tree, they are identical after every commit:

| File | sha256 (prefix) |
|---|---|
| `core/factor_engine.py` | `d84820f82eda` |
| `core/scoring_engine.py` | `0f42f8401b26` |
| `core/ranking_engine.py` | `2b354792de5d` |
| `core/decision_engine.py` | `074f5180426e` |
| `contracts/decision.py` | `3339af551c0d` |

## 6. GitHub CLI and remote status

- `gh`: **not installed** (`command -v gh` → not found), so authentication status is not applicable.
- No GitHub repository was created, no remote was added, nothing was pushed, and no credential or token was
  requested. All of this follows addendum B5.

## 7. How to connect a private GitHub repository later (only after your explicit approval)

Nothing below has been run. When you decide to do it:

1. Install the GitHub CLI (`brew install gh`), then run `gh auth login` yourself. The browser flow keeps
   the token out of this project.
2. Create a **private** repository and connect it, e.g.
   `gh repo create quant-stock-engine --private --source . --remote origin`, or create it on github.com and
   run `git remote add origin git@github.com:<you>/quant-stock-engine.git`.
3. Before the first push, re-run the secret scan and `git status`, and check that `.env`, `tracking/`,
   `runs/` and `data/*.db` are still ignored.
4. `git push -u origin main`.

Ignored data (`tracking/`, `runs/`, caches) never leaves your machine through git. Back it up separately
(e.g. `~/Developer/qse-backups/`).
