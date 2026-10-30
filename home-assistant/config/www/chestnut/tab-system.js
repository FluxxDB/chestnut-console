// The System tab: Safety (minimum-timer bars, interlock, sensor, editable timers, Clear
// interlock fault), Alerts (three HA input_boolean helpers), Wall screen, Device and the Event log.
// Mockup Main.dc.html, System tab; spec "System tab".
// - Bars: rules.safetyRows from the device's action_elapsed (published every 30 s, interpolated
//   here) and the relays (call_heat / call_cool); the startup delay and changeover lockout show
//   as call_wait_reason text.
// - Timers: number.set_value clamped to each entity's min/max (minutes).
// - Alerts: input_boolean.chestnut_alert_* are HA helpers (configuration.yaml), not device
//   entities, so they are read from hass.states and toggled directly.
// - Wall screen, IP, uptime, Wi-Fi signal and Clock Valid exist only on the Tab5; on the host sim
//   they show "—" / disabled controls.
// - Event log: adapter.logbook over the last 24 h, newest first, at most 40 rows; reloaded when a
//   watched entity changes (after the recorder has committed) and every minute while shown.
import { safetyRows, eventText } from './lib/rules.js';

const DASH = '—';
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const DEAD = new Set(['unavailable', 'unknown', '']);
const PENDING_GIVE_UP_MS = 5000;
const LOG_IDS = ['call_heat', 'call_cool', 'sensor_fault', 'interlock_fault', 'schedule_hold', 'schedule_period'];
const LOG_HOURS = 24;
const LOG_MAX = 40;
const LOG_AFTER_CHANGE_MS = 2500; // the recorder writes in batches (commit interval)
const LOG_RETRIES = 6; // a change HA shows but the logbook doesn't have yet: ask again
const LOG_EVERY_MS = 60 * 1000;

const SAFETY = [
  ['heat-run', 'furnace min run', 'heatRun', '#da5c2c'],
  ['heat-off', 'furnace min off', 'heatOff', '#7e7e7e'],
  ['cool-run', 'ac min run', 'coolRun', '#2a7fff'],
  ['cool-off', 'ac min off', 'coolOff', '#7e7e7e'],
];
const TIMERS = [
  ['heat_min_run', 'furnace min run'],
  ['heat_min_off', 'furnace min off'],
  ['cool_min_run', 'ac min run'],
  ['cool_min_off', 'ac min off'],
  ['changeover_lockout', 'auto changeover lockout'],
];
const ALERTS = [
  ['sensor_fault', 'sensor fault'],
  ['interlock_fault', 'interlock fault'],
  ['offline', 'thermostat offline 10 min'],
];
const SCREEN = [
  ['scr-bright', 'screen_brightness', 'brightness in use'],
  ['scr-dim', 'dim_brightness', 'dim brightness'],
];
const DEVICE = [['name', 'name'], ['ip', 'address'], ['firmware', 'firmware'], ['wifi', 'wi-fi'], ['uptime', 'uptime'], ['clock', 'clock']];
const KIND_STYLE = { fault: 'color: var(--cn-text); font-weight: 700', heat: 'color: var(--cn-ember)', cool: 'color: var(--cn-blue)', '': 'color: var(--cn-text-2)' };

export const SYSTEM_CSS = `
  .sys-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 24px; }
  .srow { display: flex; flex-direction: column; gap: 4px; }
  .track { height: 2px; background: var(--cn-hairline); }
  .track > div { height: 2px; width: 0; }
  .sub-block { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--cn-hairline); padding-top: 12px; }
  .kv.ctl-row { align-items: center; }
  .num { width: 64px; min-height: 36px; background: #000000; color: var(--cn-text); border: 1px solid var(--cn-outline); border-radius: 2px; padding: 0 8px; font: inherit; font-size: 13px; box-sizing: border-box; color-scheme: dark; }
  .ghost { min-height: 44px; background: transparent; color: var(--cn-text); border: 1px solid var(--cn-outline); border-radius: 2px; font: inherit; font-size: 14px; cursor: pointer; }
  .ghost:disabled { color: var(--cn-label); border-color: var(--cn-hairline); opacity: 1; cursor: not-allowed; }
  .sys-grid input[type="range"]:disabled { opacity: 0.4; }
  .log-card { grid-column: 1 / -1; }
  .log { background: #000000; border: 1px solid var(--cn-hairline); border-radius: 2px; padding: 12px; display: flex; flex-direction: column; gap: 2px; font-size: 12px; max-height: 220px; overflow-y: auto; }
  .log > div { display: flex; gap: 16px; }
  .log .when { color: var(--cn-label); flex: 0 0 104px; }
`;

