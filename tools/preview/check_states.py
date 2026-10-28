"""Assert entity states captured by drive.py --dump (DIR/<scenario>-<theme>-states.json).

Usage: check_states.py DIR SCENARIO_SLUG key=value [key=value ...]
Values: numbers compare to 0.05, 'nan' matches NaN, true/false for booleans, anything else as text.
"""
import json
import math
import sys

d, scen, *pairs = sys.argv[1:]
states = json.load(open(f"{d}/{scen}-light-states.json"))
bad = []
for pair in pairs:
    key, want = pair.split("=", 1)
    got = states.get(key, "<missing>")
    if want == "nan":
        ok = isinstance(got, float) and math.isnan(got)
    elif want in ("true", "false"):
        ok = got is (want == "true")
    else:
        try:
            # Tight enough that a dim level (0.04) can't pass for off (0.0).
            ok = abs(float(got) - float(want)) < 0.005
        except (TypeError, ValueError):
            ok = str(got) == want
    if not ok:
        bad.append(f"{key}: want {want!r}, got {got!r}")
if bad:
    print(f"FAIL {scen}:\n  " + "\n  ".join(bad))
    sys.exit(1)
print(f"PASS {scen}: {len(pairs)} checks")
