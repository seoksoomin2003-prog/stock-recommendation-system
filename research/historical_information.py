"""P5 composition boundary: historical identity/universe + PIT data, not P5-6."""

from datetime import datetime
from typing import Optional

from entity.historical_data_repository import HistoricalDataRepository
from entity.historical_security_master import HistoricalSecurityMasterRepository
from research.universe_engine import HistoricalUniverseReconstructionEngine


class HistoricalInformationService:
    """Composes existing P5-2/P5-3 state with P5-4/P5-5 data by security_id."""

    def __init__(self, data_repository: HistoricalDataRepository,
                 security_master: HistoricalSecurityMasterRepository,
                 universe_engine: Optional[HistoricalUniverseReconstructionEngine] = None):
        self.data_repository = data_repository
        self.security_master = security_master
        self.universe_engine = universe_engine or HistoricalUniverseReconstructionEngine(security_master)

    def get_information_set(self, security_id: str, as_of: datetime, universe_id: Optional[str] = None):
        state = self.security_master.reconstruct_security_state(security_id, as_of)
        universe_state = None
        if universe_id:
            universe_state = next((m for m in self.universe_engine.get_universe_members(universe_id, as_of)
                                   if m.security_id == security_id), None)
        return self.data_repository.information_set(security_id, as_of,
                                                    {"security": state, "universe": universe_state})
