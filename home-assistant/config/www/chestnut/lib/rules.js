// Display rules shared with the wall console (tab5-thermostat/ui/console-logic.yaml, ui_refresh).
// Pure and dependency-free.

const HEAT = '#da5c2c';
const COOL = '#2a7fff';
const PAUSED = '#eeeeee';
const NEUTRAL = '#b4b4b4';
const FINISHING = 'Finishing up · stops soon';

function minutesText(m) {
  if (m == null || m < 1) return 'just started';
  if (m < 60) return `${Math.floor(m)} min so far`;
  const t = Math.floor(m);
  return `${Math.floor(t / 60)} h ${t % 60} min so far`;
}

export function statusFor(s) {
  const fan = !!s.callFan || s.action === 'fan';
  const running = () => `to ${s.targetText} · ${minutesText(s.minutesSoFar)}`;
  if (s.sensorFault || s.interlockFault) {
    return { word: 'PAUSED', mark: '⊘', color: PAUSED, sub: s.callHeat || s.callCool ? FINISHING : '' };
  }
  if (s.action === 'heating') {
    const ok = s.mode === 'heat' || s.mode === 'heat_cool';
    return { word: 'HEATING', mark: '▲', color: HEAT, sub: ok ? running() : FINISHING };
  }
  if (s.action === 'cooling') {
    const ok = s.mode === 'cool' || s.mode === 'heat_cool';
    return { word: 'COOLING', mark: '▼', color: COOL, sub: ok ? running() : FINISHING };
  }
  if (s.mode === 'off') {
    return { word: fan ? 'FAN' : 'OFF', mark: '·', color: NEUTRAL, sub: fan ? 'System is off · fan on' : 'System is off' };
  }
  const wait = s.waitReason || '';
  const sub = wait ? `Waiting · ${wait[0].toLowerCase()}${wait.slice(1)}` : `holding ${s.targetText}`;
  return { word: fan ? 'FAN' : 'IDLE', mark: '·', color: NEUTRAL, sub };
}

export function targetLabel({ mode, level, hold, holdKind: kind, manual }) {
  if (manual || mode === 'off') return 'TARGET';
  if (hold && kind === 'temperature') return 'HOLD';
  return level === 'Eco' ? 'ECO TARGET' : 'COMFORT TARGET';
}

export function holdKind(scheduleStatus) {
  const m = /^Holding\s+(\S+)/i.exec(scheduleStatus || '');
  if (!m) return null;
  return /^\d/.test(m[1]) ? 'temperature' : 'level';
}

export function levelShouldSend({ picked, current, manual }) {
  return manual || picked !== current;
}

export function countdown({ running, actionElapsedS, publishedAtMs, nowMs, minS }) {
  const ok = [actionElapsedS, publishedAtMs, nowMs, minS].every(v => typeof v === 'number' && Number.isFinite(v));
  if (!running || !ok || minS <= 0) return { leftS: null, frac: 0 };
  const elapsed = actionElapsedS + (nowMs - publishedAtMs) / 1000;
  return {
    leftS: Math.max(0, minS - elapsed),
    frac: Math.min(1, Math.max(0, elapsed / minS)),
  };
}

