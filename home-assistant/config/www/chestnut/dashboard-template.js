// The dashboard's markup: the frame (header, tabs) and each tab's cards. The element
// (chestnut-dashboard.js) finds nodes by id and data-testid and shows the cards whose
// data-views lists the selected tab.
import { DASHBOARD_CSS } from './dashboard-style.js';
import { SCHEDULE_HTML, SCHEDULE_CSS } from './tab-schedule.js';
import { SIMULATION_HTML, SIMULATION_CSS } from './tab-simulation.js';
import { SYSTEM_HTML, SYSTEM_CSS } from './tab-system.js';

export const TABS = ['HOME', 'SCHEDULE', 'SIMULATION', 'SYSTEM'];
export const MODES = [['off', 'OFF', 'off'], ['heat', 'HEAT', 'heat'], ['cool', 'COOL', 'cool'], ['auto', 'AUTO', 'heat_cool']];
export const FANS = [['auto', 'AUTO'], ['on', 'ON']];
export const LEVELS = [['comfort', 'COMFORT', 'Comfort'], ['eco', 'ECO', 'Eco']];
export const BUCKETS = 120; // 6-minute bars in the last-12-hours card
export const DASH = '—';

export const slugDash = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
export const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

const SEG = (id, label) => `<button type="button" class="seg" data-testid="${id}" aria-pressed="false">${label}</button>`;

export const TEMPLATE = (device) => `
<style>${DASHBOARD_CSS}${SCHEDULE_CSS}${SIMULATION_CSS}${SYSTEM_CSS}</style>
<div class="page">
<header><div class="head">
  <div class="titlebar">
    <div class="title"><span class="prompt">~/chestnut/${esc(slugDash(device))}</span><h1>${esc(device)}</h1></div>
    <div class="meta"><span id="sched-line">${DASH}</span><span id="clock"></span><span id="conn">○ connecting</span></div>
  </div>
  <div class="tabs" role="tablist" aria-label="Dashboard views">
    ${TABS.map((t) => `<button type="button" role="tab" class="tab${t === 'SIMULATION' ? ' desk' : ''}" data-tab="${t}" aria-selected="false"${t === 'SIMULATION' ? ' hidden' : ''}>${t}</button>`).join('')}
  </div>
</div></header>
<div class="wrap">
  <div class="row">
    <chestnut-room-view class="card room desk" data-testid="room" data-views="HOME SIMULATION" role="region" aria-label="Room"></chestnut-room-view>
    <section class="card thermo" data-views="HOME" aria-label="Thermostat">
      <div class="between"><span class="label" id="tlabel">TARGET</span><span class="label" style="text-transform:none">set_target</span></div>
      <div class="stepper">
        <button type="button" class="step" data-testid="minus" aria-label="Lower target">−</button>
        <span class="big" data-testid="target" aria-live="polite">${DASH}</span>
        <button type="button" class="step" data-testid="plus" aria-label="Raise target">+</button>
      </div>
      <span class="small center" id="tgt-sub" style="min-height: 20px"></span>
      <div class="status">
        <span class="word"><span id="status-mark"></span> <span data-testid="status-word"></span></span>
        <span class="small center" data-testid="status-sub"></span>
      </div>
      <div class="group"><span class="label">MODE</span><div class="segs">${MODES.map(([k, l]) => SEG(`mode-${k}`, l)).join('')}</div></div>
      <div class="pair">
        <div class="group"><span class="label">FAN</span><div class="segs">${FANS.map(([k, l]) => SEG(`fan-${k}`, l)).join('')}</div></div>
        <div class="group"><span class="label">LEVEL</span><div class="segs">${LEVELS.map(([k, l]) => SEG(`level-${k}`, l)).join('')}</div></div>
      </div>
      <div class="foot">
        <div class="between" style="font-size: 12px"><span class="label">SCHEDULE</span><span id="sched-foot">${DASH}</span></div>
        <button type="button" class="resume" data-testid="resume" hidden>Resume schedule →</button>
      </div>
    </section>
${SIMULATION_HTML}
  </div>
  <section class="card runtime" data-testid="runtime" data-views="HOME SIMULATION" aria-label="Runtime">
    <div class="between" style="flex-wrap: wrap">
      <span class="label">LAST 12 HOURS</span>
      <div class="totals"><span>heat <b id="tot-heat">${DASH}</b></span><span>cool <b id="tot-cool">${DASH}</b></span><span>fan <b id="tot-fan">${DASH}</b></span></div>
    </div>
    <span class="empty" id="rt-empty">loading…</span>
    <div id="rt-chart" hidden>
      <svg class="chart" viewBox="0 0 120 30" preserveAspectRatio="none" role="img" aria-label="Room temperature over the last 12 hours, with the target dashed">
        <polyline id="pl-target" fill="none" stroke="#505050" stroke-dasharray="1.5 1.5" vector-effect="non-scaling-stroke"></polyline>
        <polyline id="pl-room" fill="none" stroke="#eeeeee" vector-effect="non-scaling-stroke"></polyline>
      </svg>
      ${[['heat W', 'heat'], ['cool Y', 'cool'], ['fan G', 'fan']].map(([l, k]) => `<div class="barrow"><span>${l}</span><div class="bars" id="bars-${k}">${'<i data-bar></i>'.repeat(BUCKETS)}</div></div>`).join('')}
      <div class="axis"><span>12h ago</span><span>6h</span><span>now</span></div>
    </div>
  </section>
  <div class="grid2" data-views="HOME">
    <section class="card" data-testid="today" aria-label="Today">
      <div class="between"><span class="label" id="today-label">TODAY</span><button type="button" class="link" data-go="SCHEDULE">schedule →</button></div>
      <div class="daybar" id="daybar"></div>
      <div class="nowrow"><span class="now" id="now-mark"></span></div>
      <div class="axis"><span>12a</span><span>6a</span><span>12p</span><span>6p</span><span>12a</span></div>
    </section>
    <section class="card" data-testid="status-card" aria-label="Status">
      <div class="between"><span class="label">STATUS</span><button type="button" class="link" data-go="SYSTEM">system →</button></div>
      <div class="kv"><span>equipment</span><span id="st-equip">${DASH}</span></div>
      <div class="kv"><span>interlock</span><span id="st-lock">${DASH}</span></div>
      <div class="kv"><span>sensor</span><span id="st-sensor">${DASH}</span></div>
      <div class="kv"><span>home assistant</span><span id="st-ha">${DASH}</span></div>
    </section>
  </div>
${SCHEDULE_HTML}
${SYSTEM_HTML}
</div>
</div>`;
