// The Simulation tab's panel (BENCH ONLY): the virtual house's knobs, beside the room view.
// Mockup Main.dc.html, Simulation tab. Entities from tab5-thermostat/sim/virtual-house.yaml:
// sensor.sim_outdoor_now_f (read-only: the outdoor the physics uses now, the Fixed setting or the
// day curve), number.sim_outdoor_f (the Fixed outdoor), select.sim_weather, select.sim_fault, and
// number.sim_tau_h / sim_heat_fph / sim_cool_fph / sim_humidity. Ranges come from each number's
// attributes. Sliders write once on release (`change`, not every `input`), after a short pause
// so arrow-key repeats send one write; selects write on change. The dashboard shows the panel
// only while adapter.simPresent() (the SIMULATION tab), never at ≤ 860 px (class desk).

const WRITE_PAUSE_MS = 250;
const PENDING_GIVE_UP_MS = 5000;
const DASH = '—';
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

const SLIDERS = [
  ['sim-outdoor', 'sim_outdoor_f', 'fixed outdoor', (v) => `${v}°F`],
  ['sim-tau', 'sim_tau_h', 'insulation (hours to drift)', (v) => `${v} h`],
  ['sim-heat', 'sim_heat_fph', 'furnace heating rate', (v) => `${v}°F/h`],
  ['sim-cool', 'sim_cool_fph', 'ac cooling rate', (v) => `${v}°F/h`],
  ['sim-hum', 'sim_humidity', 'humidity', (v) => `${Math.round(v)}%`],
];
const SELECTS = [
  ['sim-weather', 'sim_weather', 'weather'],
  ['sim-fault', 'sim_fault', 'sensor fault'],
];

export const SIMULATION_CSS = `
  .sim { flex: 1 1 340px; gap: 16px; }
  .ctl { display: flex; flex-direction: column; gap: 6px; }
  .ctl label { display: flex; justify-content: space-between; font-size: 12px; color: var(--cn-text-2); }
  .ctl label b { color: var(--cn-text); font-weight: 400; }
  .ctl input[type="range"] { width: 100%; accent-color: var(--cn-text); }
  .ctl select { min-height: 44px; background: #000000; color: var(--cn-text); border: 1px solid var(--cn-outline); border-radius: 2px; padding: 0 12px; font: inherit; font-size: 14px; color-scheme: dark; }
  .physics { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--cn-hairline); padding-top: 12px; }
  .physics .eq { font-size: 12px; color: var(--cn-text-2); line-height: 1.7; white-space: pre-wrap; }
`;

const slider = ([id, , label]) => `
      <div class="ctl"><label for="${id}"><span>${label}</span><b data-testid="${id}-val">${DASH}</b></label>
        <input type="range" id="${id}" data-testid="${id}"></div>`;
const select = ([id, , label]) => `
      <div class="ctl"><label for="${id}"><span>${label}</span></label>
        <select id="${id}" data-testid="${id}"></select></div>`;

export const SIMULATION_HTML = `
    <section class="card sim desk" data-testid="sim-panel" data-views="SIMULATION" aria-label="Simulation">
      <div class="between"><span class="label">SIMULATION</span><span class="label">BENCH ONLY</span></div>
      <div class="kv"><span>outdoor now</span><span data-testid="sim-outdoor-now">${DASH}</span></div>
      ${slider(SLIDERS[0])}
      <span class="small" data-testid="sim-outdoor-note" style="color: var(--cn-label)"></span>
      ${SELECTS.map(select).join('')}${SLIDERS.slice(1).map(slider).join('')}
      <div class="physics">
        <span class="label">PHYSICS</span>
        <span class="eq">dT/dt = (outdoor − room) / insulation
  + heating rate · W − cooling rate · Y</span>
        <span class="small" style="color: var(--cn-label)">one room temperature; the colour flow is drawn around it</span>
      </div>
    </section>`;