// The System tab's four minimum-timer rows ({val, frac} each) from the device's action_elapsed
// (spec "System tab", builder check 2). M2 publishes no remaining times, so:
// - W on (call_heat) / Y on (call_cool): the running unit's min run counts from when the action
//   began; its own min off says "running"; the other unit's min off can't be known ("—");
// - W and Y both off, action idle / off / fan: each unit's min off counts from when that action
//   began (an upper bound for the unit that stopped earlier); min run is done ("✓ ok").
// Which unit runs comes from the relays, never the climate's action: during an interlock latch
// the action can still say heating with W cut (logic.yaml). While the interlock is tripped, or the
// action and the relays disagree, every row is "—": the trip time isn't published.
// mins: {heatRun, heatOff, coolRun, coolOff} in minutes. "—" wherever an input is missing.
const DASH = '—';
export function safetyRows({ action, callHeat, callCool, interlockFault, actionElapsedS, publishedAtMs, nowMs, mins }) {
  const m = mins || {};
  const unknown = { val: DASH, frac: 0 };
  const timed = (min, doneText, fullWhenDone) => {
    const c = countdown({ running: true, actionElapsedS, publishedAtMs, nowMs, minS: typeof min === 'number' ? min * 60 : NaN });
    if (c.leftS == null) return unknown;
    if (c.leftS > 0) return { val: `${Math.ceil(c.leftS / 60)} min left`, frac: c.frac };
    return { val: doneText, frac: fullWhenDone ? 1 : 0 };
  };
  const ok = { val: '✓ ok', frac: 0 };
  const none = { heatRun: unknown, heatOff: unknown, coolRun: unknown, coolOff: unknown };
  if (interlockFault === true) return none;
  if (callHeat === true && callCool !== true) {
    return { heatRun: timed(m.heatRun, '✓ ok', true), heatOff: { val: 'running', frac: 0 }, coolRun: ok, coolOff: unknown };
  }
  if (callCool === true && callHeat !== true) {
    return { heatRun: ok, heatOff: unknown, coolRun: timed(m.coolRun, '✓ ok', true), coolOff: { val: 'running', frac: 0 } };
  }
  if (callHeat === false && callCool === false && (action === 'idle' || action === 'off' || action === 'fan')) {
    return { heatRun: ok, heatOff: timed(m.heatOff, '✓ ready', false), coolRun: ok, coolOff: timed(m.coolOff, '✓ ready', false) };
  }
  return none;
}

// Plain wording for an event-log entry: {msg, kind} (kind: heat, cool, fault or ''), or null to
// leave it out. Going offline marks every entity unavailable: one line (from call_heat) says so.
const EVENTS = {
  call_heat: { on: ['furnace on', 'heat'], off: ['furnace off', 'heat'] },
  call_cool: { on: ['ac on', 'cool'], off: ['ac off', 'cool'] },
  sensor_fault: { on: ['temperature sensor problem · heating and cooling paused', 'fault'], off: ['temperature sensor ok again', ''] },
  interlock_fault: { on: ['interlock tripped · heating and cooling paused', 'fault'], off: ['interlock cleared', ''] },
  schedule_hold: { on: ['hold started', ''], off: ['hold ended · following the schedule', ''] },
};
export function eventText(objId, state) {
  if (state === 'unavailable') return objId === 'call_heat' ? { msg: 'thermostat offline', kind: 'fault' } : null;
  if (state == null || state === 'unknown' || state === '') return null;
  if (objId === 'schedule_period') return { msg: `schedule · ${String(state).toLowerCase()} period`, kind: '' };
  const e = EVENTS[objId] && EVENTS[objId][state];
  return e ? { msg: e[0], kind: e[1] } : null;
}

// A day's periods as bar segments from midnight. Before the day's first period the previous
// day's last-starting period is still in force (chestnut_logic.h): `before` ({name, level}),
// else the day's own last period (the week bars, which stand for any day of their type).
export function dayBar(periods, before) {
  if (!periods || !periods.length) return [];
  const mins = t => { const [h, m] = t.split(':').map(Number); return h * 60 + m; };
  const ps = periods.map(p => ({ ...p, at: mins(p.time) })).sort((a, b) => a.at - b.at);
  const seg = (name, level, flex) => ({ flex, level, label: flex >= 150 ? name : '' });
  const out = [];
  const carried = before || ps[ps.length - 1];
  if (ps[0].at > 0) out.push(seg(carried.name, carried.level, ps[0].at));
  ps.forEach((p, i) => {
    const end = i + 1 < ps.length ? ps[i + 1].at : 1440;
    if (end > p.at) out.push(seg(p.name, p.level, end - p.at));
  });
  return out;
}

