#!/usr/bin/env python3
import sys
import datetime
from datetime import timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

import utils.config
from research.orchestrator import ResearchOrchestrator
from contracts.research import ResearchRequest

def main():
    utils.config.APP_MODE = "local"
    utils.config.MAX_LOCAL_TICKERS = 10
    
    orch = ResearchOrchestrator()
    
    tickers = ["GOOGL", "AAPL", "MSFT", "NVDA", "TSLA"]
    as_of = datetime.datetime.now(timezone.utc)
    
    print("=============================================================")
    print("RUNNING UNMOCKED REAL INTERNET DATA E2E RESEARCH RUN")
    print("=============================================================")
    
    results = {}
    for t in tickers:
        print(f"\nAnalyzing ticker: {t} ...")
        req = ResearchRequest(query=t, as_of=as_of)
        try:
            out = orch.research(req)
            results[t] = out
            print(f"  Status: {out.status}")
            print(f"  Alpha Score: {out.alpha_score}")
            print(f"  Risks: {out.risks}")
            print("  Data Quality Status:")
            for domain, dq in out.data_quality.items():
                print(f"    - {domain:10} | Status: {dq['status']:12} | Source: {dq['source']}")
        except Exception as e:
            print(f"  CRITICAL ERROR running {t}: {e}")
            
    print("\n=============================================================")
    print("FINAL SUMMARY MATRIX:")
    print("=============================================================")
    print(f"{'Ticker':8} | {'Status':15} | {'Alpha Score':11} | {'Market':8} | {'Financial':10} | {'News':8} | {'SEC':8} | {'Trends':8}")
    print("-" * 92)
    for t in tickers:
        out = results.get(t)
        if out:
            score_str = f"{out.alpha_score:.4f}" if out.alpha_score is not None else "None"
            dq = out.data_quality
            print(f"{t:8} | {out.status:15} | {score_str:11} | "
                  f"{dq.get('market', {}).get('status', 'N/A'):8} | "
                  f"{dq.get('financial', {}).get('status', 'N/A'):10} | "
                  f"{dq.get('news', {}).get('status', 'N/A'):8} | "
                  f"{dq.get('sec', {}).get('status', 'N/A'):8} | "
                  f"{dq.get('trends', {}).get('status', 'N/A'):8}")
        else:
            print(f"{t:8} | ERROR")

if __name__ == "__main__":
    main()
