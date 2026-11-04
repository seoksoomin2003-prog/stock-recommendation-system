import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from utils.config import MACRO_ADJUSTMENT_WEIGHTS, SECTOR_MACRO_BETA
from utils.logger import setup_logger

logger = setup_logger("CrossAssetEngine")

class CrossAssetEngine:
    """
    교차 자산(Cross-Asset) 매크로 분석 및 신호 보정 엔진
    - 매크로 지표(금리, 달러, 원자재)와 주식 간의 상관관계 분석
    - 매크로 환경에 따른 섹터/팩터별 점수 동적 조정 (Macro Overlay)
    """
    def __init__(self, 
                 weights: Dict = MACRO_ADJUSTMENT_WEIGHTS, 
                 betas: Dict = SECTOR_MACRO_BETA):
        self.weights = weights
        self.betas = betas
        # 티커별 섹터 매핑 (실제 운영 시 DB 또는 API 연동)
        self.ticker_sector_map = {
            "AAPL": "tech", "MSFT": "tech", "NVDA": "tech",
            "GOOGL": "growth", "AMZN": "growth", "TSLA": "growth",
            "XOM": "energy", "CVX": "energy",
            "JPM": "value", "BRK-B": "value"
        }
        # [NEW] 캐시 및 업데이트 주기 설정
        self._macro_cache = {}
        self._last_update_time = None
        self._update_interval = pd.Timedelta(hours=4)
        
        # 매크로 심볼 정의 (Yahoo Finance 기준)
        self.macro_symbols = {
            "yield": "^TNX",      # 미국채 10년물 수익률
            "usd": "DX-Y.NYB",    # 달러 인덱스
            "oil": "CL=F"         # WTI 원유 선물
        }

    def fetch_macro_data(self) -> Dict[str, float]:
        """
        [Real Data Implementation] 매크로 지표 실제 데이터 수집 및 캐싱
        - 4시간 간격으로 업데이트 수행
        - 데이터 부재 시 이전 캐시 또는 0.0(중립) 반환
        """
        current_time = pd.Timestamp.now()
        
        # 1. 캐시 유효성 체크
        if self._last_update_time and (current_time - self._last_update_time < self._update_interval):
            return self._macro_cache

        logger.info("Fetching fresh Macro data from Yahoo Finance...")
        import yfinance as yf
        
        new_data = {}
        try:
            # 5일치 데이터를 가 수집하여 최근 변화율 계산
            all_symbols = list(self.macro_symbols.values())
            data = yf.download(all_symbols, period="5d", interval="1d", progress=False)['Close']
            
            for key, symbol in self.macro_symbols.items():
                if symbol in data.columns:
                    series = data[symbol].dropna()
                    if len(series) >= 2:
                        # 최근 대비 이전 종가 변화율
                        pct_change = (series.iloc[-1] / series.iloc[-2]) - 1
                        new_data[key] = pct_change
                    else:
                        new_data[key] = self._macro_cache.get(key, 0.0)
                else:
                    new_data[key] = self._macro_cache.get(key, 0.0)
            
            self._macro_cache = new_data
            self._last_update_time = current_time
            logger.info(f"Macro Data Updated: {new_data}")
            
        except Exception as e:
            logger.error(f"Macro Data Fetch Error: {e}")
            # 에러 시 기존 캐시 사용 또는 중립값 반환
            return self._macro_cache if self._macro_cache else {"yield": 0, "usd": 0, "oil": 0}

        return self._macro_cache

    def calculate_macro_adjustment(self, ticker: str, macro_data: Dict[str, float]) -> float:
        """
        개별 종목에 대한 매크로 조정값 산출
        Adjustment = Sum(Macro_Change * Sector_Beta * Weight)
        """
        sector = self.ticker_sector_map.get(ticker, "neutral")
        if sector == "neutral" or sector not in self.betas:
            return 0.0
            
        adjustment = 0.0
        sector_betas = self.betas[sector]
        
        # 금리 영향
        if "yield" in macro_data and "yield" in sector_betas:
            adjustment += macro_data['yield'] * sector_betas['yield'] * self.weights['yield_impact']
            
        # 달러 영향
        if "usd" in macro_data and "usd" in sector_betas:
            adjustment += macro_data['usd'] * sector_betas['usd'] * self.weights['usd_impact']
            
        # 유가 영향
        if "oil" in macro_data and "oil" in sector_betas:
            adjustment += macro_data['oil'] * sector_betas['oil'] * self.weights['oil_impact']
            
        return adjustment

    def get_macro_adjusted_scores(self, base_scores: pd.Series) -> pd.Series:
        """
        기본 신호 점수(Base Scores)에 매크로 조정값 반영
        """
        macro_data = self.fetch_macro_data()
        adjusted_scores = base_scores.copy()
        
        for ticker in base_scores.index:
            adjustment = self.calculate_macro_adjustment(ticker, macro_data)
            adjusted_scores[ticker] += adjustment
            
            if adjustment != 0:
                logger.info(f"[{ticker}] Macro Adj: {adjustment:+.4f} (Sector: {self.ticker_sector_map.get(ticker)})")
        
        return adjusted_scores

    def analyze_asset_correlations(self, stock_returns: pd.DataFrame, macro_returns: pd.DataFrame) -> pd.DataFrame:
        """자산 그룹 간 상관관계 분석 (시각화 또는 리스크 관리용)"""
        combined = pd.concat([stock_returns, macro_returns], axis=1)
        return combined.corr()
