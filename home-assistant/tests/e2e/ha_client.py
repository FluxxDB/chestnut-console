"""A small REST client for the throwaway test Home Assistant (never the dev one on 8123)."""

import json
import os
import time
from pathlib import Path

import requests
import websocket

HA_URL = os.environ.get("HA_URL", "http://localhost:8124")
CLIENT_ID = f"{HA_URL}/"
AUTH_FILE = Path(os.environ.get("E2E_WORK", "/work")) / "auth.json"
SIM_DEVICE = os.environ.get("SIM_DEVICE_NAME", "Main Thermostat (Sim)")
SIM_SLUG = "main_thermostat_sim"  # HA's slug of SIM_DEVICE, the prefix of the sim's entity ids


def wait_until(predicate, timeout, interval=0.5, message="condition"):
    """Poll predicate() until it returns a truthy value; return that value or raise."""
    deadline = time.monotonic() + timeout
    last_error = None
    while True:
        try:
            value = predicate()
            if value:
                return value
        except Exception as err:  # noqa: BLE001 - keep polling through transient errors
            last_error = err
        if time.monotonic() > deadline:
            raise TimeoutError(f"timed out after {timeout}s waiting for {message}"
                               + (f" (last error: {last_error!r})" if last_error else ""))
        time.sleep(interval)


class HA:
    """REST helper. Holds a refresh token and renews the access token when it expires."""

    def __init__(self, refresh_token, url=HA_URL, client_id=CLIENT_ID):
        self.url = url
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.access_token = None
        self.expires = 0.0
        self.session = requests.Session()

    @classmethod
    def from_auth_file(cls, path=AUTH_FILE):
        data = json.loads(Path(path).read_text())
        return cls(data["refresh_token"], data.get("url", HA_URL), data.get("client_id", CLIENT_ID))

    # --- auth ---------------------------------------------------------------------------
    def token(self):
        """A valid access token (refreshed when less than a minute is left)."""
        if self.access_token is None or time.time() > self.expires - 60:
            r = self.session.post(f"{self.url}/auth/token", data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
            }, timeout=15)
            r.raise_for_status()
            body = r.json()
            self.access_token = body["access_token"]
            self.expires = time.time() + body["expires_in"]
        return self.access_token

    def browser_tokens(self):
        """The `hassTokens` localStorage value HA's frontend reads (home-assistant-js-websocket)."""
        token = self.token()
        return {
            "hassUrl": self.url,
            "clientId": self.client_id,
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": int(self.expires - time.time()),
            "refresh_token": self.refresh_token,
            "expires": int(self.expires * 1000),
        }

    def request(self, method, path, **kwargs):
        headers = {"Authorization": f"Bearer {self.token()}"}
        r = self.session.request(method, f"{self.url}{path}", headers=headers, timeout=30, **kwargs)
        r.raise_for_status()
        return r.json() if r.content else None

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, data=None):
        return self.request("POST", path, json=data if data is not None else {})

    def ws(self, message, timeout=30):
        """Send one websocket command (e.g. {"type": "config/entity_registry/list"}) and
        return its result; raises RuntimeError if HA answers with an error."""
        url = self.url.replace("http", "ws", 1) + "/api/websocket"
        conn = websocket.create_connection(url, timeout=timeout)
        try:
            json.loads(conn.recv())  # auth_required
            conn.send(json.dumps({"type": "auth", "access_token": self.token()}))
            reply = json.loads(conn.recv())
            if reply.get("type") != "auth_ok":
                raise RuntimeError(f"websocket auth failed: {reply}")
            conn.send(json.dumps({"id": 1, **message}))
            while True:
                reply = json.loads(conn.recv())
                if reply.get("id") == 1 and reply.get("type") == "result":
                    break
        finally:
            conn.close()
        if not reply.get("success"):
            raise RuntimeError(f"websocket {message.get('type')} failed: {reply.get('error')}")
        return reply.get("result")

    # --- states and services ------------------------------------------------------------
    def states(self):
        return self.get("/api/states")

    def get_state(self, entity_id):
        """The state object ({state, attributes, ...}) or None if the entity doesn't exist."""
        try:
            return self.get(f"/api/states/{entity_id}")
        except requests.HTTPError as err:
            if err.response is not None and err.response.status_code == 404:
                return None
            raise

    def call(self, domain, service, data=None):
        """Call a service; returns the changed states HA reports."""
        return self.post(f"/api/services/{domain}/{service}", data or {})

    def template(self, template):
        r = self.session.post(f"{self.url}/api/template", json={"template": template},
                              headers={"Authorization": f"Bearer {self.token()}"}, timeout=30)
        r.raise_for_status()
        return r.text

    # --- the sim device -----------------------------------------------------------------
    def sim_entity(self, domain, object_id):
        """The entity id of the sim's ESPHome entity `object_id` in `domain` (None if absent).

        HA names it `<domain>.main_thermostat_sim_<object_id>` (device name + entity name)."""
        entity_id = f"{domain}.{SIM_SLUG}_{object_id}"
        return entity_id if self.get_state(entity_id) is not None else None

    def sim_climate(self):
        return self.sim_entity("climate", "main_thermostat")

    def sim_online(self):
        entity_id = self.sim_climate()
        if not entity_id:
            return False
        return self.get_state(entity_id)["state"] not in ("unavailable", "unknown")

    def wait_online(self, timeout=120):
        """Wait until HA is connected to the sim (its climate entity is available)."""
        return wait_until(self.sim_online, timeout, interval=1, message="the sim to be online in HA")

    def wait_state(self, entity_id, predicate, timeout=30, interval=0.5):
        """Wait until predicate(state_object) is true; return the state object."""
        def check():
            st = self.get_state(entity_id)
            return st if st is not None and predicate(st) else None
        return wait_until(check, timeout, interval, message=f"{entity_id} to match")
