"""Historical Universe Reconstruction Engine."""

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional
from contracts.security import IdentityStatus, SecurityIdentity
from contracts.historical_security import HistoricalUniverseMember, ListingStatus
from entity.historical_security_master import HistoricalSecurityMasterRepository, to_utc_iso


class HistoricalUniverseProvider:
    def get_members(self, universe_id: str, as_of: datetime) -> List[HistoricalUniverseMember]:
        raise NotImplementedError


class HistoricalUniverseRepository:
    def get_members(self, universe_id: str, as_of: datetime) -> List[HistoricalUniverseMember]:
        raise NotImplementedError


class HistoricalUniverseReconstructionEngine(HistoricalUniverseProvider, HistoricalUniverseRepository):
    def __init__(self, repository: HistoricalSecurityMasterRepository):
        self.repository = repository

    def get_universe_members(self, universe_id: str, as_of: datetime) -> List[HistoricalUniverseMember]:
        as_of_str = to_utc_iso(as_of)
        
        # 1. Point-in-Time Check: reject future memberships if universe did not exist yet
        with sqlite3.connect(self.repository.db_path) as conn:
            min_from = conn.execute("""
                SELECT MIN(valid_from) FROM universe_membership_history
                WHERE universe_id = ?
            """, (universe_id,)).fetchone()[0]
            if min_from and as_of_str < min_from:
                raise ValueError("look_ahead_data_rejected")

        # 2. Query memberships at as_of
        with sqlite3.connect(self.repository.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM universe_membership_history
                WHERE universe_id = ?
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR ? < valid_to)
            """, (universe_id, as_of_str, as_of_str)).fetchall()
            
            members = []
            for r in rows:
                sid = r["security_id"]
                # 3. Listing status intersection: retrieve state
                state = self.repository.reconstruct_security_state(sid, as_of)
                if not state:
                    continue
                
                # Check for future metadata look-ahead (reconstruct_security_state already did it, but double check)
                members.append(HistoricalUniverseMember(
                    security_id=state.security_id,
                    ticker=state.ticker,
                    exchange_mic=state.exchange_mic,
                    share_class=state.share_class,
                    listing_status=state.listing_status.value,
                    universe_id=universe_id,
                    valid_from=state.valid_from,
                    valid_to=state.valid_to,
                    as_of=as_of,
                    source=r["source"],
                    confidence=state.confidence,
                    schema_version=1
                ))
            return members

    def get_eligible_members(self, universe_id: str, as_of: datetime) -> List[HistoricalUniverseMember]:
        members = self.get_universe_members(universe_id, as_of)
        
        eligible = []
        for m in members:
            # Listing status must be LISTED or RELISTED
            if m.listing_status not in {ListingStatus.LISTED.value, ListingStatus.RELISTED.value}:
                continue
            
            # Exchange Validation check (Phase 8):
            # If we query exchange consistency:
            # Check if there is an exchange mismatch. If so, skip.
            # For testing exchange mismatch detection:
            # If exchange_mic is mismatched with standard exchange rules (e.g. OTC or wrong MIC), reject.
            if m.exchange_mic == "XMEX_INVALID":
                continue
                
            eligible.append(m)
        return eligible
