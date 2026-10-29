// The Schedule tab: the editor (on/off, Weekday/Weekend, per period a time and a level, the
// Comfort temperature and the Eco offset) and the week (Mon–Fri and Sat–Sun bars). Mockup
// Main.dc.html, Schedule tab, without the Holds card. Everything is read from and written to
// the M2 schedule entities (switch.schedule_enabled, time.sched_*_time, select.sched_*_level,
// number.comfort_target / eco_offset, sensor.schedule_period); the level selects are
// per-period settings (plain select_option), not holds.
import { dayBar, Debouncer } from './lib/rules.js';

export const PERIODS = ['wake', 'leave', 'return', 'sleep'];
const DAYS = [['weekday', 'WEEKDAY'], ['weekend', 'WEEKEND']];
const LEVEL_OPTIONS = ['Comfort', 'Eco'];
const STEP_DEBOUNCE_MS = 800;
const TIME_WRITE_PAUSE_MS = 600;
const PENDING_GIVE_UP_MS = 6000;
const DASH = '—';
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

export const dayType = (weekday) => (weekday >= 1 && weekday <= 5 ? 'weekday' : 'weekend');

// A day's four periods [{name, time "HH:MM[:SS]", level}], or null if any is missing.
export function readPeriods(a, day) {
  const periods = PERIODS.map((p) => ({ name: p, time: a.str(`sched_${day}_${p}_time`), level: a.str(`sched_${day}_${p}_level`) }));
  return periods.some((p) => !/^\d{1,2}:\d{2}/.test(p.time || '') || !LEVEL_OPTIONS.includes(p.level)) ? null : periods;
}

// rules.dayBar as spans: white #eeeeee = Comfort, #3a3a3a = Eco.
export function dayBarHtml(periods) {
  return dayBar(periods).map((s) => `<span data-level="${s.level}" style="flex: ${s.flex} 1 0; ${s.level === 'Comfort' ? 'background: #eeeeee; color: #000000' : 'background: #3a3a3a; color: #eeeeee'}">${esc(s.label)}</span>`).join('');
}

const minutesOf = (t) => { const [h, m] = String(t).split(':').map(Number); return h * 60 + m; };

export const SCHEDULE_CSS = `
  .sched-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 440px), 1fr)); gap: 24px; }
  .sched { gap: 14px; }
  .switch { min-width: 64px; min-height: 32px; background: transparent; color: var(--cn-text-2); border: 1px solid var(--cn-outline); border-radius: 2px; font-size: 12px; font-weight: 700; cursor: pointer; }
  .switch[aria-checked="true"] { background: var(--cn-text); color: #000000; border-color: var(--cn-text); }
  .prow { display: flex; gap: 8px; align-items: center; font-size: 12px; padding: 4px 0; border-bottom: 1px solid var(--cn-hairline); color: var(--cn-text-2); }
  .prow.cur { color: var(--cn-text); font-weight: 700; }
  .prow.off { opacity: 0.4; }
  .prow .mark { flex: 0 0 12px; }
  .prow .pname { flex: 1; }
  .field { min-height: 32px; background: #000000; color: var(--cn-text); border: 1px solid var(--cn-outline); border-radius: 2px; padding: 0 8px; font: inherit; font-size: 12px; color-scheme: dark; }
  .field[type="time"] { width: 122px; }
  .knobs { display: flex; flex-wrap: wrap; gap: 12px 24px; padding-top: 4px; }
  .knob { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--cn-text-2); }
  .knob button { width: 32px; height: 32px; background: transparent; color: var(--cn-text); border: 1px solid var(--cn-outline); border-radius: 2px; cursor: pointer; }
  .knob .kval { color: var(--cn-text); min-width: 32px; text-align: center; }
  .week .daybar { height: 20px; }
  .legend { display: flex; gap: 16px; font-size: 12px; color: var(--cn-text-2); }
  .legend i { display: inline-block; width: 10px; height: 10px; margin-right: 6px; }
`;

const KNOB = (key, label, down, up) => `
  <div class="knob">${label}
    <button type="button" data-testid="${key}-minus" aria-label="${down}">−</button>
    <span class="kval" data-testid="${key}-val">${DASH}</span>
    <button type="button" data-testid="${key}-plus" aria-label="${up}">+</button></div>`;