export function toF(value, unit) {
  return unit === '°C' ? value * 9 / 5 + 32 : value;
}

export function fromF(f, unit) {
  return unit === '°C' ? (f - 32) * 5 / 9 : f;
}

export class Debouncer {
  constructor(ms, onFire) {
    this.ms = ms;
    this.onFire = onFire;
    this.timer = null;
  }

  tap(value, base) {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      if (value !== base) this.onFire(value);
    }, this.ms);
  }

  cancel() {
    clearTimeout(this.timer);
    this.timer = null;
  }
}

// The − / + taps on a number: the target, and the schedule's comfort and eco offset. A burst of
// taps becomes one write of its final value, `ms` after the last tap. `pending` is the value to
// show: from the first tap until the device reports it (`settle`), or `giveUpMs` after the write
// at most. Values are rounded to 0.01 and clamped to `min`/`max` (callers may change those
// between taps, e.g. from an entity's range).
// The base a burst starts from, and is compared against when it fires, is the last value written
// that the device hasn't confirmed yet, else the device's own value. So a burst that backs out of
// an unconfirmed write is itself written, and one that returns to it sends nothing.
// `write(v)` may return a promise. A rejection undoes that write (`failed`) unless a newer write
// has gone out since; mid-burst, the burst carries on and is compared with the device instead.
export class TargetTaps {
  constructor({ ms, giveUpMs, min, max, write, onFailed }) {
    this.ms = ms;
    this.giveUpMs = giveUpMs;
    this.min = min;
    this.max = max;
    this.write = write;
    this.onFailed = onFailed;
    this.pending = null;
    this.written = null; // the last value sent, until the device reports it or we give up
    this.until = 0;
    this.deviceBase = null;
    this.seq = 0; // numbers each write, so a late failure of an older one is ignored
    this.timer = null;
  }

  get busy() {
    return this.timer != null;
  }

  _base() {
    return this.written ?? this.deviceBase;
  }

  _send(v) {
    const seq = ++this.seq;
    this.written = v;
    let p;
    try {
      p = this.write(v);
    } catch (err) {
      p = Promise.reject(err);
    }
    Promise.resolve(p).catch(() => this.failed(seq));
  }

  // One tap; `deviceBase` is the device's current value. Returns the new pending value.
  step(delta, deviceBase, now) {
    this.deviceBase = deviceBase;
    const base = this._base();
    if (base == null) return null;
    const next = Math.round(((this.pending ?? base) + delta) * 100) / 100;
    this.pending = Math.min(this.max, Math.max(this.min, next));
    this.until = now + this.ms + this.giveUpMs;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      if (this.pending !== this._base()) this._send(this.pending);
    }, this.ms);
    return this.pending;
  }

  // Every render: drop the shown value once the device reports it, or after the give-up time
  // (never mid-burst). `deviceTarget` is the device's value, null while offline.
  settle(deviceTarget, now) {
    if (this.busy || (this.pending == null && this.written == null)) return;
    const shown = this.pending ?? this.written;
    if ((deviceTarget != null && deviceTarget === shown) || now > this.until) {
      this.pending = null;
      this.written = null;
    }
  }

  // Write `seq` (default: the latest) failed. Ignored if a newer write has gone out since. Else
  // the device's value shows again, or, mid-burst, the burst goes on against the device's value.
  failed(seq = this.seq) {
    if (seq !== this.seq) return;
    this.written = null;
    if (!this.busy) this.pending = null;
    if (this.onFailed) this.onFailed();
  }

  // The element is going away mid-burst: send the burst now if it can still be written
  // (`canWrite`: an adapter is bound), else drop it so the number doesn't show a value nobody sends.
  detach(canWrite) {
    if (!this.busy) return;
    clearTimeout(this.timer);
    this.timer = null;
    if (canWrite && this.pending !== this._base()) {
      this._send(this.pending);
    } else if (!canWrite) {
      this.pending = null;
    }
  }
}
