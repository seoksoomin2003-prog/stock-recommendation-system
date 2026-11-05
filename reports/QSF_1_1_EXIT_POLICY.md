# QSF 1.1 청산 정책

보유 종목에만 적용한다. 행동: HOLD, HOLD_AND_REVIEW, PARTIAL_TAKE_PROFIT, REDUCE, EXIT, THESIS_INVALIDATED, TIME_STOP_REVIEW. 여러 조건이 겹치면 EXIT > THESIS_INVALIDATED > REDUCE > PARTIAL_TAKE_PROFIT > TIME_STOP_REVIEW > HOLD_AND_REVIEW > HOLD 순서로 하나를 고르고, 해당 조건을 모두 함께 보여준다.

## 스윙
| 조건 | 행동 |
|---|---|
| 종가 ≤ 손절 기준 | EXIT |
| 종가 < 하락 중인 50일선 | THESIS_INVALIDATED |
| 모멘텀 점수 < 25/100 | REDUCE |
| 시장 국면 점수 < 25/100 | REDUCE |
| 종가 ≥ 목표 | PARTIAL_TAKE_PROFIT |
| 보유 30거래일 경과 | TIME_STOP_REVIEW |
| 남은 손익비 < 1 | HOLD_AND_REVIEW |
| 실적 2거래일 이내 | HOLD_AND_REVIEW |

손절 발동, 예상 체결, 갭 위험을 구분한다. 손절은 체결을 보장하지 않으며, 갭이 생기면 더 불리하게 체결될 수 있다. 2 ATR은 시나리오이고 법칙이 아니다. 다른 손절 폭 비교는 표본이 쌓인 뒤 표본 외 연구로 한다.

## 장기
| 조건 | 행동 |
|---|---|
| 종가 ≤ 사용자가 정한 손절가 (QSF-1.1.2, 사용자 결정) | EXIT |
| ROE 5%p 넘게 하락하고 8% 미만 | THESIS_INVALIDATED |
| 주식 수 1년 10% 초과 증가 | THESIS_INVALIDATED |
| 재무 복원력 < 20/100 | REDUCE |
| 비중이 한도 초과 | REDUCE |
| 밸류에이션 < 10/100 | PARTIAL_TAKE_PROFIT |
| FCF 흑자 연도 1/3 미만 | HOLD_AND_REVIEW |
| 지배구조 경고 공시 | HOLD_AND_REVIEW |

가격 하락만으로는 장기 논리를 무효화하지 않는다. 스윙식 손절을 기본으로 쓰지 않는다. 경쟁력 악화와 '더 나은 대안 비교'는 측정 방법이 없어 v1에 넣지 않았다.

## 공통
중대 공시는 EXIT, 거래대금 기준 미달은 REDUCE.
