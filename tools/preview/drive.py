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
    ap.add_argument("--no-theme", action="store_true", help="leave the theme switch alone (files still say -light)")
    ap.add_argument("--watch", default="", help="ui_snapshot fields to sample over time, comma-separated (e.g. scrim_opa,bl_now)")
    ap.add_argument("--watch-for", type=float, default=0.0, help="seconds to sample --watch before capturing")
    ap.add_argument("--ha-state", action="append", default=[], help="entity:attribute=state to send as Home Assistant")
    ap.add_argument("--disconnect", type=float, default=0.0,
                    help="after each capture: drop the API connection this long, reconnect, save <base>-reconnect.json")
    ap.add_argument("scenarios", nargs="*")
    args = ap.parse_intermixed_args()

    client = APIClient("127.0.0.1", 6053, None)
    await client.connect(login=True)
    entities, _ = await client.list_entities_services()
    by_id = {e.object_id: e for e in entities}
    snapshot = by_id.get("ui_snapshot")

    states: dict[int, object] = {}
    updates: dict[str, int] = {}
    names = {e.key: e.object_id for e in entities}

    # --watch: each value a snapshot field takes, in order (repeats collapsed).
    watched: dict[str, list] = {f: [] for f in args.watch.split(",") if f}

    def on_state(s):
        states[s.key] = s
        if watched and snapshot is not None and s.key == snapshot.key:
            try:
                snap = json.loads(s.state)
            except json.JSONDecodeError:
                snap = {}
            for f, seen in watched.items():
                v = snap.get(f)
                if v is not None and (not seen or seen[-1] != v):
                    seen.append(v)
        oid = names.get(s.key)
        if oid:
            updates[oid] = updates.get(oid, 0) + 1

    await maybe_await(client.subscribe_states(on_state))

    if args.ha_state:
        # Act as Home Assistant: answer the device's state subscriptions.
        await maybe_await(client.subscribe_home_assistant_states(lambda entity_id, attribute: None))
        await asyncio.sleep(0.5)
        for spec in args.ha_state:
            ent, rest = spec.split(":", 1)
            attr, val = rest.split("=", 1)
            client.send_home_assistant_state(ent, attr or None, val)

    scenario = by_id.get("scenario")
    theme = by_id.get("dark_theme")
    snapshot = by_id.get("ui_snapshot")
    scenarios = args.scenarios if (args.scenarios and scenario) else ["default"]

    for name in scenarios:
        if scenario and name != "default":
            client.select_command(scenario.key, name)
        for th in args.themes.split(","):
            if theme and not args.no_theme:
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
            if args.watch_for:
                for seen in watched.values():
                    seen.clear()
                await asyncio.sleep(args.watch_for)
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
                    data.update({f"_watch.{f}": list(seen) for f, seen in watched.items()})
                    json.dump(data, f, indent=2)
            if args.disconnect and snapshot:
                await client.disconnect()
                await asyncio.sleep(args.disconnect)
                client = APIClient("127.0.0.1", 6053, None)
                await client.connect(login=True)
                first: list = []
                await maybe_await(client.subscribe_states(
                    lambda s: first.append(s.state) if s.key == snapshot.key and not first else None))
                for _ in range(50):
                    if first:
                        break
                    await asyncio.sleep(0.1)
                with open(f"{base}-reconnect.json", "w") as f:
                    json.dump(json.loads(first[0]) if first else {}, f, indent=2)
            print(f"captured {base}.png")

    await client.disconnect()


asyncio.run(main())
