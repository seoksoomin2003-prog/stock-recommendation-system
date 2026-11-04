from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class SECDataProvider(ABC):
    """
    Abstract Base Class for SEC Data Providers.
    Allows for multiple implementations (sec-api, custom EDGAR scraper, Bloomberg, etc.)
    """
    @abstractmethod
    def fetch_filings(self, ticker: str, filing_type: str = "10-K", limit: int = 5) -> List[Dict]:
        """
        Fetch a list of filings for a given ticker.
        """
        pass

    @abstractmethod
    def get_filing_content(self, filing_url: str) -> str:
        """
        Fetch the raw or cleaned text content of a specific filing.
        """
        pass

    @abstractmethod
    def fetch_insider_trades(self, ticker: str, limit: int = 10) -> List[Dict]:
        """
        Fetch Form 4 (Insider Trading) data.
        """
        pass