const kv = (id, label) => `<div class="kv"><span>${label}</span><span data-testid="${id}">${DASH}</span></div>`;

export const SYSTEM_HTML = `
  <div class="sys-grid" data-views="SYSTEM">
    <section class="card" data-testid="safety" aria-label="Safety">
      <span class="label">SAFETY</span>
      ${SAFETY.map(([id, label]) => `
      <div class="srow"><div class="kv"><span>${label}</span><span data-testid="safety-${id}-val">${DASH}</span></div>
        <div class="track"><div data-testid="safety-${id}-bar"></div></div></div>`).join('')}
      ${kv('safety-interlock-val', 'interlock')}
      ${kv('safety-sensor-val', 'temperature sensor')}
      ${kv('safety-wait-val', 'waiting')}
      <div class="sub-block">
        <span class="label">TIMERS · MINUTES</span>
        ${TIMERS.map(([obj, label]) => `<label class="kv ctl-row"><span>${label}</span><input type="number" class="num" data-testid="timer-${obj}" aria-label="${label} (minutes)"></label>`).join('')}
      </div>
      <button type="button" class="ghost" data-testid="clear-interlock" disabled>Clear interlock fault</button>
      <span class="small" data-testid="clear-note" style="color: var(--cn-label)"></span>
    </section>
    <section class="card" aria-label="Alerts">
      <span class="label">ALERTS · HOME ASSISTANT APP</span>
      ${ALERTS.map(([k, label]) => `<div class="kv ctl-row"><span>${label}</span><button type="button" class="switch" role="switch" aria-checked="false" aria-label="Alert: ${label}" data-testid="alert-${k}">${DASH}</button></div>`).join('')}
      <span class="small" style="color: var(--cn-label)">push to your phone through the HA app</span>
    </section>
    <section class="card" aria-label="Wall screen" style="gap: 16px">
      <span class="label">WALL SCREEN</span>
      ${SCREEN.map(([id, , label]) => `
      <div class="ctl"><label for="${id}"><span>${label}</span><b data-testid="${id}-val">${DASH}</b></label>
        <input type="range" id="${id}" data-testid="${id}" disabled></div>`).join('')}
      <div class="kv ctl-row"><span>dark theme<br><span style="color: var(--cn-label)">follows sunset and sunrise</span></span>
        <button type="button" class="switch" role="switch" aria-checked="false" aria-label="Dark theme" data-testid="dark-theme" disabled>${DASH}</button></div>
    </section>
    <section class="card" aria-label="Device">
      <span class="label">DEVICE</span>
      ${DEVICE.map(([k, label]) => kv(`dev-${k}`, label)).join('')}
    </section>
    <section class="card log-card" aria-label="Event log">
      <span class="label">EVENT LOG</span>
      <div class="log" data-testid="event-log"><span class="empty">loading…</span></div>
    </section>
  </div>`;

