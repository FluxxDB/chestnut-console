"""Assert UI snapshot fields captured by drive.py (DIR/<scenario>-<theme>.json).

Usage: check_snapshot.py DIR SCENARIO_SLUG THEME key=value [key=value ...]   (exact text match)
"""
import json
import sys

d, scen, theme, *pairs = sys.argv[1:]
snap = json.load(open(f"{d}/{scen}-{theme}.json"))
bad = [f"{k}: want {v!r}, got {snap.get(k, '<missing>')!r}" for k, v in (p.split("=", 1) for p in pairs) if snap.get(k) != v]
if bad:
    print(f"FAIL {scen}/{theme}:\n  " + "\n  ".join(bad))
    sys.exit(1)
print(f"PASS {scen}/{theme}: {len(pairs)} checks")
