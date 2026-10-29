"""Prepare the fresh test Home Assistant: onboard it, add the sim through ESPHome's config flow.

Run by run.sh inside the test container, before pytest. Writes $E2E_WORK/auth.json (the test
user's refresh token) for the fixtures. Talks only to HA_URL (the throwaway instance on 8124).
"""

import json
import os
import sys
import time

import requests

from ha_client import AUTH_FILE, CLIENT_ID, HA, HA_URL, wait_until

USER = {"name": "Test", "username": "test", "password": "test-pass-123", "language": "en"}
SIM_HOST = os.environ.get("SIM_HOST", "127.0.0.1")
SIM_PORT = int(os.environ.get("SIM_PORT", "6053"))


def log(msg):
    print(f"[ha_setup] {msg}", flush=True)


def wait_for_http(timeout=300):
    def up():
        r = requests.get(f"{HA_URL}/api/onboarding", timeout=5)
        return r.status_code == 200 and r.json()
    steps = wait_until(up, timeout, interval=1, message=f"Home Assistant at {HA_URL}")
    log(f"HA is up; onboarding steps: {steps}")
    return steps


def onboard():
    r = requests.post(f"{HA_URL}/api/onboarding/users", json={**USER, "client_id": CLIENT_ID}, timeout=60)
    if r.status_code != 200:
        sys.exit(f"onboarding user step failed: {r.status_code} {r.text}")
    code = r.json()["auth_code"]
    r = requests.post(f"{HA_URL}/auth/token", data={
        "grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID,
    }, timeout=30)
    r.raise_for_status()
    tokens = r.json()
    ha = HA(tokens["refresh_token"])
    ha.access_token = tokens["access_token"]
    ha.expires = time.time() + tokens["expires_in"]

    ha.post("/api/onboarding/core_config")
    ha.post("/api/onboarding/analytics")
    ha.post("/api/onboarding/integration",
            {"client_id": CLIENT_ID, "redirect_uri": f"{HA_URL}/?auth_callback=1"})
    status = requests.get(f"{HA_URL}/api/onboarding", timeout=10).json()
    if not all(step["done"] for step in status):
        sys.exit(f"onboarding incomplete: {status}")
    log("onboarded user 'test'")
    return ha


def add_sim(ha, key):
    """ESPHome config flow (HA 2026.10.4): user {host, port} -> encryption_key {noise_psk} -> entry."""
    answers = {
        "user": {"host": SIM_HOST, "port": SIM_PORT},
        "encryption_key": {"noise_psk": key},
    }
    flow = ha.post("/api/config/config_entries/flow", {"handler": "esphome", "show_advanced_options": False})
    for _ in range(6):
        kind = flow.get("type")
        if kind == "create_entry":
            log(f"ESPHome entry created: {flow.get('title')}")
            return flow
        if kind == "abort":
            sys.exit(f"ESPHome flow aborted: {flow.get('reason')}")
        if kind != "form" or flow.get("step_id") not in answers:
            sys.exit(f"unexpected ESPHome flow step: {json.dumps(flow)}")
        if flow.get("errors"):
            log(f"step {flow['step_id']} errors: {flow['errors']}")
        step = flow["step_id"]
        if step == "user" and flow.get("errors"):
            # The sim isn't listening yet (still starting): retry the connection.
            time.sleep(2)
        flow = ha.post(f"/api/config/config_entries/flow/{flow['flow_id']}", answers[step])
    sys.exit(f"ESPHome flow did not finish: {json.dumps(flow)}")


def main():
    key = os.environ["SIM_KEY"]
    if HA_URL.rstrip("/").endswith(":8123"):
        sys.exit("refusing to run against port 8123 (the dev HA)")
    steps = wait_for_http()
    if all(step["done"] for step in steps):
        sys.exit("this HA is already onboarded: not a fresh test instance, refusing to touch it")
    ha = onboard()
    add_sim(ha, key)
    # The one-time install step that makes Chestnut HA's landing page and drops the stock
    # Overview from the sidebar (Settings > Dashboards > Chestnut > Set as default for
    # everyone). HA 2026.10 keeps it in .storage (frontend system data), not in YAML.
    ha.ws({"type": "frontend/set_system_data", "key": "core",
           "value": {"default_panel": "lovelace"}})
    wait_until(lambda: ha.get("/api/config").get("state") == "RUNNING", 180, interval=1,
               message="HA to finish starting")
    ha.wait_online(timeout=120)
    log(f"sim online: {ha.sim_climate()}")
    AUTH_FILE.write_text(json.dumps({"url": HA_URL, "client_id": CLIENT_ID,
                                     "refresh_token": ha.refresh_token}))


if __name__ == "__main__":
    main()
