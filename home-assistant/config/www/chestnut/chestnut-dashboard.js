// <chestnut-dashboard>: the Chestnut dashboard, HA's Overview (one panel view).
// Frame (header, clock, connection, tab bar), the Home tab (thermostat card, last 12 hours,
// Today and Status), the Schedule tab (tab-schedule.js), the Simulation panel
// (tab-simulation.js, only while the sim entities exist) and the System tab (tab-system.js); the room view (room-view.js) on Home and Simulation, animated only while it
// is on screen (`active`). Layout from docs/design-mockups/ha-dashboard/Main.dc.html; the spec wins
// where they differ (no supply-air readout, the wall console's status rules, M2 level holds).
//
// Lifecycle: HA sets `hass` many times a second. The element keeps one Adapter per websocket
// connection (re-resolved on the connection's "ready" after a reconnect and when the entity
// registry changes), one requestAnimationFrame loop (renders when something changed, and once a
// second for the clock) and one interval (history, every 5 min). Both stop in
// disconnectedCallback and start again, once, on reconnect. The e2e tests read `_loops` and
// `_intervals` (live in the whole window, all instances), `_resolves` and `_historyLoads`.
import { styles } from './style.js';
import { TEMPLATE, MODES, FANS, LEVELS, BUCKETS, DASH } from './dashboard-template.js';
import { ScheduleTab, readPeriods, dayBarHtml, dayType, lastPeriod } from './tab-schedule.js';
import { SimulationTab } from './tab-simulation.js';
import { SystemTab } from './tab-system.js';
import { Adapter } from './lib/adapter.js';
import './room-view.js';
import { statusFor, targetLabel, holdKind, levelShouldSend, TargetTaps } from './lib/rules.js';

const DEFAULT_DEVICE = 'Main Thermostat';
const TARGET_MIN = 50;
const TARGET_MAX = 90;
const DEBOUNCE_MS = 1500;
const PENDING_GIVE_UP_MS = 6000; // show the tapped value this long after the write at most
const HISTORY_EVERY_MS = 5 * 60 * 1000;
const HISTORY_HOURS = 12;
const BUCKET_MS = (HISTORY_HOURS * 3600 * 1000) / BUCKETS;
const HISTORY_IDS = ['call_heat', 'call_cool', 'call_fan', 'checked_temperature', 'effective_target'];
const RESOLVE_RETRY_MS = [2000, 5000, 15000, 60000]; // after a failed entity lookup, then every minute
// Live timers across every instance in this window (a leaked loop in a detached element counts).
const live = { loops: 0, intervals: 0 };

const deg = (v) => (v == null ? DASH : `${Math.round(v)}°`);

function fmtMin(ms) {
  const m = Math.max(0, Math.round(ms / 60000));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

// Wall-clock parts in HA's time zone (the house's, which the thermostat's schedule uses), not
// the browser's; the browser's own zone if HA's is unknown or invalid.
const WEEKDAYS = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 0 };
const formatters = new Map(); // one per time zone (a render runs on every HA state change)
function nowParts(timeZone) {
  const d = new Date();
  try {
    let f = formatters.get(timeZone);
    if (!f) {
      f = new Intl.DateTimeFormat('en-US', { timeZone, hour12: false, weekday: 'short', hour: 'numeric', minute: 'numeric' });
      formatters.set(timeZone, f);
    }
    const p = Object.fromEntries(f.formatToParts(d).map((x) => [x.type, x.value]));
    return { day: WEEKDAYS[p.weekday], hour: Number(p.hour) % 24, minute: Number(p.minute) };
  } catch {
    return { day: d.getDay(), hour: d.getHours(), minute: d.getMinutes() };
  }
}

function clockText({ hour, minute }) {
  return `${hour % 12 || 12}:${String(minute).padStart(2, '0')} ${hour >= 12 ? 'pm' : 'am'}`;
}

// rows: [{t, v}] sorted by time (state changes, the first one at or before `start`).
function onBuckets(rows, start, end) {
  const on = new Array(BUCKETS).fill(false);
  let total = 0;
  rows.forEach((r, i) => {
    if (r.v !== 'on') return;
    const a = Math.max(start, r.t);
    const b = Math.min(end, i + 1 < rows.length ? rows[i + 1].t : end);
    if (b <= a) return;
    total += b - a;
    const k0 = Math.floor((a - start) / BUCKET_MS);
    const k1 = Math.min(BUCKETS - 1, Math.floor((b - start - 1) / BUCKET_MS));
    for (let k = k0; k <= k1; k++) on[k] = true;
  });
  return { on, total };
}

