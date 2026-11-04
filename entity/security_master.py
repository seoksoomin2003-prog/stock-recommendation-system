"""Additive SQLite security-master adapter with legacy table compatibility."""

import os
import shutil
import sqlite3
import difflib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid5, NAMESPACE_URL

from contracts.security import IdentityStatus, SecurityIdentity


class SecurityMaster:
    def __init__(self, db_path: str = "data/tickers.db"):
        self.db_path = db_path

    def migrate_additively(self) -> None:
        """Create only new tables; callers may back up before their first migration."""
        db = Path(self.db_path)
        if not db.exists():
            raise FileNotFoundError(self.db_path)
        backup = db.with_suffix(db.suffix + ".pre_security_master.bak")
        if not backup.exists():
            shutil.copy2(db, backup)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS securities (
                    security_id TEXT PRIMARY KEY, ticker TEXT NOT NULL,
                    company_name TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'EQUITY',
                    share_class TEXT, exchange TEXT, exchange_mic TEXT, country TEXT,
                    currency TEXT, sector TEXT, industry TEXT, cik TEXT, isin TEXT, figi TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(ticker, exchange_mic, share_class)
                );
                CREATE TABLE IF NOT EXISTS security_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, security_id TEXT NOT NULL,
                    alias TEXT NOT NULL, alias_type TEXT NOT NULL DEFAULT 'alias', locale TEXT,
                    source TEXT, confidence REAL NOT NULL DEFAULT 1.0,
                    FOREIGN KEY(security_id) REFERENCES securities(security_id)
                );
                CREATE INDEX IF NOT EXISTS idx_security_aliases_alias ON security_aliases(alias);
                CREATE TABLE IF NOT EXISTS exchanges (
                    exchange_mic TEXT PRIMARY KEY, exchange TEXT NOT NULL, country TEXT, currency TEXT
                );
                CREATE TABLE IF NOT EXISTS provider_identifiers (
                    security_id TEXT NOT NULL, provider TEXT NOT NULL, identifier TEXT NOT NULL,
                    identifier_type TEXT NOT NULL, PRIMARY KEY(security_id, provider, identifier_type),
                    FOREIGN KEY(security_id) REFERENCES securities(security_id)
                );
                CREATE TABLE IF NOT EXISTS ticker_history (
                    security_id TEXT NOT NULL, ticker TEXT NOT NULL, exchange_mic TEXT,
                    valid_from TEXT, valid_to TEXT, PRIMARY KEY(security_id, ticker, valid_from),
                    FOREIGN KEY(security_id) REFERENCES securities(security_id)
                );
                CREATE TABLE IF NOT EXISTS security_resolution_audit (
                    request_id TEXT, query TEXT, security_id TEXT, status TEXT NOT NULL,
                    confidence REAL NOT NULL, resolved_at TEXT NOT NULL
                );
            """)
            legacy = conn.execute("SELECT ticker, company_name, exchange, country, sector FROM tickers").fetchall()
            now = datetime.now(timezone.utc).isoformat()
            for ticker, name, exchange, country, sector in legacy:
                sid = str(uuid5(NAMESPACE_URL, f"legacy-security:{ticker.upper()}"))
                conn.execute("""INSERT OR IGNORE INTO securities
                    (security_id,ticker,company_name,exchange,country,sector,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?)""", (sid, ticker.upper(), name, exchange, country, sector, now, now))
                aliases = conn.execute("""SELECT a.alias, a.source, a.confidence FROM aliases a
                    JOIN tickers t ON t.id=a.ticker_id WHERE t.ticker=?""", (ticker,)).fetchall()
                for alias, source, confidence in aliases:
                    conn.execute("INSERT INTO security_aliases(security_id,alias,source,confidence) VALUES(?,?,?,?)",
                                 (sid, alias.lower().strip(), source, confidence))

    def candidates(self, normalized_query: str) -> List[SecurityIdentity]:
        query = normalized_query.lower().strip()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""SELECT DISTINCT s.* FROM securities s LEFT JOIN security_aliases a
                ON a.security_id=s.security_id WHERE lower(s.ticker)=? OR lower(s.company_name)=? OR a.alias=?""",
                (query, query, query)).fetchall()
        return [self._identity(row, 1.0) for row in rows]

    def fuzzy_candidates(self, normalized_query: str, cutoff: float = 0.84) -> List[SecurityIdentity]:
        """Return only high-confidence alias candidates; never force a multi-match result."""
        query = normalized_query.lower().strip()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""SELECT s.*, a.alias FROM securities s
                JOIN security_aliases a ON a.security_id=s.security_id""").fetchall()
        best = {}
        for row in rows:
            score = difflib.SequenceMatcher(None, query, row["alias"].lower()).ratio()
            if score >= cutoff and score > best.get(row["security_id"], (0, None))[0]:
                best[row["security_id"]] = (score, row)
        return [self._identity(row, score) for score, row in best.values()]

    def add_alias(self, security_id: str, alias: str, alias_type: str = "alias", locale: Optional[str] = None,
                  source: str = "manual", confidence: float = 1.0) -> None:
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute("SELECT 1 FROM security_aliases WHERE security_id=? AND alias=?",
                                    (security_id, alias.lower().strip())).fetchone()
            if not existing:
                conn.execute("""INSERT INTO security_aliases
                    (security_id,alias,alias_type,locale,source,confidence) VALUES(?,?,?,?,?,?)""",
                    (security_id, alias.lower().strip(), alias_type, locale, source, confidence))

    def update_cik(self, security_id: str, cik: str, provider: str = "sec") -> None:
        """Persist only a validated, numeric CIK through the security-master boundary."""
        normalized = str(cik).strip().zfill(10)
        if not normalized.isdigit():
            raise ValueError("invalid_cik")
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT cik FROM securities WHERE security_id=?", (security_id,)).fetchone()
            if row is None:
                raise KeyError(security_id)
            if row[0] and row[0].zfill(10) != normalized:
                raise ValueError("cik_conflict")
            conn.execute("UPDATE securities SET cik=?, updated_at=? WHERE security_id=?",
                         (normalized, datetime.now(timezone.utc).isoformat(), security_id))
            conn.execute("""INSERT OR REPLACE INTO provider_identifiers
                         (security_id,provider,identifier,identifier_type) VALUES(?,?,?,?)""",
                         (security_id, provider, normalized, "CIK"))

    def hydrate_ciks_from_sec_cache(self, cache_dir: str = "data/sec_cache") -> int:
        """Populate existing local security records from cached official SEC submissions and company tickers map."""
        updated = 0
        
        # 1. First load from company_tickers.json to cover all symbols
        tickers_json = Path(cache_dir) / "company_tickers.json"
        if tickers_json.exists():
            try:
                data = json.loads(tickers_json.read_text())
                for item in data.values():
                    ticker = str(item.get("ticker", "")).upper()
                    cik = item.get("cik_str")
                    if ticker and cik:
                        candidates = self.candidates(ticker)
                        if len(candidates) == 1:
                            try:
                                self.update_cik(candidates[0].security_id, str(cik))
                                updated += 1
                            except (ValueError, KeyError):
                                pass
            except Exception:
                pass

        # 2. Re-hydrate/override from individual submissions if present
        for path in Path(cache_dir).glob("*_submissions.json"):
            try:
                payload = json.loads(path.read_text())
                ticker = (payload.get("tickers") or [path.name.split("_")[0]])[0].upper()
                cik = payload.get("cik")
                candidates = self.candidates(ticker)
                if cik and len(candidates) == 1:
                    try:
                        self.update_cik(candidates[0].security_id, str(cik))
                        updated += 1
                    except (ValueError, KeyError):
                        pass
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return updated

    @staticmethod
    def _identity(row: sqlite3.Row, confidence: float) -> SecurityIdentity:
        return SecurityIdentity(
            security_id=row["security_id"], ticker=row["ticker"], company_name=row["company_name"],
            asset_type=row["asset_type"], share_class=row["share_class"], exchange=row["exchange"],
            exchange_mic=row["exchange_mic"], country=row["country"], currency=row["currency"],
            sector=row["sector"], industry=row["industry"], cik=row["cik"], isin=row["isin"], figi=row["figi"],
            identity_status=IdentityStatus.RESOLVED, resolution_confidence=confidence,
        )
