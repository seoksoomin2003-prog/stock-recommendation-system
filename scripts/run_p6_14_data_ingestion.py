import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
import requests
import argparse
from datetime import datetime, timezone
import json

from utils.logger import setup_logger
from entity.historical_security_master import HistoricalSecurityMasterRepository
from contracts.historical_security import HistoricalSecurityState, ListingStatus

logger = setup_logger("IngestionEngine")

class SECDataIngestionEngine:
    def __init__(self):
        self.headers = {"User-Agent": os.getenv("SEC_USER_AGENT", "")}
        self.repo = HistoricalSecurityMasterRepository()

    def bootstrap_security_master(self):
        """
        [P6-14] SECURITY MASTER BOOTSTRAP
        Fetches company_tickers.json and inserts it into the canonical repository.
        """
        logger.info("Starting SEC Security Master Bootstrap...")
        url = "https://www.sec.gov/files/company_tickers.json"
        
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code == 429:
                logger.error("SEC Rate Limit Exceeded (429). Backing off.")
                return
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            logger.error(f"Failed to fetch SEC tickers: {e}")
            return
            
        now = datetime.now(timezone.utc)
        count = 0
        
        for k, v in data.items():
            cik = str(v["cik_str"]).zfill(10)
            ticker = v["ticker"]
            title = v["title"]
            security_id = f"CIK{cik}"
            
            # Use 1900-01-01 as a canonical default for "available history", since SEC bootstrap doesn't provide listing dates
            state = HistoricalSecurityState(
                security_id=security_id,
                provider_ids={"sec_edgar": cik},
                ticker=ticker,
                company_name=title,
                share_class="Common",
                exchange="UNKNOWN",
                exchange_mic="UNKNOWN",
                country="US",
                currency="USD",
                listing_status=ListingStatus.LISTED, # Assuming active if currently in SEC master
                valid_from=datetime(1900, 1, 1, tzinfo=timezone.utc),
                valid_to=None,
                as_of=now,
                source="SEC_BOOTSTRAP_TICKERS",
                confidence=0.8,
                schema_version="1.0"
            )
            
            try:
                self.repo.add_historical_security_state(state)
                
                # Also store the CIK identifier history
                self.repo.add_provider_identifier_history(
                    security_id=security_id,
                    provider="sec_edgar",
                    identifier=cik,
                    identifier_type="CIK",
                    valid_from=datetime(1900, 1, 1, tzinfo=timezone.utc),
                    source="SEC_BOOTSTRAP_TICKERS"
                )
                count += 1
            except ValueError as ve:
                if "overlapping_intervals" in str(ve):
                    pass # Already ingested
                else:
                    logger.debug(f"Skipping {ticker}: {ve}")
                    
        logger.info(f"Successfully bootstrapped {count} securities from SEC.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["probe", "metadata", "incremental", "full"], required=True)
    args = parser.parse_args()
    
    engine = SECDataIngestionEngine()
    if args.mode == "metadata":
        engine.bootstrap_security_master()
    elif args.mode == "probe":
        # We will expand this to probe fundamental data
        pass
