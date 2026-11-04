import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

from data.loader import DataLoader
from utils.logger import setup_logger

logger = setup_logger("SmokeTest")

def run_smoke_test():
    loader = DataLoader()
    
    # Valid Ticker
    logger.info("Testing valid ticker AAPL...")
    prices = loader.get_price_data(["AAPL"], "2026-08-01", "2026-08-15")
    volumes = loader.get_volume_data(["AAPL"], "2026-08-01", "2026-08-15")
    assert not prices.empty, "Valid price empty"
    assert not volumes.empty, "Valid volume empty"
    
    # Invalid Ticker
    logger.info("Testing invalid ticker INVALID_XYZ...")
    prices = loader.get_price_data(["INVALID_XYZ"], "2026-08-01", "2026-08-15")
    volumes = loader.get_volume_data(["INVALID_XYZ"], "2026-08-01", "2026-08-15")
    # Due to recent changes, missing data returns dataframe with NaNs or 0s
    assert prices.isna().all().all(), "Invalid price not NaN"
    assert (volumes == 0).all().all() or volumes.isna().all().all(), "Invalid volume not empty or 0"
    
    logger.info("Live Provider Smoke Test Passed!")

if __name__ == "__main__":
    run_smoke_test()
