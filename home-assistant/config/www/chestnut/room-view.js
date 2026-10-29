// <chestnut-room-view>: the top-down room with the live heat field, the outdoor column (AC unit)
// and the equipment closet (cooling coil, interlock, furnace, blower). Layout from
// docs/design-mockups/ha-dashboard/Main.dc.html; the spec wins where they differ (no supply-air
// readout, the field mean equals checked_temperature, the field freezes on a sensor fault).
//
// Properties: `adapter` (a resolved Adapter, or null) and `active` (the dashboard's view shows
// the room). The requestAnimationFrame loop runs only while active, connected and the page is
// visible (visibilitychange). HeatField's per-step terms are not dt-scaled, so the field is
// stepped at a fixed 30 Hz from accumulated real time, whatever the display's refresh rate.
// The e2e tests read `data-mean` (the field mean), `data-on` on the equipment boxes, `_frames`
// (requestAnimationFrame callbacks, this instance) and `_loops` (live loops, whole window).
import { styles } from './style.js';
import { HeatField, heatColor, fieldInputs } from './lib/heat.js';
import { statusFor, toF } from './lib/rules.js';

const DASH = '—';
const STEP_HZ = 30;
const STEP_MS = 1000 / STEP_HZ;
const MAX_STEPS = 6;        // per frame; a longer gap (a stall) drops the backlog
const CANVAS_W = 640;
const CANVAS_H = 400;
const BLUR_PX = 10;
const WEATHER_ENTITY = 'weather.forecast_home';
const EMBER = '#da5c2c';
const COOL = '#2a7fff';
const live = { loops: 0 };

const deg = (v) => (v == null ? DASH : `${Math.round(v)}°`);

