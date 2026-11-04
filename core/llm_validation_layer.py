import json
import re
from typing import Dict, List, Any, Optional
from utils.logger import setup_logger

logger = setup_logger("LLMValidationLayer")

class LLMValidationLayer:
    """
    LLM 응답 데이터 검증 및 정제 레이어 (V2)
    - 비결정적인 LLM 출력(Markdown, 추가 텍스트 등)에서 JSON 추출
    - 필수 키 존재 여부 및 데이터 타입 검증
    - 파싱 실패 시 안전한 디폴트값 반환 (System Reliability 확보)
    """

    @staticmethod
    def sanitize_and_parse(text: str, required_keys: List[str] = None) -> Dict[str, Any]:
        """
        텍스트에서 JSON을 추출하고 검증함
        """
        if not text or not isinstance(text, str):
            logger.error("Invalid input text for parsing.")
            return LLMValidationLayer.get_safe_default()

        # 1. Markdown Code Block 제거 (```json ... ``` 또는 ``` ... ```)
        cleaned_text = text.strip()
        json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        match = re.search(json_pattern, cleaned_text)
        if match:
            cleaned_text = match.group(1)
        
        # 2. JSON 시작/끝 지점 찾기 (중괄호 기준)
        try:
            start_idx = cleaned_text.find('{')
            end_idx = cleaned_text.rfind('}') + 1
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON object found in text.")
            
            json_str = cleaned_text[start_idx:end_idx]
            data = json.loads(json_str)

            # 3. 필수 키 검증
            if required_keys:
                missing_keys = [key for key in required_keys if key not in data]
                if missing_keys:
                    logger.warning(f"Missing required keys: {missing_keys}. Applying partial defaults.")
                    # 누락된 키에 대해 기본값 채우기 (전체 실패 처리는 하지 않음)
                    for key in missing_keys:
                        data[key] = "N/A" if "reason" in key else 0.0

            return data

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON Parsing failed: {str(e)} | Raw snippet: {text[:100]}...")
            return LLMValidationLayer.get_safe_default()

    @staticmethod
    def get_safe_default() -> Dict[str, Any]:
        """
        시스템 중단을 방지하기 위한 안전한 빈 결과 반환
        """
        return {
            "status": "error",
            "signal_strength": 0.0,
            "reason": "Invalid or malformed LLM output",
            "confidence": 0.0,       # [NEW] 신뢰도 기본값 0.0
            "quality": "NEUTRAL",
            "resilience": "NEUTRAL",
            "sustainability": "NEUTRAL",
            "debt_type": "NEUTRAL"
        }

    @staticmethod
    def validate_range(value: Any, min_val: float = 0.0, max_val: float = 1.0) -> float:
        """수치 데이터 범위 강제 (0.0 ~ 1.0)"""
        try:
            num = float(value)
            return max(min_val, min(max_val, num))
        except (ValueError, TypeError):
            return 0.0
