from typing import Dict, List, Optional
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger("MacroEngine")

class MacroEventEngine:
    """
    Data Layer: Macro Event Engine
    - Tracks market-impact events (Fed, CPI, Rates, Unemployment).
    - Signal increases sentiment weight in processing layer.
    """
    def __init__(self):
        # In production, this would fetch from an Economic Calendar API
        self.economic_calendar = [
            {"date": "2026-04-12", "event": "Fed Interest Rate Decision", "impact": 0.9, "category": "Fed"},
            {"date": "2026-04-15", "event": "CPI Data Release", "impact": 0.8, "category": "Inflation"},
        ]

    def get_macro_impact(self, date: Optional[str] = None) -> float:
        """
        Returns macro_impact score [0, 1].
        """
        today = date or pd.Timestamp.now().strftime("%Y-%m-%d")
        
        # Check for significant events today
        todays_events = [e for e in self.economic_calendar if e['date'] == today]
        
        if not todays_events:
            return 0.0
            
        # Return the highest impact event
        max_impact = max([e['impact'] for e in todays_events])
        logger.info(f"Macro event detected on {today}: Impact {max_impact}")
        return max_impact

    def is_event_detected(self, date: Optional[str] = None) -> bool:
        """Helper for triggering weight boosts."""
        return self.get_macro_impact(date) > 0.5
