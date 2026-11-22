import json, sys, collections
d = json.load(open("big/latest_us.json"))
print({k: (type(v).__name__, len(v) if hasattr(v, "__len__") else v) for k, v in d.items()})
for k, v in d.items():
    if not isinstance(v, (list, dict)): print(k, "=", v)
rows = d.get("rows") or d.get("items") or d.get("snapshots")
if rows is None:
    for k, v in d.items():
        if isinstance(v, list) and v and isinstance(v[0], dict): print("list key", k, list(v[0].keys())[:60])
        if isinstance(v, dict): print("dict key", k, list(v.keys())[:30])