export const SCHEDULE_HTML = `
  <div class="sched-grid" data-views="SCHEDULE">
    <section class="card sched" data-testid="schedule" aria-label="Schedule">
      <div class="between" style="align-items: center"><span class="label">SCHEDULE</span>
        <button type="button" class="switch" role="switch" aria-checked="false" aria-label="Schedule on" data-testid="sched-switch">${DASH}</button></div>
      <div class="segs">${DAYS.map(([k, l]) => `<button type="button" class="seg" data-testid="day-${k}" aria-pressed="false">${l}</button>`).join('')}</div>
      ${PERIODS.map((p) => `
      <div class="prow" data-testid="sched-row-${p}">
        <span class="mark"></span><span class="pname">${p}</span>
        <input type="time" class="field" data-testid="sched-time-${p}" aria-label="${p} time">
        <select class="field" data-testid="sched-level-${p}" aria-label="${p} level">${LEVEL_OPTIONS.map((o) => `<option>${o}</option>`).join('')}</select>
      </div>`).join('')}
      <div class="knobs">${KNOB('comfort', 'comfort', 'Lower comfort', 'Raise comfort')}${KNOB('eco', 'eco offset', 'Smaller eco offset', 'Larger eco offset')}</div>
    </section>
    <section class="card week" data-testid="week" aria-label="Week">
      <span class="label">THE WEEK</span>
      ${[['weekday', 'mon – fri'], ['weekend', 'sat – sun']].map(([k, l]) => `
      <div class="group" style="gap: 6px"><span class="small">${l}</span><div class="daybar" data-testid="week-${k}"></div></div>`).join('')}
      <div class="axis"><span>12a</span><span>6a</span><span>12p</span><span>6p</span><span>12a</span></div>
      <div class="legend"><span><i style="background: #eeeeee"></i>comfort</span><span><i style="background: #3a3a3a"></i>eco</span></div>
    </section>
  </div>`;

// − / + for a number: the tapped value shows at once, one write after a short pause, and the
// tapped value stays until the entity reports it (or gives up).
class Stepper {
  constructor(tab, key, { read, range, write }) {
    Object.assign(this, { tab, read, range, write, pending: null, until: 0 });
    this.val = tab.q(`${key}-val`);
    this.minus = tab.q(`${key}-minus`);
    this.plus = tab.q(`${key}-plus`);
    this.debouncer = new Debouncer(STEP_DEBOUNCE_MS, (v) => this.write(v));
    this.minus.addEventListener('click', () => this.step(-1));
    this.plus.addEventListener('click', () => this.step(1));
  }

  step(dir) {
    const a = this.tab.adapter();
    const cur = a ? this.read(a) : null;
    if (cur == null) return;
    const r = this.range(a) || { min: -Infinity, max: Infinity, step: 1 };
    const base = this.pending ?? cur;
    this.pending = Math.min(r.max, Math.max(r.min, Math.round((base + dir * r.step) * 100) / 100));
    this.until = Date.now() + STEP_DEBOUNCE_MS + PENDING_GIVE_UP_MS;
    this.debouncer.tap(this.pending, cur);
    this.render(a);
  }

  render(a) {
    const cur = a ? this.read(a) : null;
    if (this.pending != null && !this.debouncer.timer && (cur === this.pending || Date.now() > this.until)) this.pending = null;
    const v = this.pending ?? cur;
    this.tab.text(this.val, v == null ? DASH : `${Math.round(v * 10) / 10}°`);
    this.minus.disabled = cur == null;
    this.plus.disabled = cur == null;
  }
}

