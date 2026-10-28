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
        if hasattr(s, "brightness") and hasattr(s, "state"):
            out[e.object_id] = s.state
            out[f"{e.object_id}.brightness"] = round(s.brightness, 2)
            continue
        if not hasattr(s, "state"):
            continue
        v = s.state
        if getattr(s, "missing_state", False):
            v = None
        out[e.object_id] = v.name if hasattr(v, "name") else v
    return out


def tap(xy: str) -> None:
    x, y = xy.split(",")
    # Hold the press for 100 ms: the SDL touchscreen polls the button state, so an instant
    # click (down and up within microseconds) falls between polls and is never seen.
    subprocess.run(["xdotool", "mousemove", x, y, "mousedown", "1", "sleep", "0.1", "mouseup", "1"], check=True)


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
    ap.add_argument("--number", action="append", default=[], help="object_id=value to set before clicking")
    ap.add_argument("--clicks", default="", help="'x,y;x,y' taps after the scenario is applied")
    ap.add_argument("--click-gap", type=float, default=0.15)
    ap.add_argument("--wake", default="200,50", help="neutral tap first, so a dimmed screen is awake")
    ap.add_argument("--post-wait", type=float, default=2.5, help="seconds after the clicks (debounce)")
    ap.add_argument("--pre-wait", type=float, default=0.0, help="seconds of no input before clicking (idle tests)")
    ap.add_argument("--no-wake", action="store_true", help="skip the neutral wake tap")
    ap.add_argument("scenarios", nargs="*")
    args = ap.parse_intermixed_args()

    client = APIClient("127.0.0.1", 6053, None)
    await client.connect(login=True)
    entities, _ = await client.list_entities_services()
    by_id = {e.object_id: e for e in entities}

    states: dict[int, object] = {}
    updates: dict[str, int] = {}
    names = {e.key: e.object_id for e in entities}

    def on_state(s):
        states[s.key] = s
        oid = names.get(s.key)
        if oid:
            updates[oid] = updates.get(oid, 0) + 1

    await maybe_await(client.subscribe_states(on_state))

    scenario = by_id.get("scenario")
    theme = by_id.get("dark_theme")
    snapshot = by_id.get("ui_snapshot")
    scenarios = args.scenarios if (args.scenarios and scenario) else ["default"]

    for name in scenarios:
        if scenario and name != "default":
            client.select_command(scenario.key, name)
        for th in args.themes.split(","):
            if theme:
                client.switch_command(theme.key, th == "dark")
            await asyncio.sleep(args.settle)
            for spec in args.number:
                oid, val = spec.split("=", 1)
                client.number_command(by_id[oid].key, float(val))
            if args.number:
                await asyncio.sleep(args.settle)
            writes = {}
            if not args.clicks and args.pre_wait:
                await asyncio.sleep(args.pre_wait)
            if args.clicks:
                if args.pre_wait:
                    await asyncio.sleep(args.pre_wait)
                elif not args.no_wake:
                    tap(args.wake)
                    await asyncio.sleep(0.5)
                before = dict(updates)
                for xy in args.clicks.split(";"):
                    tap(xy)
                    await asyncio.sleep(args.click_gap)
                await asyncio.sleep(args.post_wait)
                writes = {k: updates.get(k, 0) - before.get(k, 0) for k in updates}
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
                    data = dump_states(entities, states)
                    data.update({f"_writes.{k}": v for k, v in writes.items()})
                    json.dump(data, f, indent=2)
            print(f"captured {base}.png")

    await client.disconnect()


asyncio.run(main())
