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


async def maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--themes", default="light")
    ap.add_argument("--settle", type=float, default=1.5)
    ap.add_argument("scenarios", nargs="*")
    args = ap.parse_args()

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
            print(f"captured {base}.png")

    await client.disconnect()


asyncio.run(main())
