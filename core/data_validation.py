import pandas as pd
import numpy as np
from typing import List, Union, Optional, Tuple
from utils.logger import setup_logger

logger = setup_logger("DataValidation")

class DataValidation:
    """
    데이터 품질 보장 및 바이이어스 방지 모듈
    """
    def __init__(self, outlier_threshold: float = 3.0):
        self.outlier_threshold = outlier_threshold
        # [NEW] 상장/폐지 아카이브 (Survivorship Bias 방지용 메타데이터)
        # 실제 운영 시에는 외부 DB(SQL/NoSQL) 또는 전문 데이터 API 연동
        self.listing_database = {
            "AAPL": {"listed": "1980-12-12", "delisted": None},
            "MSFT": {"listed": "1986-03-13", "delisted": None},
            "GOOGL": {"listed": "2004-08-19", "delisted": None},
            "AMZN": {"listed": "1997-05-15", "delisted": None},
            "META": {"listed": "2012-05-18", "delisted": None},
            "NVDA": {"listed": "1999-01-22", "delisted": None},
            "TSLA": {"listed": "2010-06-29", "delisted": None},
            # 상장 폐지 예시 (XYZ_CORP: 2010년 상장, 2020년 폐지)
            "XYZ_CORP": {"listed": "2010-01-01", "delisted": "2020-05-20"}
        }

    def get_active_tickers(self, date: Union[str, pd.Timestamp], tickers: List[str]) -> List[str]:
        """
        [NEW] 특정 시점(Point-in-Time)에 활성화된(상장된) 티커만 필터링
        - Survivorship Bias 방지의 핵심 로직
        """
        target_date = pd.to_datetime(date)
        active_tickers = []
        
        for ticker in tickers:
            meta = self.listing_database.get(ticker)
            if not meta:
                # 데이터베이스에 없는 경우: 보수적 접근(로그만 남기고 일단 포함) 또는 제외 선택 가능
                # 여기서는 '포함'하되 누락 경고 발생
                active_tickers.append(ticker)
                continue
                
            listed_date = pd.to_datetime(meta['listed'])
            delisted_date = pd.to_datetime(meta['delisted']) if meta['delisted'] else None
            
            # 조건: 상장일 이후 AND (상장 폐지일 이전 OR 현재 상장 중)
            is_listed = target_date >= listed_date
            not_delisted = (delisted_date is None) or (target_date <= delisted_date)
            
            if is_listed and not_delisted:
                active_tickers.append(ticker)
            else:
                status = "Not yet listed" if not is_listed else f"Delisted on {meta['delisted']}"
                logger.info(f"Filtering out {ticker} for date {target_date.date()}: {status}")
                
        return active_tickers

    def handle_missing_values(self, df: pd.DataFrame, method: str = 'ffill') -> pd.DataFrame:
        """
        결측치 처리: forward fill 후 남은 결측치는 제거하거나 0으로 채움
        """
        if method == 'ffill':
            return df.ffill().fillna(0)
        elif method == 'drop':
            return df.dropna()
        else:
            return df.fillna(0)

    def remove_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Z-score 기반 이상치 제거 (Winzorizing 또는 Clipping)
        """
        mean = df.mean()
        std = df.std()
        
        upper = mean + self.outlier_threshold * std
        lower = mean - self.outlier_threshold * std
        
        return df.clip(lower=lower, upper=upper, axis=1)

    def align_timestamps(self, price_df: pd.DataFrame, financial_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        가격 데이터와 재무 데이터의 타임스탬프 동기화
        """
        aligned_financial = financial_df.reindex(price_df.index, method='ffill')
        return price_df, aligned_financial

    def check_look_ahead_bias(self, data_timestamp: pd.Timestamp, model_timestamp: pd.Timestamp):
        """
        미래 데이터 접근 차단 확인
        """
        if data_timestamp > model_timestamp:
            raise ValueError(f"Look-ahead bias detected: Data from {data_timestamp} used at {model_timestamp}")

    def validate_universe(self, tickers: List[str], date: Optional[Union[str, pd.Timestamp]] = None) -> List[str]:
        """
        유니버스 검증 및 정제 (Point-in-Time 지원)
        """
        if not tickers:
            logger.warning("Tickers list is empty.")
            return []

        # 1. 시점별 상장 여부 필터링 (Survivorship Bias 방지)
        if date:
            tickers = self.get_active_tickers(date, tickers)

        # 2. 중복 제거
        unique_tickers = list(set(tickers))
        
        # 3. 형식 검증
        valid_tickers = [
            t.strip().upper() for t in unique_tickers 
            if isinstance(t, str) and len(t.strip()) > 0
        ]
        
        if len(valid_tickers) < len(tickers):
            logger.info(f"Universe validated for {date if date else 'current'}: {len(tickers)} -> {len(valid_tickers)} tickers.")
            
        return valid_tickers

    def validate_pipeline(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        전체 데이터 검증 파이프라인 실행
        """
        df = self.handle_missing_values(df)
        df = self.remove_outliers(df)
        logger.info("Data validation pipeline completed.")
        return df
