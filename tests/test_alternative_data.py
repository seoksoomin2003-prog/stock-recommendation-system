from core.alternative_data_engine import AlternativeDataEngine

def test_alternative_data():
    engine = AlternativeDataEngine()
    ticker = "AAPL"
    
    print(f"--- Alternative Data Test for {ticker} ---")
    
    # 1. 개별 소스 테스트
    trends = engine.fetch_google_trends(ticker)
    print(f"Google Trends (last 5 days):\n{trends.tail(5)}")
    
    sns_score = engine.fetch_sns_sentiment(ticker)
    print(f"SNS Sentiment: {sns_score:+.4f}")
    
    momentum = engine.fetch_news_momentum(ticker)
    print(f"News Momentum: {momentum:.4f}")
    
    # 2. 통합 점수 산출
    final_score = engine.calculate_alternative_score(ticker)
    print(f"\nFinal Combined Alternative Score: {final_score:+.4f}")
    
    assert -1.0 <= final_score <= 1.0
    print("\nVerification Successful!")

if __name__ == "__main__":
    test_alternative_data()
