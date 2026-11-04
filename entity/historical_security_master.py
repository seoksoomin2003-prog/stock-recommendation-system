"""Historical Security Master Repository."""

import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from contracts.security import IdentityStatus, SecurityIdentity
from contracts.historical_security import HistoricalSecurityState, ListingStatus, SecurityLifecycleEvent


def to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def from_utc_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


class HistoricalSecurityMasterRepository:
    def __init__(self, db_path: str = "data/historical_security.db", *, allow_synthetic: bool = False):
        self.db_path = db_path
        self.allow_synthetic = allow_synthetic
        self._init_db()

    def _reject_synthetic(self, source: str) -> None:
        if not self.allow_synthetic:
            s_upper = (source or "").upper()
            if any(marker in s_upper for marker in ("SYNTHETIC", "TEST FIXTURE", "TEST_FIXTURE", "MOCK", "GENERATED")):
                raise ValueError("synthetic_records_forbidden_in_production_repository")

    def _validate_provenance(self, security_id: str, provider: str, source: str, timestamp = None) -> None:
        if not security_id or not security_id.strip():
            raise ValueError("historical_security_id_required")
        if not provider or not provider.strip() or not source or not source.strip():
            raise ValueError("historical_provenance_incomplete")
        if not self.allow_synthetic and timestamp is None:
            raise ValueError("historical_timestamp_provenance_missing")

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS historical_security_states (
                    security_id TEXT NOT NULL,
                    ticker TEXT,
                    company_name TEXT NOT NULL,
                    share_class TEXT,
                    exchange TEXT,
                    exchange_mic TEXT,
                    country TEXT,
                    currency TEXT,
                    listing_status TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    source TEXT,
                    confidence REAL,
                    schema_version TEXT DEFAULT '1.0'
                );
                CREATE INDEX IF NOT EXISTS idx_hist_sec_state_lookup 
                    ON historical_security_states(security_id, valid_from, valid_to);
                CREATE INDEX IF NOT EXISTS idx_hist_sec_ticker_lookup 
                    ON historical_security_states(ticker, valid_from, valid_to);

                CREATE TABLE IF NOT EXISTS provider_identifiers_history (
                    security_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    identifier TEXT NOT NULL,
                    identifier_type TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    source TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_hist_provider_lookup 
                    ON provider_identifiers_history(security_id, provider, valid_from, valid_to);

                CREATE TABLE IF NOT EXISTS lifecycle_events (
                    event_id TEXT PRIMARY KEY,
                    security_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    effective_at TEXT NOT NULL,
                    announced_at TEXT,
                    source TEXT,
                    source_record_id TEXT,
                    metadata_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_hist_events_lookup 
                    ON lifecycle_events(security_id, effective_at);

                CREATE TABLE IF NOT EXISTS corporate_actions_history (
                    action_id TEXT PRIMARY KEY,
                    parent_security_id TEXT NOT NULL,
                    child_security_id TEXT,
                    action_type TEXT NOT NULL,
                    effective_at TEXT NOT NULL,
                    announced_at TEXT,
                    details_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_hist_actions_lookup 
                    ON corporate_actions_history(parent_security_id, effective_at);

                CREATE TABLE IF NOT EXISTS universe_membership_history (
                    universe_id TEXT NOT NULL,
                    security_id TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    source TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_hist_universe_lookup 
                    ON universe_membership_history(universe_id, valid_from, valid_to);
            """)

    def add_historical_security_state(self, state: HistoricalSecurityState) -> None:
        self._reject_synthetic(state.source)
        provider = list(state.provider_ids.keys())[0] if state.provider_ids else "unknown"
        self._validate_provenance(state.security_id, provider, state.source, state.valid_from)
        start_str = to_utc_iso(state.valid_from) if state.valid_from else "1900-01-01T00:00:00Z"
        end_str = to_utc_iso(state.valid_to) if state.valid_to else "9999-12-31T23:59:59Z"

        # Validate intervals: overlap check for same security_id
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT valid_from, valid_to FROM historical_security_states
                WHERE security_id = ?
            """, (state.security_id,)).fetchall()
            for r in rows:
                r_start = r["valid_from"]
                r_end = r["valid_to"] or "9999-12-31T23:59:59Z"
                if max(start_str, r_start) < min(end_str, r_end):
                    raise ValueError("overlapping_intervals")

            # Data Quality checks: Listing before delisting etc.
            if state.listing_status == ListingStatus.DELISTED:
                # Delisting date check
                pass

            conn.execute("""
                INSERT INTO historical_security_states (
                    security_id, ticker, company_name, share_class, exchange, exchange_mic,
                    country, currency, listing_status, valid_from, valid_to, source,
                    confidence, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                state.security_id, state.ticker, state.company_name, state.share_class,
                state.exchange, state.exchange_mic, state.country, state.currency,
                state.listing_status.value, start_str, state.valid_to and to_utc_iso(state.valid_to),
                state.source, state.confidence, state.schema_version
            ))

    def add_provider_identifier_history(self, security_id: str, provider: str, identifier: str,
                                         identifier_type: str, valid_from: datetime,
                                         valid_to: Optional[datetime] = None, source: str = "unknown") -> None:
        self._reject_synthetic(source)
        self._validate_provenance(security_id, provider, source, valid_from)
        start_str = to_utc_iso(valid_from)
        end_str = to_utc_iso(valid_to) if valid_to else None
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO provider_identifiers_history (
                    security_id, provider, identifier, identifier_type, valid_from, valid_to, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (security_id, provider, identifier, identifier_type, start_str, end_str, source))

    def add_lifecycle_event(self, event: SecurityLifecycleEvent) -> None:
        self._reject_synthetic(event.source)
        self._validate_provenance(event.security_id, event.source or "unknown", event.source, event.effective_at)
        eff_str = to_utc_iso(event.effective_at)
        ann_str = to_utc_iso(event.announced_at) if event.announced_at else None
        with sqlite3.connect(self.db_path) as conn:
            # Check duplicates
            existing = conn.execute("SELECT 1 FROM lifecycle_events WHERE event_id=?", (event.event_id,)).fetchone()
            if existing:
                raise ValueError("duplicate_lifecycle_event")
            conn.execute("""
                INSERT INTO lifecycle_events (
                    event_id, security_id, event_type, effective_at, announced_at, source,
                    source_record_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id, event.security_id, event.event_type, eff_str, ann_str,
                event.source, event.source_record_id, json.dumps(event.metadata)
            ))

    def add_corporate_action(self, action_id: str, parent_security_id: str,
                             child_security_id: Optional[str], action_type: str,
                             effective_at: datetime, announced_at: Optional[datetime] = None,
                             details: Optional[Dict] = None) -> None:
        eff_str = to_utc_iso(effective_at)
        ann_str = to_utc_iso(announced_at) if announced_at else None
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO corporate_actions_history (
                    action_id, parent_security_id, child_security_id, action_type,
                    effective_at, announced_at, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                action_id, parent_security_id, child_security_id, action_type,
                eff_str, ann_str, json.dumps(details or {})
            ))

    def add_universe_membership(self, universe_id: str, security_id: str,
                                valid_from: datetime, valid_to: Optional[datetime] = None,
                                source: str = "unknown") -> None:
        self._reject_synthetic(source)
        self._validate_provenance(security_id, "universe", source, valid_from)
        start_str = to_utc_iso(valid_from)
        end_str = to_utc_iso(valid_to) if valid_to else "9999-12-31T23:59:59Z"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Duplicate check
            dup = conn.execute("""
                SELECT 1 FROM universe_membership_history
                WHERE universe_id = ? AND security_id = ? AND valid_from = ?
            """, (universe_id, security_id, start_str)).fetchone()
            if dup:
                raise ValueError("duplicate_universe_membership")

            # Overlap check
            rows = conn.execute("""
                SELECT valid_from, valid_to FROM universe_membership_history
                WHERE universe_id = ? AND security_id = ?
            """, (universe_id, security_id)).fetchall()
            for r in rows:
                r_start = r["valid_from"]
                r_end = r["valid_to"] or "9999-12-31T23:59:59Z"
                if max(start_str, r_start) < min(end_str, r_end):
                    raise ValueError("overlapping_intervals")

            conn.execute("""
                INSERT INTO universe_membership_history (
                    universe_id, security_id, valid_from, valid_to, source
                ) VALUES (?, ?, ?, ?, ?)
            """, (universe_id, security_id, start_str, valid_to and to_utc_iso(valid_to), source))

    def _get_provider_ids(self, security_id: str, as_of_str: str) -> Dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT provider, identifier FROM provider_identifiers_history
                WHERE security_id = ?
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR ? < valid_to)
            """, (security_id, as_of_str, as_of_str)).fetchall()
            return {r["provider"]: r["identifier"] for r in rows}

    def reconstruct_security_state(self, security_id: str, as_of: datetime) -> Optional[HistoricalSecurityState]:
        as_of_str = to_utc_iso(as_of)
        
        # Check future data leakage: only throw if the security does not exist yet on as_of
        with sqlite3.connect(self.db_path) as conn:
            min_from = conn.execute("""
                SELECT MIN(valid_from) FROM historical_security_states
                WHERE security_id = ?
            """, (security_id,)).fetchone()[0]
            if min_from and as_of_str < min_from:
                raise ValueError("look_ahead_data_rejected")
                
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT * FROM historical_security_states
                WHERE security_id = ?
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR ? < valid_to)
            """, (security_id, as_of_str, as_of_str)).fetchone()
            
            if not row:
                return None
                
            prov_ids = self._get_provider_ids(security_id, as_of_str)
            return HistoricalSecurityState(
                security_id=row["security_id"],
                provider_ids=prov_ids,
                ticker=row["ticker"],
                company_name=row["company_name"],
                share_class=row["share_class"],
                exchange=row["exchange"],
                exchange_mic=row["exchange_mic"],
                country=row["country"],
                currency=row["currency"],
                listing_status=ListingStatus(row["listing_status"]),
                valid_from=from_utc_iso(row["valid_from"]),
                valid_to=from_utc_iso(row["valid_to"]),
                as_of=as_of,
                source=row["source"],
                confidence=row["confidence"],
                schema_version=row["schema_version"]
            )

    def resolve_historical_ticker(self, ticker: str, as_of: datetime) -> List[HistoricalSecurityState]:
        as_of_str = to_utc_iso(as_of)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM historical_security_states
                WHERE lower(ticker) = ?
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR ? < valid_to)
            """, (ticker.lower().strip(), as_of_str, as_of_str)).fetchall()
            
            states = []
            for row in rows:
                prov_ids = self._get_provider_ids(row["security_id"], as_of_str)
                states.append(HistoricalSecurityState(
                    security_id=row["security_id"],
                    provider_ids=prov_ids,
                    ticker=row["ticker"],
                    company_name=row["company_name"],
                    share_class=row["share_class"],
                    exchange=row["exchange"],
                    exchange_mic=row["exchange_mic"],
                    country=row["country"],
                    currency=row["currency"],
                    listing_status=ListingStatus(row["listing_status"]),
                    valid_from=from_utc_iso(row["valid_from"]),
                    valid_to=from_utc_iso(row["valid_to"]),
                    as_of=as_of,
                    source=row["source"],
                    confidence=row["confidence"],
                    schema_version=row["schema_version"]
                ))
            return states

    def get_members(self, universe_id: str, as_of: datetime) -> List[SecurityIdentity]:
        as_of_str = to_utc_iso(as_of)
        
        # Check future membership leakage
        with sqlite3.connect(self.db_path) as conn:
            min_from = conn.execute("""
                SELECT MIN(valid_from) FROM universe_membership_history
                WHERE universe_id = ?
            """, (universe_id,)).fetchone()[0]
            if min_from and as_of_str < min_from:
                raise ValueError("look_ahead_data_rejected")
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT security_id FROM universe_membership_history
                WHERE universe_id = ?
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR ? < valid_to)
            """, (universe_id, as_of_str, as_of_str)).fetchall()
            
            members = []
            for r in rows:
                sid = r["security_id"]
                state = self.reconstruct_security_state(sid, as_of)
                if state:
                    members.append(SecurityIdentity(
                        security_id=state.security_id,
                        ticker=state.ticker,
                        company_name=state.company_name,
                        share_class=state.share_class,
                        exchange=state.exchange,
                        exchange_mic=state.exchange_mic,
                        country=state.country,
                        currency=state.currency,
                        provider_ids=state.provider_ids,
                        identity_status=IdentityStatus.RESOLVED,
                        resolution_confidence=state.confidence
                    ))
            return members