// The value in force at the end of each bucket (null before the first reading).
function stepSeries(rows, start) {
  const out = new Array(BUCKETS).fill(null);
  let i = -1;
  for (let k = 0; k < BUCKETS; k++) {
    const t = start + (k + 1) * BUCKET_MS;
    while (i + 1 < rows.length && rows[i + 1].t <= t) i++;
    out[k] = i >= 0 && typeof rows[i].v === 'number' ? rows[i].v : null;
  }
  return out;
}

class ChestnutDashboard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.adoptedStyleSheets = [styles];
    this._config = { device_name: DEFAULT_DEVICE };
    this._hass = null;
    this._adapter = null;
    this._conn = null;
    this._resolved = false;
    this._gen = 0;
    this._tab = 'HOME';
    this._history = null; // null = not loaded yet; {empty: true} or the computed chart
    this._dirty = true;
    this._raf = null;
    this._timer = null;
    this._lastPaint = 0;
    this._todayKey = '';
    // Test-observable counters (e2e: reconnect_rebinds_once); see also _loops / _intervals.
    this._resolves = 0;
    this._historyLoads = 0;
    this._onReady = () => this._resolve();
    this._resolveError = false; // the entity lookup failed; a retry is scheduled
    this._retryTimer = null;
    this._retries = 0;
    this._narrow = window.matchMedia('(max-width: 860px)');
    this._onNarrow = () => { this._syncRoom(); this._dirty = true; };
    this._taps = new TargetTaps({
      ms: DEBOUNCE_MS, giveUpMs: PENDING_GIVE_UP_MS, min: TARGET_MIN, max: TARGET_MAX,
      write: (f) => this._writeTarget(f),
      onFailed: () => { this._dirty = true; },
    });
  }

  setConfig(config) {
    const device = (config && config.device_name) || DEFAULT_DEVICE;
    const changed = device !== this._config.device_name;
    this._config = { ...(config || {}), device_name: device };
    if (changed || !this._built) this._build();
    if (changed && this._adapter) this._unbind();
    this._bind();
  }

  set hass(hass) {
    this._hass = hass;
    this._bind();
    this._dirty = true;
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (!this._built) this._build();
    this._narrow.addEventListener('change', this._onNarrow);
    this._syncRoom();
    this._start();
    this._bind();
  }

  disconnectedCallback() {
    this._narrow.removeEventListener('change', this._onNarrow);
    this._stop();
    // A − / + burst still in its debounce: send it now while the adapter is bound, else drop it.
    this._taps.detach(!!(this._adapter && this._resolved));
    if (this._schedule) this._schedule.detach();
    if (this._system) this._system.detach();
    this._unbind();
  }

  getCardSize() {
    return 12;
  }

  get _loops() {
    return live.loops;
  }

  get _intervals() {
    return live.intervals;
  }

  // ── lifecycle ──────────────────────────────────────────────────────────────────────────
  _start() {
    if (this._raf == null) {
      const tick = (ts) => {
        this._raf = requestAnimationFrame(tick);
        if (this._dirty || ts - this._lastPaint >= 1000) {
          this._dirty = false;
          this._lastPaint = ts;
          this._render();
        }
      };
      this._raf = requestAnimationFrame(tick);
      live.loops++;
    }
    if (this._timer == null) {
      this._timer = setInterval(() => this._loadHistory(), HISTORY_EVERY_MS);
      live.intervals++;
    }
  }

  _stop() {
    if (this._raf != null) {
      cancelAnimationFrame(this._raf);
      this._raf = null;
      live.loops--;
    }
    if (this._timer != null) {
      clearInterval(this._timer);
      this._timer = null;
      live.intervals--;
    }
  }

  // One Adapter per connection; a reconnect ("ready") or a registry change re-resolves it.
  _bind() {
    const hass = this._hass;
    if (!hass || !this.isConnected) return;
    if (!this._adapter || this._conn !== hass.connection) {
      this._unbind();
      this._adapter = new Adapter(hass, { deviceName: this._config.device_name });
      this._conn = hass.connection;
      if (this._conn && this._conn.addEventListener) this._conn.addEventListener('ready', this._onReady);
      this._entitiesRef = hass.entities;
      this._devicesRef = hass.devices;
      this._resolve();
      return;
    }
    this._adapter.hass = hass;
    // A registry change (or a device list that arrives late, or a renamed device) re-resolves.
    if (hass.entities !== this._entitiesRef || hass.devices !== this._devicesRef) {
      this._entitiesRef = hass.entities;
      this._devicesRef = hass.devices;
      this._resolve();
    }
  }

  _unbind() {
    if (this._conn && this._conn.removeEventListener) this._conn.removeEventListener('ready', this._onReady);
    this._conn = null;
    this._adapter = null;
    this._resolved = false;
    this._resolveError = false;
    clearTimeout(this._retryTimer);
    this._retryTimer = null;
    this._retries = 0;
    this._gen++;
  }

  async _resolve() {
    const adapter = this._adapter;
    if (!adapter) return;
    const gen = ++this._gen;
    this._resolves++;
    clearTimeout(this._retryTimer);
    this._retryTimer = null;
    try {
      await adapter.resolve();
    } catch (err) {
      console.warn('chestnut-dashboard: entity lookup failed', err);
      if (gen !== this._gen) return;
      // Say so and try again (2 s, 5 s, 15 s, then every minute), rather than "connecting" forever.
      this._resolveError = true;
      this._dirty = true;
      const ms = RESOLVE_RETRY_MS[Math.min(this._retries++, RESOLVE_RETRY_MS.length - 1)];
      this._retryTimer = setTimeout(() => { this._retryTimer = null; this._resolve(); }, ms);
      return;
    }
    if (gen !== this._gen) return;
    this._resolveError = false;
    this._retries = 0;
    this._resolved = true;
    this._dirty = true;
    this._loadHistory();
  }

  async _loadHistory() {
    const adapter = this._adapter;
    if (!adapter || !this._resolved) return;
    const gen = this._gen;
    let res = null;
    try {
      res = await adapter.history(HISTORY_IDS, HISTORY_HOURS);
    } catch (err) {
      console.warn('chestnut-dashboard: history failed', err);
    }
    if (gen !== this._gen) return;
    this._historyLoads++;
    this._history = this._chart(res);
    this._paintRuntime();
  }

  _chart(res) {
    if (!res || HISTORY_IDS.every((k) => !(res[k] || []).length)) return { empty: true };
    const end = Date.now();
    const start = end - HISTORY_HOURS * 3600 * 1000;
    const sorted = (k) => (res[k] || []).slice().sort((a, b) => a.t - b.t);
    const heat = onBuckets(sorted('call_heat'), start, end);
    const cool = onBuckets(sorted('call_cool'), start, end);
    const fan = onBuckets(sorted('call_fan'), start, end);
    const room = stepSeries(sorted('checked_temperature'), start);
    const target = stepSeries(sorted('effective_target'), start);
    const vals = [...room, ...target].filter((v) => v != null);
    let lo = vals.length ? Math.min(...vals) - 1 : 60;
    let hi = vals.length ? Math.max(...vals) + 1 : 80;
    if (hi - lo < 4) { const mid = (hi + lo) / 2; lo = mid - 2; hi = mid + 2; }
    const pts = (s) => s.map((v, k) => (v == null ? null : `${k + 0.5},${(30 - ((v - lo) / (hi - lo)) * 30).toFixed(2)}`)).filter(Boolean).join(' ');
    return { empty: false, heat, cool, fan, roomPts: pts(room), targetPts: pts(target) };
  }

  // ── DOM ────────────────────────────────────────────────────────────────────────────────
  _build() {
    this._built = true;
    this.shadowRoot.innerHTML = TEMPLATE(this._config.device_name);
    const root = this.shadowRoot;
    this._el = {};
    root.querySelectorAll('[id]').forEach((n) => { this._el[n.id] = n; });
    root.querySelectorAll('[data-testid]').forEach((n) => { this._el[n.dataset.testid] = n; });
    root.querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => this._pickTab(b.dataset.tab)));
    root.querySelectorAll('[data-go]').forEach((b) => b.addEventListener('click', () => this._pickTab(b.dataset.go)));
    this._el.minus.addEventListener('click', () => this._step(-1));
    this._el.plus.addEventListener('click', () => this._step(1));
    for (const [k, , mode] of MODES) this._el[`mode-${k}`].addEventListener('click', () => this._call('climate', 'set_hvac_mode', 'main_thermostat', { hvac_mode: mode }));
    for (const [k] of FANS) this._el[`fan-${k}`].addEventListener('click', () => this._setFan(k));
    for (const [k, , option] of LEVELS) this._el[`level-${k}`].addEventListener('click', () => this._pickLevel(option));
    this._el.resume.addEventListener('click', () => this._call('button', 'press', 'resume_schedule'));
    this._simTab = root.querySelector('[data-tab="SIMULATION"]');
    this._schedule = new ScheduleTab(root, this);
    this._simulation = new SimulationTab(root, this);
    this._system = new SystemTab(root, this);
    this._todayKey = '';
    this._applyTab();
    this._paintRuntime();
  }

  _pickTab(tab) {
    this._tab = tab;
    this._applyTab();
  }

  _applyTab() {
    const root = this.shadowRoot;
    root.querySelectorAll('[data-tab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === this._tab)));
    root.querySelectorAll('[data-views]').forEach((n) => { n.hidden = !n.dataset.views.split(' ').includes(this._tab); });
    this._syncRoom();
    this._dirty = true;
  }

  // The room animates only while it is on screen: Home or Simulation, wider than a phone (the
  // room view itself also pauses while the page is hidden or the element is detached).
  _syncRoom() {
    const room = this._el && this._el.room;
    if (room) room.active = !room.hidden && !this._narrow.matches;
  }

  // ── controls ───────────────────────────────────────────────────────────────────────────
  // For the tab modules: the adapter once resolved (else null), and a service call.
  adapter() {
    return this._resolved ? this._adapter : null;
  }

  call(domain, service, objId, data) {
    this._call(domain, service, objId, data);
  }

  _call(domain, service, objId, data) {
    if (!this._adapter || !this._resolved) return;
    this._adapter.call(domain, service, objId, data).catch((err) => console.warn('chestnut-dashboard:', service, err));
  }

  _baseTarget() {
    const a = this._adapter;
    if (!a) return null;
    const eff = a.num('effective_target');
    return eff != null ? Math.round(eff) : (a.num('set_target') != null ? Math.round(a.num('set_target')) : null);
  }

  _step(delta) {
    const a = this._adapter;
    if (!a || !this._resolved || !a.online()) return;
    // As on the wall screen: − / + do nothing in Off (a write would start a hold, or set the
    // manual target, that nobody sees until the mode changes).
    if (a.str('main_thermostat') === 'off') return;
    const base = this._baseTarget();
    if (base == null) return;
    this._taps.step(delta, base, Date.now());
    this._dirty = true;
    this._render();
  }

  // A promise: TargetTaps undoes the write if it rejects. The thermostat may have gone offline
  // since the last tap; HA would drop that call without an error, so it isn't sent.
  _writeTarget(f) {
    const a = this._adapter;
    if (!a || !this._resolved || !a.online()) return Promise.reject(new Error('thermostat offline'));
    return a.setTargetF(f).catch((err) => {
      console.warn('chestnut-dashboard: set_target failed', err);
      throw err;
    });
  }

  _setFan(key) {
    const modes = (this._adapter && this._adapter.attr('main_thermostat', 'fan_modes')) || [];
    const match = modes.find((m) => String(m).toLowerCase() === key) || key;
    this._call('climate', 'set_fan_mode', 'main_thermostat', { fan_mode: match });
  }

  _pickLevel(option) {
    const a = this._adapter;
    if (!a) return;
    const send = levelShouldSend({ picked: option, current: a.str('comfort_level'), manual: a.on('manual_target') === true });
    if (send) this._call('select', 'select_option', 'comfort_level', { option });
  }

  // ── render ─────────────────────────────────────────────────────────────────────────────
  _text(id, value) {
    const n = this._el[id];
    if (n && n.textContent !== value) n.textContent = value;
  }

  _render() {
    if (!this._built) return;
    const a = this._adapter;
    const hass = this._hass;
    const ready = !!(a && this._resolved);
    const online = ready && a.online();
    const now = nowParts(hass && hass.config ? hass.config.time_zone : undefined);
    this._text('clock', clockText(now));
    const haUp = !!(hass && hass.connected !== false);
    const missing = ready && a.found === false;
    this._text('conn', !haUp ? '○ reconnecting' : online ? '● connected' : missing ? '○ thermostat not found' : ready ? '○ thermostat offline' : '○ connecting');

    // The Simulation panel exists only while the sim does, and never at phone width.
    const sim = ready && a.simPresent();
    this._simTab.hidden = !sim;
    if ((!sim || this._narrow.matches) && this._tab === 'SIMULATION') this._pickTab('HOME');

    // The tapped value shows until the device reports it (or gives up); never mid-burst.
    const eff = online ? a.num('effective_target') : null;
    this._taps.settle(eff != null ? Math.round(eff) : null, Date.now());
    const v = online ? this._read(a) : null;
    this._renderThermostat(v, ready, missing);
    const room = this._el.room;
    const roomAdapter = ready ? a : null;
    if (room.adapter !== roomAdapter) room.adapter = roomAdapter;
    this._renderToday(online ? a : null, now);
    this._renderStatus(v, haUp);
    if (this._tab === 'SCHEDULE') this._schedule.render(ready ? a : null, now);
    if (this._tab === 'SIMULATION') this._simulation.render(ready ? a : null);
    if (this._tab === 'SYSTEM') this._system.render(ready ? a : null);
  }

  // Everything the cards show, from live entities only (called only while the climate is online).
  _read(a) {
    const mode = a.str('main_thermostat');
    const action = a.attr('main_thermostat', 'hvac_action');
    const eff = a.num('effective_target');
    const lo = a.num('effective_low');
    const hi = a.num('effective_high');
    const band = mode === 'heat_cool' && this._taps.pending == null && lo != null && hi != null && hi - lo > 2.5;
    let targetText;
    if (this._taps.pending != null) targetText = `${this._taps.pending}°`;
    else if (band) targetText = `${Math.round(lo)}–${Math.round(hi)}°`;
    else targetText = deg(eff);
    let actionTarget = targetText;
    if (band && action === 'heating') actionTarget = deg(lo);
    if (band && action === 'cooling') actionTarget = deg(hi);

    let minutesSoFar = null;
    const el = a.num('action_elapsed');
    if (el != null) {
      const unit = a.attr('action_elapsed', 'unit_of_measurement');
      const sec = el * (unit === 'min' ? 60 : unit === 'h' ? 3600 : 1);
      const at = a.updatedMs('action_elapsed');
      minutesSoFar = (sec + (at != null ? Math.max(0, Date.now() - at) / 1000 : 0)) / 60;
    }
    const wait = a.str('call_wait_reason');
    const s = {
      mode, action,
      sensorFault: a.on('sensor_fault') === true,
      interlockFault: a.on('interlock_fault') === true,
      callHeat: a.on('call_heat') === true,
      callCool: a.on('call_cool') === true,
      callFan: a.on('call_fan') === true,
      waitReason: wait && !['unknown', 'unavailable'].includes(wait) ? wait : '',
      targetText: actionTarget,
      minutesSoFar,
    };
    const scheduleOn = a.on('schedule_enabled');
    const schedStatus = a.str('schedule_status');
    return {
      ...s,
      sensorFaultRaw: a.on('sensor_fault'),
      interlockFaultRaw: a.on('interlock_fault'),
      status: statusFor(s),
      display: mode === 'off' && this._taps.pending == null ? 'OFF' : targetText,
      level: a.str('comfort_level'),
      hold: a.on('schedule_hold') === true,
      manual: a.on('manual_target') === true,
      kind: holdKind(schedStatus),
      fanMode: a.attr('main_thermostat', 'fan_mode'),
      comfort: a.num('comfort_target'),
      room: a.num('checked_temperature'),
      humidity: a.num('room_humidity'),
      eff,
      schedLine: scheduleOn === false ? 'Schedule off' : schedStatus && !['unknown', 'unavailable', ''].includes(schedStatus) ? schedStatus : DASH,
    };
  }

  _renderThermostat(v, ready, missing) {
    const el = this._el;
    const live = !!v;
    this._text('target', live ? v.display : DASH);
    this._text('tlabel', live ? targetLabel({ mode: v.mode, level: v.level, hold: v.hold, holdKind: v.kind, manual: v.manual }) : 'TARGET');
    let sub = '';
    if (live) {
      if (v.manual) sub = 'schedule off';
      else if (v.hold) sub = 'until the next period';
      else if (v.level === 'Eco' && v.comfort != null) sub = `comfort ${deg(v.comfort)}`;
    }
    this._text('tgt-sub', sub);
    const st = live ? v.status : null;
    this._text('status-mark', live ? st.mark : '·');
    let word = 'CONNECTING';
    let why = this._resolveError ? "Couldn't read Home Assistant's entity list · retrying" : '';
    if (missing) {
      word = 'NOT FOUND';
      why = `No device named "${this._config.device_name}" in Home Assistant (dashboard device_name)`;
    } else if (ready) {
      word = 'OFFLINE';
      why = 'The thermostat is not connected to Home Assistant';
    }
    this._text('status-word', live ? st.word : word);
    this._text('status-sub', live ? st.sub : why);
    const color = live ? st.color : '#b4b4b4';
    if (el['status-word'].parentNode.style.color !== color) el['status-word'].parentNode.style.color = color;

    const uiMode = live ? (v.mode === 'heat_cool' ? 'auto' : v.mode) : null;
    for (const [k] of MODES) this._press(`mode-${k}`, uiMode === k, live);
    const fan = live && v.fanMode ? String(v.fanMode).toLowerCase() : null;
    for (const [k] of FANS) this._press(`fan-${k}`, fan === k, live);
    for (const [k, , option] of LEVELS) this._press(`level-${k}`, live && !v.manual && v.level === option, live);
    el.minus.disabled = !live || v.mode === 'off';
    el.plus.disabled = !live || v.mode === 'off';
    const sched = live ? v.schedLine : DASH;
    this._text('sched-line', sched);
    this._text('sched-foot', sched);
    el.resume.hidden = !(live && v.hold);
  }

  _press(id, on, enabled) {
    const n = this._el[id];
    const val = String(!!on);
    if (n.getAttribute('aria-pressed') !== val) n.setAttribute('aria-pressed', val);
    n.disabled = !enabled;
  }

  _renderToday(a, now) {
    const day = dayType(now.day);
    this._text('today-label', `TODAY · ${day.toUpperCase()}`);
    this._el['now-mark'].style.left = `${(((now.hour * 60 + now.minute) / 1440) * 100).toFixed(1)}%`;
    const periods = a ? readPeriods(a, day) : null;
    // Before today's first period, yesterday's last one is still in force.
    const before = a ? lastPeriod(readPeriods(a, dayType((now.day + 6) % 7))) : null;
    const off = !!a && a.on('schedule_enabled') === false;
    const key = JSON.stringify([periods, before, off]);
    if (key === this._todayKey) return;
    this._todayKey = key;
    const bar = this._el.daybar;
    bar.classList.toggle('off', off);
    if (!periods) {
      bar.innerHTML = `<span class="empty" style="padding-left: 0">${DASH}</span>`;
      return;
    }
    bar.innerHTML = dayBarHtml(periods, before);
  }

  _renderStatus(v, haUp) {
    if (!v) {
      for (const id of ['st-equip', 'st-lock', 'st-sensor']) this._text(id, DASH);
    } else {
      this._text('st-equip', v.callHeat ? 'furnace firing' : v.callCool ? 'ac running' : v.callFan ? 'fan on' : 'all off');
      this._text('st-lock', v.interlockFaultRaw == null ? DASH : v.interlockFault ? '⚠ tripped' : '✓ armed');
      this._text('st-sensor', v.sensorFaultRaw == null ? DASH : v.sensorFault ? '⚠ fault' : '✓ ok');
    }
    this._text('st-ha', haUp ? '● connected' : '○ reconnecting');
  }

  _paintRuntime() {
    if (!this._built) return;
    const h = this._history;
    const el = this._el;
    el['rt-chart'].hidden = !h || h.empty;
    el['rt-empty'].hidden = !!h && !h.empty;
    this._text('rt-empty', !h ? 'loading…' : h.empty ? 'no data yet' : '');
    if (!h || h.empty) {
      for (const k of ['tot-heat', 'tot-cool', 'tot-fan']) this._text(k, DASH);
      return;
    }
    el['pl-room'].setAttribute('points', h.roomPts);
    el['pl-target'].setAttribute('points', h.targetPts);
    const paint = (k, series, color) => {
      this._text(`tot-${k}`, fmtMin(series.total));
      [...el[`bars-${k}`].children].forEach((bar, i) => {
        const on = series.on[i];
        bar.style.height = on ? '8px' : '2px';
        bar.style.background = on ? color : '#202020';
      });
    };
    paint('heat', h.heat, '#da5c2c');
    paint('cool', h.cool, '#2a7fff');
    paint('fan', h.fan, '#b4b4b4');
  }
}

if (!customElements.get('chestnut-dashboard')) {
  customElements.define('chestnut-dashboard', ChestnutDashboard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'chestnut-dashboard')) {
  window.customCards.push({
    type: 'chestnut-dashboard',
    name: 'Chestnut dashboard',
    description: 'The Main Thermostat dashboard (Axiom).',
  });
}
