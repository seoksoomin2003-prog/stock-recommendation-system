import pandas as pd
import numpy as np
from typing import Dict, Union
from utils.logger import setup_logger

logger = setup_logger("FactorEngine")

class FactorEngine:
    """
    팩터 계산 및 정규화 엔진
    주요 팩터: Momentum, Value, Quality, Low-Vol
    """
    
    @staticmethod
    def calculate_momentum(prices: pd.DataFrame) -> pd.Series:
        """
        12개월 수익률 - 최근 1개월 수익률 (12-1 Momentum)
        - [Bias Prevention] t-1 시점 이전의 데이터를 사용하도록 보장
        """
        # 월간 데이터로 변환 (마지막 영업일 기준)
        monthly_prices = prices.resample('ME').last()
        
        if len(monthly_prices) < 14:
            # Insufficient history -> Momentum is UNAVAILABLE
            momentum_series = pd.Series(np.nan, index=prices.columns)
            momentum_series.attrs['status'] = 'UNAVAILABLE'
            return momentum_series
            
        # 12개월 전 대비 현재 수익률
        ret_12m = monthly_prices.pct_change(12)
        # 1개월 전 대비 현재 수익률
        ret_1m = monthly_prices.pct_change(1)
        
        # [Strict Lag] 1개 월(Period)을 지연시켜 신호 생성 시점의 미래 정보를 차단
        momentum_series = (ret_12m - ret_1m).shift(1)
        
        # 가장 최근 유효한 신호 반환
        result = momentum_series.iloc[-1]
        result.attrs['status'] = 'REAL'
        return result

    @classmethod
    def calculate_value(cls, financial_data: pd.DataFrame) -> pd.Series:
        """
        Value Factor: PER, PBR 역수 기반
        - [Caution] financial_data는 반드시 Point-in-Time(공시일 기준) 데이터여야 함
        """
        if financial_data is None or financial_data.empty:
            return pd.Series(dtype=float)
        per_inv = 1 / (financial_data['per'].replace(0, np.nan))
        pbr_inv = 1 / (financial_data['pbr'].replace(0, np.nan))
        
        norm_per = cls.normalize(per_inv.fillna(per_inv.median()))
        norm_pbr = cls.normalize(pbr_inv.fillna(pbr_inv.median()))
        
        return norm_per + norm_pbr

    @classmethod
    def calculate_quality(cls, financial_data: pd.DataFrame) -> pd.Series:
        """
        Quality Factor: ROE, Profit Margin
        - [Caution] 실적 발표 지연(Reporting Lag)이 반영된 데이터 권장
        """
        if financial_data is None or financial_data.empty:
            return pd.Series(dtype=float)
        roe = financial_data['roe']
        margin = financial_data['profitMargin']
        
        norm_roe = cls.normalize(roe.fillna(roe.median()))
        norm_margin = cls.normalize(margin.fillna(margin.median()))
        
        return norm_roe + norm_margin

    @staticmethod
    def calculate_volatility(prices: pd.DataFrame, window: int = 22) -> pd.Series:
        """
        Low Volatility: 과거 변동성 (낮을수록 좋음)
        - [Bias Prevention] Trade Day(T)의 가격이 변동성 산출에 포함되지 않도록 지연 처리
        """
        returns = prices.pct_change()
        # [Strict Lag] 롤링 변동성 계산 후 1일 지연(.shift(1))
        vol_series = (returns.rolling(window=window).std() * np.sqrt(252)).shift(1)
        
        # T-1 시점까지의 데이터를 기반으로 한 최신 변동성 반환
        return vol_series.iloc[-1]

    @staticmethod
    def normalize(series: pd.Series, method: str = 'robust', epsilon: float = 1e-6) -> pd.Series:
        """
        팩터 정규화 (Robust Scaler vs Standard Z-score)
        """
        if series.empty:
            return series
        if series.isna().all():
            return series
            
        if method == 'robust':
            median = series.median()
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            
            # IQR이 0이거나 너무 작을 경우 STD로 폴백
            if iqr < epsilon:
                std = series.std()
                if std < epsilon or np.isnan(std): return pd.Series(0.0, index=series.index) # 신호 없음
                return (series - series.mean()) / (std + epsilon)
                
            return (series - median) / (iqr + epsilon)

        elif method == 'z-score':
            std = series.std()
            if std < epsilon or np.isnan(std): return pd.Series(0.0, index=series.index)
            return (series - series.mean()) / (std + epsilon)
            
        elif method == 'min-max':
            diff = series.max() - series.min()
            if diff < epsilon or np.isnan(diff): return pd.Series(0.0, index=series.index)
            return (series - series.min()) / (diff + epsilon)
        else:
            raise ValueError(f"Unknown normalization method: {method}")

    def get_factor_matrix(self, prices: pd.DataFrame, financial_data: pd.DataFrame) -> pd.DataFrame:
        """
        모든 팩터를 계산하여 정규화된 매트릭스 반환.

        Candidate-level provider missingness is preserved as NaN.  ScoringEngine
        is responsible for explicit weight renormalisation among observed
        factors; filling with a cross-sectional median would fabricate an
        observation for this security.
        """
        # 1. 원본 팩터 계산
        mom = self.calculate_momentum(prices)
        val = self.calculate_value(financial_data)
        qual = self.calculate_quality(financial_data)
        vol = self.calculate_volatility(prices)
        
        # 2. 팩터별 데이터 병합 및 정규화
        raw_df = pd.DataFrame({
            'momentum': mom,
            'value': val,
            'quality': qual,
            'low_volatility': -vol # 낮을수록 좋음
        })
        
        # 3. Robust 정규화 및 결측치 처리 (Median Fill)
        norm_df = pd.DataFrame()
        for col in raw_df.columns:
            # 개별 정규화 수행
            normalized = self.normalize(raw_df[col], method='robust')
            
            # If the entire column is NaN, preserve it to allow dynamic weight renormalization
            if raw_df[col].isna().all():
                norm_df[col] = pd.Series(np.nan, index=raw_df.index)
            else:
                norm_df[col] = normalized
            
            # 팩터 변동성 로깅 (신호 존재 여부 확인용)
            variance = norm_df[col].var()
            logger.info(f"Factor Diagnostics: {col:15} | Variance: {variance:.4f} | Coverage: {1 - raw_df[col].isna().mean():.1%}")
            
            if not np.isnan(variance) and variance < 1e-4:
                logger.warning(f"Low variance detected in factor '{col}'. Signal may be dying.")

        return norm_df