function fmtUptime(s) {
  const t = Math.max(0, Math.floor(s));
  const d = Math.floor(t / 86400);
  const h = Math.floor((t % 86400) / 3600);
  const m = Math.floor((t % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m ${t % 60}s`;
}

const SECONDS = { s: 1, min: 60, h: 3600, d: 86400 };

export class SystemTab {
  // host: the dashboard (adapter(), call(domain, service, objId, data), hass).
  constructor(root, host) {
    this.root = root;
    this.host = host;
    this.q = (id) => root.querySelector(`[data-testid="${id}"]`);
    this.timers = TIMERS.map(([objId]) => {
      const c = { objId, el: this.q(`timer-${objId}`), pending: null, until: 0 };
      c.el.addEventListener('change', () => this.writeTimer(c));
      return c;
    });
    this.clear = this.q('clear-interlock');
    this.clearNote = this.q('clear-note');
    // The logic drops the latch only once the longer min off since the trip has passed (an early
    // press is remembered, a second one ignored): after a press, say so and hold the button until
    // the latch drops, or that wait plus a minute (a press that never arrived can be repeated).
    this.clearUntil = 0;
    this.clear.addEventListener('click', () => {
      const a = this.host.adapter();
      const offMin = Math.max(a ? a.num('heat_min_off') || 0 : 0, a ? a.num('cool_min_off') || 0 : 0, 5);
      this.clearUntil = Date.now() + (offMin + 1) * 60000;
      this.host.call('button', 'press', 'clear_interlock_fault');
      this.render(a);
    });
    this.alerts = ALERTS.map(([k]) => {
      const c = { entityId: `input_boolean.chestnut_alert_${k}`, el: this.q(`alert-${k}`) };
      c.el.addEventListener('click', () => {
        const hass = this.host.hass;
        if (hass && hass.states[c.entityId]) {
          hass.callService('input_boolean', 'toggle', { entity_id: c.entityId }).catch((e) => console.warn('chestnut-dashboard:', c.entityId, e));
        }
      });
      return c;
    });
    this.screen = SCREEN.map(([id, objId]) => {
      const c = { objId, el: this.q(id), val: this.q(`${id}-val`), dragging: false, pending: null, until: 0 };
      c.el.addEventListener('pointercancel', () => { c.dragging = false; });
      c.el.addEventListener('input', () => { c.dragging = true; this.text(c.val, `${c.el.value}%`); });
      c.el.addEventListener('change', () => {
        c.dragging = false;
        c.pending = Number(c.el.value);
        c.until = Date.now() + PENDING_GIVE_UP_MS;
        this.host.call('number', 'set_value', objId, { value: c.pending });
      });
      return c;
    });
    this.dark = this.q('dark-theme');
    this.dark.addEventListener('click', () => this.host.call('switch', 'toggle', 'dark_theme'));
    this.log = this.q('event-log');
    this.logState = { adapter: null, key: null, timer: null, loadedAt: 0, loading: false, html: '', retries: 0 };
  }

  text(n, value) {
    if (n.textContent !== value) n.textContent = value;
  }

  // The dashboard is going away: no more logbook calls from a detached element.
  detach() {
    clearTimeout(this.logState.timer);
    this.logState.timer = null;
    this.logState.adapter = null;
  }

  writeTimer(c) {
    const a = this.host.adapter();
    const v = Number(c.el.value);
    if (!a || c.el.value === '' || !Number.isFinite(v)) return;
    const lo = a.attr(c.objId, 'min');
    const hi = a.attr(c.objId, 'max');
    const step = a.attr(c.objId, 'step') || 1;
    let w = Math.round(v / step) * step;
    if (typeof lo === 'number') w = Math.max(lo, w);
    if (typeof hi === 'number') w = Math.min(hi, w);
    c.pending = w;
    c.until = Date.now() + PENDING_GIVE_UP_MS;
    c.el.value = String(w);
    this.host.call('number', 'set_value', c.objId, { value: w });
  }

  // a: the resolved adapter, else null (everything shows "—").
  render(a) {
    const now = Date.now();
    const online = !!a && a.online();
    this.renderSafety(online ? a : null, now);
    this.renderTimers(a, now);
    this.renderAlerts();
    this.renderScreen(a, now);
    this.renderDevice(a, online, now);
    this.renderLog(a, now);
  }

  renderSafety(a, now) {
    const minutes = (objId) => (a ? a.num(objId) : null);
    let elapsedS = null;
    if (a) {
      const el = a.num('action_elapsed');
      const unit = a.attr('action_elapsed', 'unit_of_measurement') || 's';
      if (el != null && SECONDS[unit]) elapsedS = el * SECONDS[unit];
    }
    const rows = safetyRows({
      action: a ? a.attr('main_thermostat', 'hvac_action') : null,
      callHeat: a ? a.on('call_heat') : null,
      callCool: a ? a.on('call_cool') : null,
      interlockFault: a ? a.on('interlock_fault') : null,
      actionElapsedS: elapsedS,
      publishedAtMs: a ? a.updatedMs('action_elapsed') : null,
      nowMs: now,
      mins: { heatRun: minutes('heat_min_run'), heatOff: minutes('heat_min_off'), coolRun: minutes('cool_min_run'), coolOff: minutes('cool_min_off') },
    });
    for (const [id, , key, color] of SAFETY) {
      const r = rows[key];
      this.text(this.q(`safety-${id}-val`), r.val);
      const bar = this.q(`safety-${id}-bar`);
      const width = `${(r.frac * 100).toFixed(1)}%`;
      if (bar.style.width !== width) bar.style.width = width;
      if (bar.style.background !== color) bar.style.background = color;
    }
    const lock = a ? a.on('interlock_fault') : null;
    const sensor = a ? a.on('sensor_fault') : null;
    this.text(this.q('safety-interlock-val'), lock == null ? DASH : lock ? '⚠ tripped' : '✓ armed');
    this.text(this.q('safety-sensor-val'), sensor == null ? DASH : sensor ? '⚠ fault' : '✓ ok');
    const wait = a ? a.str('call_wait_reason') : null;
    this.text(this.q('safety-wait-val'), wait == null || DEAD.has(wait) ? (a ? 'none' : DASH) : wait);
    if (lock !== true || now > this.clearUntil) this.clearUntil = 0;
    const asked = this.clearUntil > 0;
    this.clear.disabled = lock !== true || asked;
    this.text(this.clearNote, lock !== true ? '' : asked
      ? 'clear requested · it takes effect once the furnace and ac min off times since the trip have passed'
      : 'takes effect once the furnace and ac min off times since the trip have passed');
  }

  renderTimers(a, now) {
    const focused = this.root.activeElement;
    for (const c of this.timers) {
      const cur = a ? a.num(c.objId) : null;
      for (const k of ['min', 'max', 'step']) {
        const v = a ? a.attr(c.objId, k) : null;
        if (v != null && c.el.getAttribute(k) !== String(v)) c.el.setAttribute(k, String(v));
      }
      if (c.pending != null && (cur === c.pending || now > c.until)) c.pending = null;
      c.el.disabled = cur == null;
      const v = c.pending ?? cur;
      const shown = v == null ? '' : String(v);
      if (focused !== c.el && c.el.value !== shown) c.el.value = shown;
    }
  }

  renderAlerts() {
    const hass = this.host.hass;
    for (const c of this.alerts) {
      const s = hass && hass.states[c.entityId];
      const on = s && !DEAD.has(s.state) ? s.state === 'on' : null;
      const checked = String(on === true);
      if (c.el.getAttribute('aria-checked') !== checked) c.el.setAttribute('aria-checked', checked);
      this.text(c.el, on == null ? DASH : on ? 'ON' : 'OFF');
      c.el.disabled = on == null;
    }
  }

  renderScreen(a, now) {
    for (const c of this.screen) {
      const cur = a ? a.num(c.objId) : null;
      const r = a ? a.rangeF(c.objId) : null;
      if (r) for (const k of ['min', 'max', 'step']) if (c.el.getAttribute(k) !== String(r[k])) c.el.setAttribute(k, String(r[k]));
      if (c.pending != null && (cur === c.pending || now > c.until)) c.pending = null;
      c.el.disabled = cur == null || !r;
      if (c.el.disabled) c.dragging = false; // a drag cut short never fires change
      if (c.dragging) continue;
      const v = c.pending ?? cur;
      if (v != null && c.el.value !== String(v)) c.el.value = String(v);
      this.text(c.val, v == null ? DASH : `${Math.round(v)}%`);
    }
    const dark = a ? a.on('dark_theme') : null;
    const checked = String(dark === true);
    if (this.dark.getAttribute('aria-checked') !== checked) this.dark.setAttribute('aria-checked', checked);
    this.text(this.dark, dark == null ? DASH : dark ? 'ON' : 'OFF');
    this.dark.disabled = dark == null;
  }

  renderDevice(a, online, now) {
    const dev = a ? a.deviceEntry() : null;
    this.text(this.q('dev-name'), dev ? dev.name_by_user || dev.name || DASH : a ? a.deviceName : DASH);
    const ip = a ? a.str('ip_address') : null;
    this.text(this.q('dev-ip'), ip && !DEAD.has(ip) ? ip : DASH);
    this.text(this.q('dev-firmware'), (dev && dev.sw_version) || DASH);
    const rssi = a ? a.num('wi_fi_signal') : null;
    this.text(this.q('dev-wifi'), rssi == null ? DASH : `${Math.round(rssi)} dBm`);
    let up = null;
    if (a && online) {
      const v = a.num('uptime');
      const mult = SECONDS[a.attr('uptime', 'unit_of_measurement') || 's'];
      const at = a.updatedMs('uptime');
      if (v != null && mult) up = v * mult + (at != null ? Math.max(0, now - at) / 1000 : 0);
    }
    this.text(this.q('dev-uptime'), up == null ? DASH : fmtUptime(up));
    const clock = a ? a.on('clock_valid') : null;
    this.text(this.q('dev-clock'), clock == null ? DASH : clock ? 'valid' : 'not set');
  }

  // ── event log ──────────────────────────────────────────────────────────────────────────
  renderLog(a, now) {
    const L = this.logState;
    if (a !== L.adapter) {
      L.adapter = a;
      L.key = null;
      L.loadedAt = 0;
      clearTimeout(L.timer);
      L.timer = null;
      if (!a) this.paintLog(null);
    }
    if (!a) return;
    const key = LOG_IDS.map((o) => `${a.str(o)}@${a.updatedMs(o)}`).join('|');
    if (L.key === null) {
      L.key = key;
      L.retries = 0;
      this.loadLog(a);
    } else if (key !== L.key) {
      L.key = key;
      L.retries = 0;
      this.scheduleLog(a, LOG_AFTER_CHANGE_MS);
    } else if (!L.timer && !L.loading && now - L.loadedAt > LOG_EVERY_MS) {
      this.loadLog(a);
    }
  }

  scheduleLog(a, ms) {
    const L = this.logState;
    clearTimeout(L.timer);
    L.timer = setTimeout(() => { L.timer = null; this.loadLog(a); }, ms);
  }

  async loadLog(a) {
    const L = this.logState;
    L.loading = true;
    L.loadedAt = Date.now();
    let rows = null;
    try {
      rows = await a.logbook(LOG_IDS, LOG_HOURS);
    } catch (err) {
      console.warn('chestnut-dashboard: logbook failed', err);
    }
    L.loading = false;
    if (a !== L.adapter || !rows) return;
    this.paintLog(rows);
    // The newest change HA shows should be in the logbook; if the recorder hasn't written it
    // yet, ask again shortly (a few times). Only for a change inside the logbook's window: on a
    // quiet system the newest change is older than that and never shows up.
    const newestShown = Math.max(0, ...LOG_IDS.map((o) => a.updatedMs(o) || 0));
    const newestLogged = rows.length ? rows[0].t : 0;
    const windowStart = Date.now() - LOG_HOURS * 3600 * 1000;
    if (newestShown > windowStart && newestShown > newestLogged + 1000 && L.retries < LOG_RETRIES && !L.timer) {
      L.retries++;
      this.scheduleLog(a, LOG_AFTER_CHANGE_MS);
    }
  }

  paintLog(rows) {
    const L = this.logState;
    let html;
    if (!rows) {
      html = `<span class="empty">${DASH}</span>`;
    } else {
      // A state seen again after the thermostat was offline (or HA restarted) isn't a change.
      const last = {};
      const changes = [];
      for (const r of rows.slice().reverse()) {
        if (r.state === 'unavailable' || r.state === 'unknown') {
          if (r.state === 'unavailable') changes.push(r);
          continue;
        }
        if (last[r.objId] === r.state) continue;
        last[r.objId] = r.state;
        changes.push(r);
      }
      const items = [];
      for (const r of changes.reverse()) {
        const e = eventText(r.objId, r.state);
        if (!e) continue;
        items.push(`<div data-event data-t="${r.t}"><span class="when">${esc(this.when(r.t))}</span><span style="${KIND_STYLE[e.kind] || KIND_STYLE['']}">${esc(e.msg)}</span></div>`);
        if (items.length >= LOG_MAX) break;
      }
      html = items.length ? items.join('') : '<span class="empty">no events yet</span>';
    }
    if (html === L.html) return;
    L.html = html;
    this.log.innerHTML = html;
  }

  // "9:15 pm" today, "Oct 28 9:15 pm" before; in HA's time zone (the house's), else the browser's.
  when(t) {
    const hass = this.host.hass;
    const zone = hass && hass.config ? hass.config.time_zone : undefined;
    const fmt = (x, opts) => {
      try {
        return new Intl.DateTimeFormat('en-US', { timeZone: zone, ...opts }).format(new Date(x));
      } catch {
        return new Intl.DateTimeFormat('en-US', opts).format(new Date(x));
      }
    };
    const clock = fmt(t, { hour: 'numeric', minute: '2-digit' }).replace(/\s?AM$/, ' am').replace(/\s?PM$/, ' pm');
    const day = (x) => fmt(x, { year: 'numeric', month: 'short', day: 'numeric' });
    return day(t) === day(Date.now()) ? clock : `${fmt(t, { month: 'short', day: 'numeric' })} ${clock}`;
  }
}
