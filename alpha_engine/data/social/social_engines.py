from abc import ABC, abstractmethod
from typing import List, Dict

class SocialDataProvider(ABC):
    """
    Abstract interface for Social/News data sources.
    Separate layers for Retail and Institutional data.
    """
    @abstractmethod
    def fetch_mentions(self, ticker: str, limit: int = 20) -> List[str]:
        """
        Fetch raw text mentions (tweets, reddit posts, news snippets).
        """
        pass

class RetailSocialEngine(SocialDataProvider):
    """
    Retail Layer: Focuses on Twitter(X) and Reddit.
    """
    def fetch_mentions(self, ticker: str, limit: int = 20) -> List[str]:
        # Simulation of retail buzz from X and Reddit
        return [
            f"{ticker} is definitely going to moon! 🚀 #stocks",
            f"Why is everyone talking about {ticker} today?",
            f"Reddit DD: {ticker} has massive upside."
        ]

class InstitutionalSocialEngine(SocialDataProvider):
    """
    Institutional Layer: Focuses on Bloomberg and Refinitiv.
    Designed for higher-fidelity professionals signals.
    """
    def fetch_mentions(self, ticker: str, limit: int = 20) -> List[str]:
        # Simulation of institutional news flow
        return [
            f"BREAKING: {ticker} reports higher than expected Q4 earnings.",
            f"Analyst Note: Upgrade {ticker} to BUY based on strong margins.",
            f"Bloomberg: {ticker} in talks for potential M&A."
        ]
