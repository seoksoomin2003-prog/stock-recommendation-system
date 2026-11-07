"""Can untested Korean event signals be read for free?  Counts of OpenDART structured records on the sample of the insider probe.
No returns, no score.  Saved in the git-ignored research_data/kr_share_probe/candidates.  Run with: python scripts/qsf_kr_candidate_probe.py"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from utils import runtime_config  # noqa: E402

runtime_config.load_local_env()
from markets.kr.dart import OpenDartClient  # noqa: E402
from scripts.qsf_kr_corp_action_probe import call  # noqa: E402

EVENTS = {"cvbdIsDecsn": "CB", "bdwtIsDecsn": "BW", "piicDecsn": "rights", "fricDecsn": "bonus", "tsstkAqDecsn": "buyback", "crDecsn": "reduction"}
YEARLY = {"alotMatter": "dividend", "hyslrSttus": "largest_holder", "accnutAdtorNmNdAdtOpinion": "audit"}


def main():
    dart = OpenDartClient()
    corp = {str(r["stock_code"]).strip(): str(r["corp_code"]) for _, r in dart.corp_codes().iterrows() if str(r["stock_code"]).strip()}
    rows = json.load(open("research_data/kr_share_probe/insider/summary.json"))["rows"]
    d = Path("research_data/kr_share_probe/candidates")
    d.mkdir(exist_ok=True)
    out = {}
    for e, label in EVENTS.items():
        n, first, read = [], [], 0
        for r in rows:
            got = call(dart, d / f"{r['code']}_{e}.json", f"{e}.json", corp_code=corp[r["code"]], bgn_de="20150101", end_de="20261106")
            read += got.get("status") in ("000", "013")
            lst = got.get("list") or []
            n.append(len(lst))
            first += [x.get("rcept_no", "")[:4] for x in lst]
        out[label] = {"read": read, "names_with_event": int(sum(x > 0 for x in n)), "events": int(sum(n)), "mean": round(float(np.mean(n)), 2), "first_year": min(first) if first else None}
    for e, label in YEARLY.items():
        have, read = 0, 0
        for r in rows[:30]:
            got = call(dart, d / f"{r['code']}_{e}_2024.json", f"{e}.json", corp_code=corp[r["code"]], bsns_year="2024", reprt_code="11011")
            read += got.get("status") in ("000", "013")
            have += bool(got.get("list"))
        out[label] = {"read": read, "names_with_2024_value": have, "sample": 30}
    (d / "summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in out.items():
        print(k, v)


if __name__ == "__main__":
    main()