export class SimulationTab {
  // host: the dashboard (adapter(), call(domain, service, objId, data)).
  constructor(root, host) {
    this.root = root;
    this.host = host;
    const q = (id) => root.querySelector(`[data-testid="${id}"]`);
    this.sliders = SLIDERS.map(([id, objId, , fmt]) => {
      const c = { objId, fmt, el: q(id), val: q(`${id}-val`), dragging: false, pending: null, until: 0, timer: null };
      c.el.addEventListener('pointercancel', () => { c.dragging = false; });
      c.el.addEventListener('input', () => { c.dragging = true; this.label(c, Number(c.el.value)); });
      c.el.addEventListener('change', () => {
        c.dragging = false;
        const v = Number(c.el.value);
        c.pending = v;
        c.until = Date.now() + WRITE_PAUSE_MS + PENDING_GIVE_UP_MS;
        clearTimeout(c.timer);
        c.timer = setTimeout(() => { c.timer = null; this.writeSlider(c, v); }, WRITE_PAUSE_MS);
      });
      return c;
    });
    this.outdoorNow = q('sim-outdoor-now');
    this.outdoorNote = q('sim-outdoor-note');
    this.selects = SELECTS.map(([id, objId]) => {
      const c = { objId, el: q(id), pending: null, until: 0, optionsKey: '' };
      c.el.addEventListener('change', () => {
        c.pending = c.el.value;
        c.until = Date.now() + PENDING_GIVE_UP_MS;
        this.host.call('select', 'select_option', objId, { option: c.el.value });
      });
      return c;
    });
  }

  label(c, v) {
    const t = v == null ? DASH : c.fmt(v);
    if (c.val.textContent !== t) c.val.textContent = t;
  }

  writeSlider(c, v) {
    const a = this.host.adapter();
    if (!a) return;
    if (c.objId === 'sim_outdoor_f') {
      a.setNumberF(c.objId, v).catch((e) => console.warn('chestnut-dashboard:', c.objId, e));
      // As in the mockup: the outdoor slider is the Fixed setting, so moving it selects Fixed.
      const w = a.str('sim_weather');
      if (w && w !== 'Fixed' && (a.attr('sim_weather', 'options') || []).includes('Fixed')) {
        this.host.call('select', 'select_option', 'sim_weather', { option: 'Fixed' });
      }
    } else {
      this.host.call('number', 'set_value', c.objId, { value: v });
    }
  }

  // a: the resolved adapter (unavailable entities disable their control), else null.
  render(a) {
    const now = Date.now();
    const out = a ? a.num('sim_outdoor_now_f') : null;
    const outText = out == null ? DASH : `${out.toFixed(1)}°F`;
    if (this.outdoorNow.textContent !== outText) this.outdoorNow.textContent = outText;
    const weather = a ? a.str('sim_weather') : null;
    const note = weather && weather !== 'Fixed' && (a.attr('sim_weather', 'options') || []).includes('Fixed')
      ? `moving it switches the weather from ${weather.toLowerCase()} to fixed` : '';
    if (this.outdoorNote.textContent !== note) this.outdoorNote.textContent = note;
    for (const c of this.sliders) {
      const cur = a ? a.num(c.objId) : null;
      const r = a ? a.rangeF(c.objId) : null;
      if (r) {
        for (const k of ['min', 'max', 'step']) if (c.el.getAttribute(k) !== String(r[k])) c.el.setAttribute(k, String(r[k]));
      }
      if (c.pending != null && !c.timer && (cur === c.pending || now > c.until)) c.pending = null;
      c.el.disabled = cur == null || !r;
      if (c.el.disabled) c.dragging = false; // a drag cut short never fires change
      if (c.dragging) continue;
      const v = c.pending ?? cur;
      if (v != null && c.el.value !== String(v)) c.el.value = String(v);
      this.label(c, v);
    }
    for (const c of this.selects) {
      const cur = a ? a.str(c.objId) : null;
      const options = (a && a.attr(c.objId, 'options')) || [];
      const key = JSON.stringify(options);
      if (key !== c.optionsKey) {
        c.optionsKey = key;
        c.el.innerHTML = options.map((o) => `<option>${esc(o)}</option>`).join('');
      }
      if (c.pending != null && (cur === c.pending || now > c.until)) c.pending = null;
      const v = c.pending ?? cur;
      c.el.disabled = !options.includes(cur);
      if (options.includes(v) && c.el.value !== v && this.root.activeElement !== c.el) c.el.value = v;
    }
  }
}
