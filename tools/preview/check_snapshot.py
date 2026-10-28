"""Assert UI snapshot fields captured by drive.py (DIR/<scenario>-<theme>.json).

Usage: check_snapshot.py DIR SCENARIO_SLUG THEME key=value [key=value ...]   (exact text; prefix ~ for a regex)
"""
import json
import sys

d, scen, theme, *pairs = sys.argv[1:]
snap = json.load(open(f"{d}/{scen}-{theme}.json"))
import re


def ok(got, want):
    if want.startswith("~"):
        return isinstance(got, str) and re.search(want[1:], got) is not None
    return got == want


bad = [f"{k}: want {v!r}, got {snap.get(k, '<missing>')!r}" for k, v in (p.split("=", 1) for p in pairs) if not ok(snap.get(k), v)]
if bad:
    print(f"FAIL {scen}/{theme}:\n  " + "\n  ".join(bad))
    sys.exit(1)
print(f"PASS {scen}/{theme}: {len(pairs)} checks")