function fmtMin(m) {
  m = Math.max(0, Math.round(m));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

const BOX = (id, name, letter, body) => `
  <div class="box" data-testid="${id}" data-on="0">
    <div class="boxhead"><span>${name}</span><span class="letter">${letter}</span></div>${body}
  </div>`;

const TEMPLATE = `
<style>
  :host { display: flex; flex-direction: column; gap: 16px; padding: 24px; min-width: 0; min-height: 0; background: var(--cn-card); }
  [hidden] { display: none !important; }
  .top { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 8px 24px; }
  .head { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .line { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }
  .num { font-size: 48px; line-height: 1; font-weight: 700; }
  .word { font-size: 14px; }
  .small { font-size: 12px; color: var(--cn-text-2); }
  .tag { font-size: 10px; letter-spacing: 0.08em; color: var(--cn-text-2); border: 1px solid var(--cn-outline); border-radius: 2px; padding: 0 4px; margin-left: 6px; }
  .legend { display: flex; gap: 16px; font-size: 12px; color: var(--cn-text-2); align-items: center; }
  .scale { display: flex; height: 8px; width: 140px; border: 1px solid var(--cn-hairline); }
  .scale > span { flex: 1; }
  .body { display: flex; flex-wrap: wrap; gap: 16px; align-items: stretch; }
  .col { display: flex; flex-direction: column; gap: 12px; }
  .outdoor { flex: 1 1 130px; min-width: 130px; }
  .closet { flex: 1 1 150px; min-width: 150px; }
  .mid { flex: 999 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
  .out { font-size: 24px; font-weight: 700; }
  .box { border-radius: 2px; padding: 12px; display: flex; flex-direction: column; gap: 6px; background: #0b0b0b; border: 1px solid var(--cn-hairline); color: var(--cn-label); }
  .boxhead { display: flex; justify-content: space-between; align-items: center; font-size: 12px; letter-spacing: 0.06em; color: var(--cn-text); }
  .letter { color: var(--cn-label); }
  .state { font-size: 12px; }
  .iconrow { display: flex; align-items: center; gap: 10px; }
  .ac svg { align-self: center; }
  .box[data-testid="ac"][data-on="1"], .box[data-testid="coil"][data-on="1"] { border-color: ${COOL}; color: ${COOL}; }
  .box[data-testid="furnace"][data-on="1"] { border-color: ${EMBER}; color: ${EMBER}; }
  .box[data-testid="blower"][data-on="1"] { border-color: var(--cn-text-2); color: var(--cn-text); }
  .ic { fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
  .fan { transform-box: view-box; }
  .ac .fan { transform-origin: 32px 32px; }
  .blower .fan { transform-origin: 12px 12px; }
  .box[data-on="1"] .fan { animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .box[data-on="1"] .fan { animation: none; } }
  .lock { display: flex; align-items: center; gap: 8px; padding-left: 12px; font-size: 11px; color: var(--cn-label); }
  .lock.tripped { color: var(--cn-text); }
  .lock .sym { width: 16px; text-align: center; }
  .roombox { position: relative; width: 100%; aspect-ratio: 16 / 10; border: 2px solid var(--cn-outline); border-radius: 2px; background: #0b0b0b; overflow: hidden; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  .abs { position: absolute; }
  .win { left: -2px; width: 6px; height: 18%; background: #0b0b0b; border-left: 1px solid var(--cn-label); border-right: 1px solid var(--cn-label); }
  .door { right: 14%; bottom: -2px; width: 14%; height: 4px; background: var(--cn-card); }
  .cap { font-size: 10px; color: var(--cn-label); }
  .vent { border: 1px solid #505050; border-radius: 1px; }
  .vents-on .vent { border-color: var(--cn-text); }
  .ret { left: 4%; bottom: 8px; width: 12%; height: 8px; border: 1px solid #505050; border-radius: 2px; }
  .tab5 { right: 8px; top: 46%; display: flex; align-items: center; gap: 8px; }
  .tab5 .sensor { font-size: 10px; color: var(--cn-text-2); text-align: right; }
  .tstat { width: 22px; height: 32px; border: 1px solid var(--cn-text-2); border-radius: 2px; background: var(--cn-card); display: flex; align-items: center; justify-content: center; color: var(--cn-text); font-size: 9px; font-weight: 700; }
  .tstat.fault { border-color: var(--cn-text); }
  .caption { left: 50%; bottom: 10px; transform: translateX(-50%); font-size: 10px; color: #505050; letter-spacing: 0.1em; white-space: nowrap; }
  .readouts { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 12px; color: var(--cn-label); }
  .readouts b { color: var(--cn-text); font-weight: 400; }
</style>
<div class="top">
  <div class="head" data-testid="room-head">
    <span class="label">ROOM<span class="tag" id="room-sim" hidden>SIM</span></span>
    <div class="line"><span class="num" data-testid="room-num" id="room-num">${DASH}</span><span class="word" id="st"><span id="st-mark"></span> <span id="st-word"></span></span></div>
    <span class="small" id="st-sub"></span>
  </div>
  <div class="legend" aria-label="Colour scale, 60 to 80°F"><span>60°</span><span class="scale" id="scale" aria-hidden="true"></span><span>80°F</span></div>
</div>
<div class="body">
  <div class="col outdoor" data-testid="outdoor">
    <span class="label">OUTDOOR<span class="tag" id="out-sim" hidden>SIM</span></span>
    <div class="col" style="gap: 2px">
      <span class="out" data-testid="outdoor-num" id="out-num">${DASH}</span>
      <span class="small" id="out-sub"></span>
    </div>
    <div class="ac">${BOX('ac', 'AC UNIT', 'Y', `
      <svg viewBox="0 0 64 64" width="64" height="64" aria-hidden="true" style="align-self: center">
        <rect x="4" y="4" width="56" height="56" rx="2" class="ic"></rect>
        <circle cx="32" cy="32" r="18" class="ic"></circle>
        <g class="fan"><path d="M32 32 32 16M32 32 46 40M32 32 18 40" class="ic"></path></g>
      </svg>
      <span class="state" id="ac-state">${DASH}</span>`)}</div>
  </div>
  <div class="mid">
    <div class="roombox" id="roombox">
      <canvas id="cv" width="${CANVAS_W}" height="${CANVAS_H}" aria-hidden="true"></canvas>
      <div class="abs win" aria-hidden="true" style="top: 22%"></div>
      <div class="abs win" aria-hidden="true" style="top: 58%"></div>
      <div class="abs door" aria-hidden="true"></div>
      <span class="abs cap" style="left: 10px; top: 32%; writing-mode: vertical-rl">WINDOWS</span>
      <div class="abs vent" aria-hidden="true" style="left: 16%; top: 2px; width: 14%; height: 6px"></div>
      <div class="abs vent" aria-hidden="true" style="left: 60%; top: 2px; width: 14%; height: 6px"></div>
      <div class="abs vent" aria-hidden="true" style="left: calc(100% - 8px); top: 64%; width: 6px; height: 16%"></div>
      <span class="abs cap" style="left: 16%; top: 12px">SUPPLY</span>
      <span class="abs cap" style="left: 60%; top: 12px">SUPPLY</span>
      <div class="abs ret" aria-hidden="true"></div>
      <span class="abs cap" style="left: 4%; bottom: 20px">RETURN</span>
      <div class="abs tab5"><span class="sensor" id="sensor-line">${DASH}</span><div class="tstat" id="tstat">--</div></div>
      <span class="abs caption">LIVING ROOM · TOP-DOWN</span>
    </div>
    <div class="readouts" data-testid="readouts">
      <span>room avg <b id="ro-room">${DASH}</b></span><span>target <b id="ro-target">${DASH}</b></span>
      <span>airflow <b id="ro-air">${DASH}</b></span><span>humidity <b id="ro-hum">${DASH}</b></span>
    </div>
  </div>
  <div class="col closet">
    <span class="label">EQUIPMENT CLOSET</span>
    ${BOX('coil', 'COOLING COIL', 'Y', `<span class="state" id="coil-state">${DASH}</span>`)}
    <div class="lock" id="lock">
      <svg class="ic" id="lock-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="1"></rect><path d="M8 11V8a4 4 0 0 1 8 0v3"></path></svg>
      <span class="sym" id="lock-sym" hidden>⚠</span>
      <span id="lock-line">interlock ${DASH}</span>
    </div>
    ${BOX('furnace', 'FURNACE', 'W', `
      <div class="iconrow">
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path class="ic" d="M12 3c1 3 5 5 5 10a5 5 0 0 1-10 0c0-3 2-4 2-6 1 1 2 2 3 2 0-2-1-4 0-6Z"></path></svg>
        <span class="state" id="furnace-state">${DASH}</span>
      </div>`)}
    <div class="blower">${BOX('blower', 'BLOWER', 'G', `
      <div class="iconrow">
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g class="fan"><circle cx="12" cy="12" r="2" class="ic"></circle><path class="ic" d="M12 10c-1-4 1-7 3-6s0 5-3 6Zm2 2c4-1 7 1 6 3s-5 0-6-3Zm-2 2c1 4-1 7-3 6s0-5 3-6Zm-2-2c-4 1-7-1-6-3s5 0 6 3Z"></path></g></svg>
        <span class="state" id="blower-state">${DASH}</span>
      </div>`)}</div>
  </div>
</div>`;

class ChestnutRoomView extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.adoptedStyleSheets = [styles];
    this.shadowRoot.innerHTML = TEMPLATE;
    this._el = {};
    this.shadowRoot.querySelectorAll('[id]').forEach((n) => { this._el[n.id] = n; });
    this.shadowRoot.querySelectorAll('[data-testid]').forEach((n) => { this._el[n.dataset.testid] = n; });
    this._el.scale.innerHTML = Array.from({ length: 21 }, (_, k) => {
      const c = heatColor(60 + k);
      return `<span style="background: rgba(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])},${c[3]})"></span>`;
    }).join('');
    this._adapter = null;
    this._active = false;
    this._field = new HeatField();
    this._raf = null;
    this._last = null;
    this._acc = 0;
    this._frames = 0;
    this._tick = (ts) => this._frame(ts);
    this._onVisibility = () => this._sync();
  }

  set adapter(a) {
    this._adapter = a || null;
  }

  get adapter() {
    return this._adapter;
  }

  set active(on) {
    this._active = !!on;
    this._sync();
  }

  get active() {
    return this._active;
  }

  get _loops() {
    return live.loops;
  }

  connectedCallback() {
    document.addEventListener('visibilitychange', this._onVisibility);
    this._sync();
  }

  disconnectedCallback() {
    document.removeEventListener('visibilitychange', this._onVisibility);
    this._sync();
  }

  // Start or stop the loop to match active && connected && the page visible.
  _sync() {
    const run = this._active && this.isConnected && !document.hidden;
    if (run && this._raf == null) {
      this._last = null;
      this._acc = 0;
      this._raf = requestAnimationFrame(this._tick);
      live.loops++;
      this._render();
    } else if (!run && this._raf != null) {
      cancelAnimationFrame(this._raf);
      this._raf = null;
      live.loops--;
    }
  }

  _frame(ts) {
    this._raf = requestAnimationFrame(this._tick);
    this._frames++;
    if (this._last == null) this._last = ts - STEP_MS; // step once on the first frame
    this._acc += ts - this._last;
    this._last = ts;
    let n = 0;
    if (this._acc >= STEP_MS) {
      const inputs = this._inputs();
      while (this._acc >= STEP_MS && n < MAX_STEPS) {
        this._field.step(1 / STEP_HZ, inputs);
        this._acc -= STEP_MS;
        n++;
      }
      if (this._acc >= STEP_MS) this._acc = 0;
    }
    if (n) {
      this._draw();
      this._render();
    }
  }

  // ── data ───────────────────────────────────────────────────────────────────────────────
  _read() {
    const a = this._adapter;
    if (!a || !a.online()) return null;
    const fanMode = a.attr('main_thermostat', 'fan_mode');
    const v = {
      mode: a.str('main_thermostat'),
      action: a.attr('main_thermostat', 'hvac_action'),
      room: a.num('checked_temperature'),
      eff: a.num('effective_target'),
      humidity: a.num('room_humidity'),
      heat: a.on('call_heat') === true,
      cool: a.on('call_cool') === true,
      fan: a.on('call_fan') === true,
      fanOn: String(fanMode || '').toLowerCase() === 'on',
      sensorFault: a.on('sensor_fault') === true,
      interlock: a.on('interlock_fault'),
      minutes: this._minutes(a),
    };
    v.air = v.heat || v.cool || v.fan || v.fanOn;
    return v;
  }

  // Minutes in the current action (action_elapsed plus the time since HA got it), or null.
  _minutes(a) {
    const el = a.num('action_elapsed');
    if (el == null) return null;
    const unit = a.attr('action_elapsed', 'unit_of_measurement');
    const sec = el * (unit === 'min' ? 60 : unit === 'h' ? 3600 : 1);
    const at = a.updatedMs('action_elapsed');
    return (sec + (at != null ? Math.max(0, Date.now() - at) / 1000 : 0)) / 60;
  }

  // Outdoor: the sim's current outdoor sensor, else its fixed knob, else HA's weather entity.
  _outdoor() {
    const a = this._adapter;
    if (!a) return { f: null, sub: '', sim: false };
    const now = (a.entries || []).find((e) => e.objectId && (e.objectId === 'sim_outdoor_now_f'
      || (e.objectId.includes('outdoor') && e.objectId.includes('now'))));
    const weather = a.str('sim_weather');
    const wtxt = weather && !['unknown', 'unavailable'].includes(weather) ? weather.toLowerCase() : '';
    if (now) return { f: a.num(now.objectId), sub: wtxt, sim: true };
    if ((a.entries || []).some((e) => e.objectId === 'sim_outdoor_f')) return { f: a.num('sim_outdoor_f'), sub: wtxt && wtxt !== 'fixed' ? `fixed · sim ${wtxt}` : 'fixed', sim: true };
    const w = a.hass && a.hass.states ? a.hass.states[WEATHER_ENTITY] : null;
    const t = w && w.attributes ? Number(w.attributes.temperature) : NaN;
    if (w && !['unknown', 'unavailable'].includes(w.state) && Number.isFinite(t)) {
      return { f: toF(t, w.attributes.temperature_unit), sub: String(w.state).replace(/-/g, ' '), sim: false };
    }
    return { f: null, sub: '', sim: false };
  }

  _inputs() {
    return fieldInputs(this._read(), this._outdoor().f);
  }

  // ── drawing ────────────────────────────────────────────────────────────────────────────
  _draw() {
    const f = this._field;
    if (!f._primed) return;
    const m = f.mean().toFixed(2);
    if (this.getAttribute('data-mean') !== m) this.setAttribute('data-mean', m);
    if (!this._off) {
      this._off = document.createElement('canvas');
      this._off.width = f.w;
      this._off.height = f.h;
      this._offCtx = this._off.getContext('2d');
      this._img = this._offCtx.createImageData(f.w, f.h);
      this._ctx = this._el.cv.getContext('2d');
    }
    if (!this._ctx) return;
    f.toImageData(this._img.data);
    this._offCtx.putImageData(this._img, 0, 0);
    const ctx = this._ctx;
    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    if ('filter' in ctx) ctx.filter = `blur(${BLUR_PX}px)`;
    ctx.drawImage(this._off, -BLUR_PX, -BLUR_PX, CANVAS_W + 2 * BLUR_PX, CANVAS_H + 2 * BLUR_PX);
    if ('filter' in ctx) ctx.filter = 'none';
    ctx.fillStyle = '#202020';
    for (let y = 16; y < CANVAS_H; y += 20) for (let x = 16; x < CANVAS_W; x += 20) ctx.fillRect(x, y, 1.5, 1.5);
  }

  _text(id, value) {
    const n = this._el[id];
    if (n && n.textContent !== value) n.textContent = value;
  }

  _on(id, on) {
    const n = this._el[id];
    const val = on ? '1' : '0';
    if (n.dataset.on !== val) n.dataset.on = val;
  }

  _render() {
    const a = this._adapter;
    const v = this._read();
    const sim = !!(a && a.simPresent());
    this._el['room-sim'].hidden = !sim;
    const out = this._outdoor();
    this._el['out-sim'].hidden = !out.sim;
    this._text('out-num', out.f == null ? DASH : `${Math.round(out.f)}°F`);
    this._text('out-sub', out.f == null ? 'outdoor —' : out.sub);

    const room = v ? v.room : null;
    this._text('room-num', room == null ? DASH : `${room.toFixed(1)}°`);
    this._text('ro-room', room == null ? DASH : `${room.toFixed(1)}°F`);
    this._text('ro-target', v && v.mode !== 'off' ? deg(v.eff) : v ? 'OFF' : DASH);
    this._text('ro-air', v ? (v.air ? 'on' : 'still') : DASH);
    this._text('ro-hum', v && v.humidity != null ? `${Math.round(v.humidity)}%` : DASH);

    let st;
    if (!v) st = { mark: '·', word: a ? 'OFFLINE' : '', color: '#b4b4b4' };
    else st = statusFor({ mode: v.mode, action: v.action, sensorFault: v.sensorFault, interlockFault: v.interlock === true, callHeat: v.heat, callCool: v.cool, callFan: v.fan, targetText: deg(v.eff), minutesSoFar: v.minutes });
    this._text('st-mark', st.mark);
    this._text('st-word', st.word);
    if (this._el.st.style.color !== st.color) this._el.st.style.color = st.color;
    let sub = '';
    if (!v) sub = a ? 'the thermostat is not connected · field paused' : '';
    else if (v.sensorFault) sub = '⚠ sensor fault · field frozen at the last good reading';
    else if (v.interlock === true) sub = '⚠ interlock tripped · heating and cooling stopped';
    else if (room == null) sub = 'no room reading · field paused';
    this._text('st-sub', sub);

    // The Tab5 on the wall.
    this._text('sensor-line', !v ? DASH : v.sensorFault ? '⚠ sensor fault' : room == null ? 'sensor —' : `sensor ${room.toFixed(1)}°F`);
    this._text('tstat', !v || v.mode === 'off' || v.eff == null ? '--' : String(Math.round(v.eff)));
    this._el.tstat.classList.toggle('fault', !!(v && v.sensorFault));
    this._el.roombox.classList.toggle('vents-on', !!(v && (v.heat || v.cool)));

    // Equipment.
    const mins = v && v.minutes != null ? ` · ${fmtMin(v.minutes)}` : '';
    const heat = !!(v && v.heat), cool = !!(v && v.cool), air = !!(v && v.air);
    this._on('ac', cool);
    this._on('coil', cool);
    this._on('furnace', heat);
    this._on('blower', air);
    this._text('ac-state', !v ? DASH : cool ? `● running${mins}` : '○ off');
    this._text('coil-state', !v ? DASH : cool ? '● cooling air' : '○ idle');
    this._text('furnace-state', !v ? DASH : heat ? `● firing${mins}` : '○ off');
    this._text('blower-state', !v ? DASH : air ? '● moving air' : '○ still');

    // Interlock: armed, or tripped (a symbol, not a colour badge).
    const tripped = !!(v && v.interlock === true);
    this._el['lock-icon'].style.display = tripped ? 'none' : '';
    this._el['lock-sym'].hidden = !tripped;
    this._el.lock.classList.toggle('tripped', tripped);
    this._text('lock-line', !v || v.interlock == null ? `interlock ${DASH}` : tripped ? 'interlock tripped · W and Y were both on' : 'interlock armed · never both');
  }
}

if (!customElements.get('chestnut-room-view')) {
  customElements.define('chestnut-room-view', ChestnutRoomView);
}
