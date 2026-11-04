import pandas as pd
from typing import List, Optional
import functools
from core.data_validation import DataValidation
from utils.logger import setup_logger

logger = setup_logger("AlphaUniverse")

class UniverseManager:
    """
    Input Layer: 유연한 종목 입력 및 검사 시스템
    - Ticker 리스트 고정 제거
    - 실시간 종목 추가 및 필터링
    - 캐싱 지원 (LRU or simple dict)
    """
    def __init__(self):
        self.validator = DataValidation()
        self._universe_cache = {}

    @functools.lru_cache(maxsize=128)
    def _validate_and_clean_tickers(self, tickers_tuple: tuple) -> List[str]:
        """
        내부 캐싱을 위한 튜플 기반 검증 메서드
        """
        tickers = list(tickers_tuple)
        valid_tickers = self.validator.validate_universe(tickers)
        return valid_tickers

    def get_user_universe(self, input_tickers: List[str], use_cache: bool = True) -> List[str]:
        """
        사용자 입력 기반 유니버스 생성
        - 중복 제거
        - Invalid ticker 필터링
        - 캐싱 지원
        """
        if not input_tickers:
            logger.warning("No input tickers provided. Returning empty universe.")
            return []

        # 튜플로 변환하여 LRU 캐시 활용
        tickers_tuple = tuple(sorted(list(set(input_tickers))))
        
        if use_cache and tickers_tuple in self._universe_cache:
            logger.info(f"Returning cached universe for {len(input_tickers)} inputs.")
            return self._universe_cache[tickers_tuple]

        valid_tickers = self._validate_and_clean_tickers(tickers_tuple)
        
        if use_cache:
            self._universe_cache[tickers_tuple] = valid_tickers
            
        logger.info(f"Universe processed: {len(input_tickers)} -> {len(valid_tickers)} valid tickers.")
        return valid_tickers

def get_user_universe(input_tickers: List[str]) -> List[str]:
    """
    Global helper function to get universe using high-level manager
    """
    manager = UniverseManager()
    return manager.get_user_universe(input_tickers)
