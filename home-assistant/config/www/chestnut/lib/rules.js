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

export function dayBar(periods) {
  if (!periods || !periods.length) return [];
  const mins = t => { const [h, m] = t.split(':').map(Number); return h * 60 + m; };
  const ps = periods.map(p => ({ ...p, at: mins(p.time) })).sort((a, b) => a.at - b.at);
  const seg = (name, level, flex) => ({ flex, level, label: flex >= 150 ? name : '' });
  const out = [];
  if (ps[0].at > 0) out.push(seg(ps[ps.length - 1].name, ps[ps.length - 1].level, ps[0].at));
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
