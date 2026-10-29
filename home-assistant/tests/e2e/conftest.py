"""Fixtures for the dashboard's end-to-end tests (run through home-assistant/tests/run.sh e2e).

- `ha`: helper for the test HA: REST (get_state, call, states, template), one-shot websocket
  commands (ws), and the sim (sim_entity(domain, object_id), sim_climate, wait_online), wait_state.
- `page`: a Playwright page logged in as the test user and open on /lovelace/0 (the Chestnut
  dashboard). `request_log` lists every URL the page requested.
- `sim`: stop() / start() the host sim (its container), to test the thermostat going offline.
  A test that leaves it stopped gets it restarted, and HA reconnected, afterwards.
"""

import json
import os

import docker
import pytest

from ha_client import HA, HA_URL

SIM_CONTAINER = os.environ.get("SIM_CONTAINER", "chestnut-e2e-sim")
DASHBOARD_PATH = "/lovelace/0"


@pytest.fixture(scope="session")
def ha():
    return HA.from_auth_file()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "base_url": HA_URL, "viewport": {"width": 1440, "height": 900}}


@pytest.fixture
def request_log():
    return []


def open_dashboard(context, ha, request_log, path=DASHBOARD_PATH):
    """Log `context` in (HA's own token storage) and open `path`; returns the page."""
    tokens = json.dumps(json.dumps(ha.browser_tokens()))
    context.add_init_script(script=f"window.localStorage.setItem('hassTokens', {tokens});")
    page = context.new_page()
    page.on("request", lambda req: request_log.append(req.url))
    page.goto(path)
    # The lovelace panel is up once the view is attached (css selectors pierce shadow roots).
    page.wait_for_selector("hui-root", state="attached", timeout=30_000)
    return page


@pytest.fixture
def page(context, ha, request_log):
    return open_dashboard(context, ha, request_log)


class Sim:
    def __init__(self, ha):
        self.ha = ha
        self.client = docker.from_env()
        self.stopped = False

    def _container(self):
        return self.client.containers.get(SIM_CONTAINER)

    def stop(self):
        """Stop the sim program (HA sees the device go offline)."""
        self._container().stop(timeout=2)
        self.stopped = True

    def start(self, wait=True, timeout=120):
        """Start it again (fresh program state); by default wait until HA has reconnected."""
        self._container().start()
        self.stopped = False
        if wait:
            self.ha.wait_online(timeout=timeout)


@pytest.fixture
def sim(ha):
    s = Sim(ha)
    yield s
    if s.stopped or s._container().status != "running":
        s.start(wait=True)