export class ScheduleTab {
  // host: the dashboard (adapter(), call(domain, service, objId, data)).
  constructor(root, host) {
    this.root = root;
    this.host = host;
    this.day = null; // the day type shown; today's until picked
    this.weekKey = '';
    this.switch = this.q('sched-switch');
    this.switch.addEventListener('click', () => this.host.call('switch', 'toggle', 'schedule_enabled'));
    for (const [k] of DAYS) this.q(`day-${k}`).addEventListener('click', () => {
      this.day = k;
      for (const row of this.rows) row.pending = null; // a pending time belongs to the other day
      if (this.now) this.render(this.adapter(), this.now);
    });
    this.rows = PERIODS.map((p) => {
      const row = { p, el: this.q(`sched-row-${p}`), time: this.q(`sched-time-${p}`), level: this.q(`sched-level-${p}`) };
      row.mark = row.el.querySelector('.mark');
      // Typing a time fires change once per complete value (09:0…, 09:15): write the last one.
      row.time.addEventListener('change', () => {
        clearTimeout(row.timer);
        const day = this.day;
        const value = row.time.value;
        if (!/^\d{2}:\d{2}$/.test(value)) return;
        row.pending = value; // shown until the entity reports it (or gives up)
        row.until = Date.now() + TIME_WRITE_PAUSE_MS + PENDING_GIVE_UP_MS;
        row.timer = setTimeout(() => this.host.call('time', 'set_value', `sched_${day}_${p}_time`, { time: `${value}:00` }), TIME_WRITE_PAUSE_MS);
      });
      row.level.addEventListener('change', () => this.host.call('select', 'select_option', `sched_${this.day}_${p}_level`, { option: row.level.value }));
      return row;
    });
    this.comfort = new Stepper(this, 'comfort', {
      read: (a) => { const f = a.num('comfort_target'); return f == null ? null : Math.round(f); }, // whole °F (°C round-trips)
      range: (a) => a.rangeF('comfort_target'),
      write: (f) => { const a = this.host.adapter(); if (a) a.setNumberF('comfort_target', f).catch((e) => console.warn('chestnut-dashboard: comfort_target', e)); },
    });
    // An offset, not a temperature: never unit-converted.
    this.eco = new Stepper(this, 'eco', {
      read: (a) => { const n = Number(a.str('eco_offset')); return a.str('eco_offset') != null && Number.isFinite(n) ? n : null; },
      range: (a) => { const lo = a.attr('eco_offset', 'min'); const hi = a.attr('eco_offset', 'max'); return lo == null || hi == null ? null : { min: lo, max: hi, step: a.attr('eco_offset', 'step') || 1 }; },
      write: (v) => this.host.call('number', 'set_value', 'eco_offset', { value: v }),
    });
  }

  q(testid) {
    return this.root.querySelector(`[data-testid="${testid}"]`);
  }

  adapter() {
    return this.host.adapter();
  }

  text(n, value) {
    if (n.textContent !== value) n.textContent = value;
  }

  // The day type whose period is running now: a period that started yesterday (before today's
  // first period) belongs to yesterday's day type.
  activeDay(a, now) {
    const today = dayType(now.day);
    const periods = readPeriods(a, today);
    if (!periods) return today;
    const first = Math.min(...periods.map((p) => minutesOf(p.time)));
    return now.hour * 60 + now.minute < first ? dayType((now.day + 6) % 7) : today;
  }

  // a: the resolved adapter (unavailable entities show — / disabled), else null.
  // now: nowParts in HA's time zone.
  render(a, now) {
    this.now = now;
    if (!this.day) this.day = dayType(now.day);
    for (const [k] of DAYS) this.q(`day-${k}`).setAttribute('aria-pressed', String(this.day === k));
    const on = a ? a.on('schedule_enabled') : null;
    this.switch.setAttribute('aria-checked', String(on === true));
    this.text(this.switch, on == null ? DASH : on ? 'ON' : 'OFF');
    this.switch.disabled = on == null;

    const period = a ? String(a.str('schedule_period') || '').toLowerCase() : '';
    const cur = on === true && PERIODS.includes(period) && this.activeDay(a, now) === this.day ? period : '';
    const focused = this.root.activeElement;
    for (const row of this.rows) {
      row.el.classList.toggle('off', on === false);
      row.el.classList.toggle('cur', row.p === cur);
      this.text(row.mark, row.p === cur ? '›' : '');
      const t = a ? a.str(`sched_${this.day}_${row.p}_time`) : null;
      const okTime = /^\d{1,2}:\d{2}/.test(t || '');
      const hhmm = okTime ? t.split(':').slice(0, 2).map((x) => x.padStart(2, '0')).join(':') : '';
      if (row.pending != null && (row.pending === hhmm || Date.now() > row.until)) row.pending = null;
      const shown = row.pending ?? hhmm;
      if (focused !== row.time && row.time.value !== shown) row.time.value = shown;
      row.time.disabled = !okTime;
      const lvl = a ? a.str(`sched_${this.day}_${row.p}_level`) : null;
      const okLvl = LEVEL_OPTIONS.includes(lvl);
      if (focused !== row.level && okLvl && row.level.value !== lvl) row.level.value = lvl;
      row.level.disabled = !okLvl;
    }
    this.comfort.render(a);
    this.eco.render(a);
    this.renderWeek(a);
  }

  renderWeek(a) {
    const bars = DAYS.map(([k]) => (a ? readPeriods(a, k) : null));
    const key = JSON.stringify(bars);
    if (key === this.weekKey) return;
    this.weekKey = key;
    DAYS.forEach(([k], i) => {
      this.q(`week-${k}`).innerHTML = bars[i] ? dayBarHtml(bars[i]) : `<span class="empty" style="padding-left: 0">${DASH}</span>`;
    });
  }
}
