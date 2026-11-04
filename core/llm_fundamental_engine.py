import json
import requests
import pandas as pd
from typing import Dict, List, Optional
from core.rag_engine import RAGEngine
from utils.config import OLLAMA_URL, OLLAMA_MODEL, FUNDAMENTAL_ANALYSIS_CONFIG
from core.llm_validation_layer import LLMValidationLayer # [NEW]
from utils.logger import setup_logger

logger = setup_logger("LLMFundamentalEngine")

class LLMFundamentalEngine:
    """
    고성능 LLM 기반 펀더멘탈 분석 엔진 (V2)
    - RAG 엔진으로부터 추출된 기업 공시 및 뉴스 컨텍스트 활용
    - 정성적 판단(Judgment)을 정량적 알파 신호(0-100 Score)로 변환
    - Ollama의 JSON 모드를 활용한 결정론적 출력 보장
    """
    def __init__(self, rag_engine: RAGEngine):
        self.rag = rag_engine
        self.config = FUNDAMENTAL_ANALYSIS_CONFIG
        self.weights = self.config["weights"]
        self.score_mapping = self.config["score_mapping"]
        self.api_url = OLLAMA_URL

    def _query_ollama_json(self, prompt: str, required_keys: List[str] = None) -> Dict:
        """Ollama API 호출 및 Validation Layer를 통한 검증 (Delegated to Provider Factory)"""
        from core.providers import ProviderFactory
        return ProviderFactory.get_fundamental_provider().query_fundamental(prompt, required_keys)

    def analyze_cashflow_quality(self, ticker: str) -> Dict:
        """현금흐름 질적 분석: 영업현금흐름 vs 당기순이익 괴리 등"""
        context = self.rag.retrieve(f"{ticker} cash flow statement net income depreciation accruals")
        context_str = "\n".join([c['content'] for c in context])

        prompt = f"""
[Role] Principal Quant Analyst
[Task] Analyze Cashflow Quality for {ticker} based on the context.
[Context]
{context_str}

[Rules]
1. Evaluate CFO/Net Income ratio and accruals.
3. Output JSON with fields: 'quality' (HIGH/STABLE/NEUTRAL/WEAK/LOW/RED_FLAG), 'reason', 'confidence'.
"""
        return self._query_ollama_json(prompt, required_keys=['quality', 'reason', 'confidence'])

    def analyze_earnings_resilience(self, ticker: str) -> Dict:
        """이익 복원력/지속성 분석: 일회성 비용, 핵심 사업 성장성 등"""
        context = self.rag.retrieve(f"{ticker} earnings quality core business operating income one-time gains")
        context_str = "\n".join([c['content'] for c in context])

        prompt = f"""
[Role] Principal Quant Analyst
[Task] Analyze Earnings Resilience for {ticker}.
[Context]
{context_str}

[Rules]
1. Identify if growth is driven by core operations or non-recurring items.
2. Output JSON with fields: 'resilience' (HIGH/STABLE/NEUTRAL/WEAK/LOW/RED_FLAG), 'reason', 'confidence'.
"""
        return self._query_ollama_json(prompt, required_keys=['resilience', 'reason', 'confidence'])

    def analyze_growth_sustainability(self, ticker: str) -> Dict:
        """성장 지속성 분석: 시장 점유율, 해자(Moat), R&D 효율 등"""
        context = self.rag.retrieve(f"{ticker} competitive advantage moat market share growth outlook")
        context_str = "\n".join([c['content'] for c in context])

        prompt = f"""
[Role] Principal Quant Analyst
[Task] Analyze Growth Sustainability and Moat for {ticker}.
[Context]
{context_str}

[Rules]
1. Evaluate competitive advantages and long-term viability.
2. Output JSON with fields: 'sustainability' (HIGH/STABLE/NEUTRAL/WEAK/LOW/RED_FLAG), 'reason', 'confidence'.
"""
        return self._query_ollama_json(prompt, required_keys=['sustainability', 'reason', 'confidence'])

    def analyze_debt_quality(self, ticker: str) -> Dict:
        """부채 질적 분석: 생산적 투자(GOOD) vs 생존형 부채(BAD)"""
        context = self.rag.retrieve(f"{ticker} debt capex interest coverage leverage borrowing purpose")
        context_str = "\n".join([c['content'] for c in context])

        prompt = f"""
[Role] Principal Quant Analyst
[Task] Analyze Debt Quality and Purpose for {ticker}.
[Context]
{context_str}

[Rules]
1. Determine if debt is for productive investment (GOOD) or survival/liquidity (BAD).
2. Criteria for GOOD: CAPEX expansion, R&D, strategic M&A with synergy.
3. Criteria for BAD: Refinancing high-interest debt, covering operating losses, dividend recapitalization.
4. Output JSON with fields: 'debt_type' (GOOD/BAD), 'reason', 'confidence' (0.0-1.0).
"""
        return self._query_ollama_json(prompt, required_keys=['debt_type', 'reason', 'confidence'])

    def _get_filtered_score(self, res: Dict, key: str, default_val: str = "NEUTRAL") -> float:
        """[Institutional Rule] Confidence < 0.6인 시그널은 무시(NEUTRAL 처리하지 않고 NaN 반환)함"""
        import numpy as np
        confidence = res.get("confidence", 0.0)
        label = res.get(key, default_val)
        
        # [P6-16] Do not fabricate 50.0 neutral scores for low confidence or mock data.
        if confidence < 0.6:
            logger.warning(f"Low confidence ({confidence:.2f}) for '{key}:{label}'. Ignoring signal (NaN).")
            return np.nan
            
        return self.score_mapping.get(label, np.nan)

    def get_alpha_signal(self, ticker: str) -> Dict:
        """
        종합 펀더멘탈 알파 신호 생성
        - 개별 분석 결과 취합 및 점수화
        """
        import numpy as np
        logger.info(f"Generating fundamental alpha signal for {ticker}...")
        
        # 1. 개별 분석 수행
        cf_res = self.analyze_cashflow_quality(ticker)
        er_res = self.analyze_earnings_resilience(ticker)
        gs_res = self.analyze_growth_sustainability(ticker)
        db_res = self.analyze_debt_quality(ticker) # [NEW]
        
        # 2. 점수 매핑 및 신뢰도 필터링 (Section 8: Confidence < 0.6 Ignore)
        scores = {
            "cashflow": self._get_filtered_score(cf_res, "quality"),
            "earnings": self._get_filtered_score(er_res, "resilience"),
            "growth": self._get_filtered_score(gs_res, "sustainability"),
            "debt": self._get_filtered_score(db_res, "debt_type")
        }
        
        # Check if any component is mock
        is_mock = any(
            res.get("reason", "").lower() == "mock" or 
            res.get("status") == "MOCK" or
            res.get("mode") == "local" or
            "local mode" in res.get("reason", "").lower()
            for res in [cf_res, er_res, gs_res, db_res]
        )
        is_unavailable = any(res.get("status") == "UNAVAILABLE" for res in [cf_res, er_res, gs_res, db_res])

        # 3. 가중 평균 산출
        valid_scores = [s for s in scores.values() if not pd.isna(s)]
        if len(valid_scores) < 4 or is_mock:
            # If any required fundamental component fails or is MOCK, the entire fundamental optional factor is unavailable.
            final_score = np.nan
            if is_mock:
                data_status = "MOCK"
            else:
                data_status = "UNAVAILABLE"
        else:
            final_score = (
                scores["cashflow"] * self.weights["cashflow"] +
                scores["earnings"] * self.weights["earnings_quality"] +
                scores["growth"] * self.weights["growth_resilience"] +
                scores["debt"] * self.weights["debt_quality"]
            )
            data_status = "REAL"
        
        final_result = {
            "ticker": ticker,
            "final_score": round(final_score, 2) if not pd.isna(final_score) else np.nan,
            "data_status": data_status,
            "components": {
                "cashflow": cf_res,
                "earnings": er_res,
                "growth": gs_res,
                "debt": db_res
            },
            "timestamp": pd.Timestamp.now().isoformat()
        }
        
        logger.info(f"[{ticker}] Fundamental Alpha Score: {final_result['final_score']} (Status: {data_status})")
        return final_result

    def batch_analyze_full(self, tickers: List[str]) -> Dict[str, Dict]:
        """상위 종목군에 대한 상세 분석 결과 반환 (Scoring Overlay용)"""
        results = {}
        for ticker in tickers:
            results[ticker] = self.get_alpha_signal(ticker)
        return results

    def batch_analyze_top_candidates(self, tickers: List[str]) -> pd.Series:
        """상위 종목군에 대한 일괄 분석 (Score Series 반환)"""
        results = {}
        statuses = {}
        for ticker in tickers:
            signal = self.get_alpha_signal(ticker)
            results[ticker] = signal["final_score"]
            statuses[ticker] = signal["data_status"]
        series = pd.Series(results)
        series.attrs["data_status"] = statuses
        return series
