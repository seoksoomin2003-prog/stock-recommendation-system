"""Read-only: the assistant's stored-scan answers for three recorded stocks.  Network is blocked first, so nothing can be fetched."""
import socket, sys, json
from pathlib import Path
def _no(*a, **k): raise OSError("network blocked by the assessment script")
socket.socket.connect = _no
socket.create_connection = _no
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from utils import runtime_config
runtime_config.load_local_env(repo / ".env")
from terminal.services import Terminal
from terminal import assistant
t = Terminal(repo)
out = {}
for market, ticker, name, strategy, intents in (("US", "ECL", "Ecolab Inc.", "LONG_TERM", ("WHY", "SELL_CHECK")), ("US", "BA", "The Boeing Company", "LONG_TERM", ("WHY", "RISK")),
                                               ("KR", "138930", "BNK금융지주", "SWING", ("WHY", "STOP")), ("US", "ACGL", "Arch Capital Group Ltd.", "LONG_TERM", ("WHY",))):
    for intent in intents:
        try:
            r = assistant.stock_answer(t, intent, {"market": market, "ticker": ticker, "name": name}, strategy)
        except Exception as exc:
            r = {"error": f"{type(exc).__name__}: {exc}"}
        out[f"{market}_{ticker}_{intent}"] = r
        print(f"\n===== {market} {ticker} {strategy} {intent}")
        if "error" in r: print(r["error"]); continue
        print("TITLE:", r["title"]); print("SUMMARY:", r["summary"])
        for s in r["sections"]:
            print(" [", s["title"], "]")
            for line in s["lines"]: print("    -", line)
        print(" basis:", r.get("basis"))
json.dump(out, open(Path(__file__).with_name("assistant_answers.json"), "w"), ensure_ascii=False, indent=1, default=str)
