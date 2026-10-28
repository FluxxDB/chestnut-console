"""Drive the console preview through the native API and capture screenshots.

Usage: drive.py --out DIR [--themes light,dark] [--settle 1.5] [SCENARIO ...]
With no scenarios (or no Scenario select in the config) it captures "default".
For each scenario and theme it writes DIR/<scenario>-<theme>.png and, when the
config exposes a `ui_snapshot` text sensor, DIR/<scenario>-<theme>.json.
"""
import argparse
import asyncio
import inspect
import json
import re
import subprocess

from aioesphomeapi import APIClient


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def dump_states(entities, states) -> dict:
    """object_id -> plain state; climates also get <id>.mode / .action / .fan_mode."""
    out = {}
    for e in entities:
        s = states.get(e.key)
        if s is None:
            continue
        if hasattr(s, "mode") and hasattr(s, "action"):
            out[f"{e.object_id}.mode"] = s.mode.name
            out[f"{e.object_id}.action"] = s.action.name
            out[f"{e.object_id}.fan_mode"] = s.fan_mode.name if s.fan_mode is not None else None
            continue
        if not hasattr(s, "state"):
            continue
        v = s.state
        if getattr(s, "missing_state", False):
            v = None
        out[e.object_id] = v.name if hasattr(v, "name") else v
    return out


async def maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--themes", default="light")
    ap.add_argument("--settle", type=float, default=1.5)
    ap.add_argument("--dump", action="store_true", help="also write <base>-states.json")
    ap.add_argument("scenarios", nargs="*")
    args = ap.parse_intermixed_args()

    client = APIClient("127.0.0.1", 6053, None)
    await client.connect(login=True)
    entities, _ = await client.list_entities_services()
    by_id = {e.object_id: e for e in entities}

    states: dict[int, object] = {}
    await maybe_await(client.subscribe_states(lambda s: states.__setitem__(s.key, s)))

    scenario = by_id.get("scenario")
    theme = by_id.get("ui_dark_theme")
    snapshot = by_id.get("ui_snapshot")
    scenarios = args.scenarios if (args.scenarios and scenario) else ["default"]

    for name in scenarios:
        if scenario and name != "default":
            client.select_command(scenario.key, name)
        for th in args.themes.split(","):
            if theme:
                client.switch_command(theme.key, th == "dark")
            await asyncio.sleep(args.settle)
            base = f"{args.out}/{slug(name)}-{th}"
            subprocess.run(["import", "-window", "root", f"{base}.png"], check=True)
            if snapshot and snapshot.key in states:
                text = states[snapshot.key].state
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = {"raw": text}
                with open(f"{base}.json", "w") as f:
                    json.dump(data, f, indent=2)
            if args.dump:
                with open(f"{base}-states.json", "w") as f:
                    json.dump(dump_states(entities, states), f, indent=2)
            print(f"captured {base}.png")

    await client.disconnect()


asyncio.run(main())
