"""Agent 8 scratch: what one day's Telegram message looks like.  Uses the program's own pure functions (Automation.compose,
assistant.daily_lines) on the step states and the two Today briefings already fetched with GET.  Sends nothing, writes nothing
but its own output, builds no Terminal and reads no environment."""
import json, sys, urllib.request
from pathlib import Path
here = Path(__file__).parent
sys.path.insert(0, str(here.parents[3]))
from terminal import assistant
from terminal.automation import Daily as Automation
st = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/automation/status"))
steps = st["steps"]
briefs = [json.load(open(here / f"get_api_assistant_today_market_{m}.json")) for m in ("US", "KR")]
brief = assistant.daily_lines(briefs)
alerts = {"status": "OK", "items": [], "stale": []}          # no account is recorded in the terminal
text = Automation.compose(st["latest_session"], steps, alerts, [], st["last_run"].get("missing_sessions") or [], notes=st.get("notes") or [], brief=brief)
print(text)
print("-----\nchars:", len(text), "lines:", len(text.splitlines()), "| [오늘 볼 것] lines:", len(brief), "chars:", sum(map(len, brief)))
