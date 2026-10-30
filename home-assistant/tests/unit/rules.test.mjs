import test, { mock } from 'node:test';
import assert from 'node:assert/strict';
import {
  statusFor, targetLabel, holdKind, levelShouldSend, countdown, dayBar, toF, fromF, Debouncer, TargetTaps, safetyRows, eventText,
} from '../../config/www/chestnut/lib/rules.js';

const eq = assert.equal;
const closeTo = (a, b, tol) => assert.ok(Math.abs(a - b) <= tol, `${a} vs ${b}`);
const base = {
  mode: 'heat', action: 'idle', sensorFault: false, interlockFault: false, callHeat: false, callCool: false,
  callFan: false, fanMode: 'auto', waitReason: '', targetText: '72°', minutesSoFar: null,
};

test('paused_wins_over_heating', () => {
  const r = statusFor({ ...base, action: 'heating', interlockFault: true, callHeat: false });
  eq(r.word, 'PAUSED'); eq(r.mark, '⊘'); eq(r.color, '#eeeeee'); eq(r.sub, '');
});
test('paused_finishing_while_call_on', () => eq(statusFor({ ...base, sensorFault: true, callHeat: true }).sub, 'Finishing up · stops soon'));
test('mode_switch_mid_heat_finishing', () => eq(statusFor({ ...base, mode: 'cool', action: 'heating', callHeat: true }).sub, 'Finishing up · stops soon'));
test('mode_switch_mid_cool_finishing', () => eq(statusFor({ ...base, mode: 'heat', action: 'cooling' }).sub, 'Finishing up · stops soon'));
test('heating_running', () => {
  const r = statusFor({ ...base, action: 'heating', minutesSoFar: null });
  eq(r.word, 'HEATING'); eq(r.mark, '▲'); eq(r.color, '#da5c2c'); eq(r.sub, 'to 72° · just started');
  eq(statusFor({ ...base, action: 'heating', minutesSoFar: 18 }).sub, 'to 72° · 18 min so far');
  eq(statusFor({ ...base, action: 'heating', minutesSoFar: 65 }).sub, 'to 72° · 1 h 5 min so far');
  eq(statusFor({ ...base, action: 'heating', minutesSoFar: 0 }).sub, 'to 72° · just started');
});
test('cooling_running', () => {
  const r = statusFor({ ...base, mode: 'heat_cool', action: 'cooling', minutesSoFar: 3 });
  eq(r.word, 'COOLING'); eq(r.mark, '▼'); eq(r.color, '#2a7fff'); eq(r.sub, 'to 72° · 3 min so far');
});
test('off_and_fan', () => {
  let r = statusFor({ ...base, mode: 'off', action: 'off' });
  eq(r.word, 'OFF'); eq(r.mark, '·'); eq(r.color, '#b4b4b4'); eq(r.sub, 'System is off');
  r = statusFor({ ...base, mode: 'off', action: 'off', callFan: true });
  eq(r.word, 'FAN'); eq(r.sub, 'System is off · fan on');
});
test('idle_holding_and_fan', () => {
  let r = statusFor({ ...base });
  eq(r.word, 'IDLE'); eq(r.mark, '·'); eq(r.sub, 'holding 72°');
  r = statusFor({ ...base, action: 'fan', callFan: true });
  eq(r.word, 'FAN'); eq(r.color, '#b4b4b4');
});
test('idle_waiting_reason', () => eq(statusFor({ ...base, action: 'idle', waitReason: 'Short-cycle protection' }).sub, 'Waiting · short-cycle protection'));

test('target_label', () => {
  eq(targetLabel({ mode: 'heat', level: 'Comfort', hold: false, holdKind: null, manual: false }), 'COMFORT TARGET');
  eq(targetLabel({ mode: 'heat', level: 'Eco', hold: false, holdKind: null, manual: false }), 'ECO TARGET');
  eq(targetLabel({ mode: 'heat', level: 'Eco', hold: true, holdKind: 'level', manual: false }), 'ECO TARGET');
  eq(targetLabel({ mode: 'heat', level: 'Comfort', hold: true, holdKind: 'temperature', manual: false }), 'HOLD');
  eq(targetLabel({ mode: 'heat', level: 'Eco', hold: false, holdKind: null, manual: true }), 'TARGET');
  eq(targetLabel({ mode: 'off', level: 'Eco', hold: true, holdKind: 'temperature', manual: false }), 'TARGET');
});
test('hold_kind', () => {
  eq(holdKind('Holding 69° until 10:30 pm'), 'temperature');
  eq(holdKind('Holding Eco until 10:30 pm'), 'level');
  eq(holdKind('Comfort until 5:30 pm'), null);
  eq(holdKind(undefined), null);
});
test('level_send', () => {
  eq(levelShouldSend({ picked: 'Comfort', current: 'Comfort', manual: false }), false);
  eq(levelShouldSend({ picked: 'Comfort', current: 'Comfort', manual: true }), true);
  eq(levelShouldSend({ picked: 'Eco', current: 'Comfort', manual: false }), true);
});
test('units_metric_roundtrip', () => {
  closeTo(toF(22.2222, '°C'), 72, 1e-3); closeTo(fromF(72, '°C'), 22.2222, 1e-3);
  eq(toF(72, '°F'), 72); eq(fromF(72, '°F'), 72); eq(toF(72), 72); eq(fromF(72, undefined), 72);
});

test('countdown_from_action_elapsed', () => {
  const r = countdown({ running: true, actionElapsedS: 60, publishedAtMs: 1000, nowMs: 11000, minS: 180 });
  closeTo(r.leftS, 110, 1e-9); closeTo(r.frac, 70 / 180, 1e-9);
});
test('countdown_clamps_and_missing', () => {
  const done = countdown({ running: true, actionElapsedS: 500, publishedAtMs: 0, nowMs: 0, minS: 180 });
  eq(done.leftS, 0); eq(done.frac, 1);
  assert.deepEqual(countdown({ running: false, actionElapsedS: 1, publishedAtMs: 0, nowMs: 0, minS: 180 }), { leftS: null, frac: 0 });
  assert.deepEqual(countdown({ running: true, actionElapsedS: null, publishedAtMs: 0, nowMs: 0, minS: 180 }), { leftS: null, frac: 0 });
});

test('day_bar_wraps_midnight', () => {
  const bar = dayBar([
    { name: 'Evening', time: '22:00', level: 'Eco' },
    { name: 'Morning', time: '06:00', level: 'Comfort' },
  ]);
  eq(bar.length, 3);
  eq(bar[0].level, 'Eco'); eq(bar[0].flex, 360); eq(bar[0].label, 'Evening');
  eq(bar[1].level, 'Comfort'); eq(bar[1].flex, 960); eq(bar[1].label, 'Morning');
  eq(bar[2].level, 'Eco'); eq(bar[2].flex, 120); eq(bar[2].label, '');
  eq(bar.reduce((a, b) => a + b.flex, 0), 1440);
});
test('day_bar_sorts_and_single', () => {
  const bar = dayBar([{ name: 'B', time: '12:00', level: 'Eco' }, { name: 'A', time: '00:00', level: 'Comfort' }]);
  assert.deepEqual(bar.map(b => b.level), ['Comfort', 'Eco']);
  eq(bar[0].label, 'A');
});

test('debounce_nets_zero', () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const fired = [];
    const d = new Debouncer(1500, v => fired.push(v));
    d.tap(73, 72); mock.timers.tick(500); d.tap(72, 72);
    mock.timers.tick(2000);
    eq(fired.length, 0);
  } finally { mock.timers.reset(); }
});
test('debounce_one_write', () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const fired = [];
    const d = new Debouncer(1500, v => fired.push(v));
    for (const v of [73, 74, 75, 76, 77]) { d.tap(v, 72); mock.timers.tick(400); }
    eq(fired.length, 0);
    mock.timers.tick(1500);
    assert.deepEqual(fired, [77]);
  } finally { mock.timers.reset(); }
});
test('debounce_cancel', () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const fired = [];
    const d = new Debouncer(1500, v => fired.push(v));
    d.tap(80, 72); d.cancel(); mock.timers.tick(5000);
    eq(fired.length, 0);
  } finally { mock.timers.reset(); }
});

// --- − / + taps on the target (TargetTaps: the debouncer plus the base a burst is compared to) ---
function taps(written) {
  return new TargetTaps({ ms: 1500, giveUpMs: 6000, min: 50, max: 90, write: v => written.push(v) });
}
test('taps_second_burst_back_to_start_is_written', () => {
  // 70 -> +2 is written; -2 before the device confirms 72 must write 70, not compare against
  // the stale device value (70) and send nothing (the device would stay on 72, a hold undone).
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    const t = taps(written);
    let now = 0;
    t.step(1, 70, now); t.step(1, 70, now);
    mock.timers.tick(1500); now += 1500;
    assert.deepEqual(written, [72]);
    t.settle(70, now);           // the device hasn't reported 72 yet
    t.step(-1, 70, now); t.step(-1, 70, now);
    eq(t.pending, 70);
    mock.timers.tick(1500); now += 1500;
    assert.deepEqual(written, [72, 70]);
    t.settle(72, now); eq(t.pending, 70);   // the first write landing doesn't end the second
    t.settle(70, now); eq(t.pending, null);
  } finally { mock.timers.reset(); }
});
test('taps_net_zero_after_unconfirmed_write', () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    const t = taps(written);
    t.step(2, 70, 0);
    mock.timers.tick(1500);
    t.step(1, 70, 1500); t.step(-1, 70, 1500);   // back to the written 72: nothing new to send
    mock.timers.tick(1500);
    assert.deepEqual(written, [72]);
  } finally { mock.timers.reset(); }
});
test('taps_base_returns_to_device_after_confirm_or_give_up', () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    const t = taps(written);
    t.step(2, 70, 0); mock.timers.tick(1500);
    t.settle(72, 1500); eq(t.pending, null);
    t.step(-2, 72, 1600); mock.timers.tick(1500);
    assert.deepEqual(written, [72, 70]);
    t.settle(null, 1600 + 7600);                   // never confirmed: give up
    eq(t.pending, null);
    t.step(1, 74, 10000); mock.timers.tick(1500);  // base is the device again
    assert.deepEqual(written, [72, 70, 75]);
  } finally { mock.timers.reset(); }
});
test('taps_detach_flushes_when_bound', () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    const t = taps(written);
    t.step(1, 70, 0); t.step(1, 70, 0);
    t.detach(true);
    assert.deepEqual(written, [72]);
    eq(t.pending, 72);                             // still shown until the device reports it
    mock.timers.tick(5000);
    assert.deepEqual(written, [72]);
  } finally { mock.timers.reset(); }
});
test('taps_detach_drops_when_unbound', () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    const t = taps(written);
    t.step(1, 70, 0);
    t.detach(false);
    eq(t.pending, null);                           // the display doesn't keep a value nobody sends
    mock.timers.tick(5000);
    assert.deepEqual(written, []);
  } finally { mock.timers.reset(); }
});
test('taps_detach_net_zero_sends_nothing', () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    const t = taps(written);
    t.step(1, 70, 0); t.step(-1, 70, 0);
    t.detach(true);
    mock.timers.tick(5000);
    assert.deepEqual(written, []);
  } finally { mock.timers.reset(); }
});

// A write that fails (the websocket call rejects, or the thermostat went offline mid-burst).
const settleMicrotasks = () => new Promise((r) => setImmediate(r));
function failingTaps(written, fails, onFailed) {
  return new TargetTaps({
    ms: 1500, giveUpMs: 6000, min: 50, max: 90, onFailed,
    write: (v) => { written.push(v); return fails.has(v) ? Promise.reject(new Error('rejected')) : Promise.resolve(); },
  });
}
test('taps_failure_when_idle_shows_the_device_again', async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    let failedCalls = 0;
    const t = failingTaps(written, new Set([72]), () => failedCalls++);
    t.step(1, 70, 0); t.step(1, 70, 0);
    mock.timers.tick(1500);
    await settleMicrotasks();
    assert.deepEqual(written, [72]);
    eq(t.pending, null); eq(t.written, null); eq(failedCalls, 1);
  } finally { mock.timers.reset(); }
});
test('taps_failure_mid_burst_keeps_the_new_burst', async () => {
  // Write A (71) fails while burst B is under way: B keeps counting from its own value and is then
  // written against the device's value (not against the failed 71).
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    const t = failingTaps(written, new Set([71]));
    t.step(1, 70, 0);
    mock.timers.tick(1500);                     // A: 71 sent
    t.step(1, 70, 1500);                        // B starts: 72
    await settleMicrotasks();                   // A's rejection lands mid-burst
    eq(t.pending, 72);
    t.step(1, 70, 1600);                        // the next + shows 73, not 71
    eq(t.pending, 73);
    mock.timers.tick(1500);
    assert.deepEqual(written, [71, 73]);
  } finally { mock.timers.reset(); }
});
test('taps_failed_value_is_resent_when_a_burst_returns_to_it', async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    const t = failingTaps(written, new Set([71]));
    t.step(1, 70, 0);
    mock.timers.tick(1500);                     // A: 71 sent
    t.step(1, 70, 1500); t.step(-1, 70, 1500);  // B ends on 71 again
    await settleMicrotasks();                   // A failed, so 71 never reached the device
    written.length = 0;
    mock.timers.tick(1500);
    assert.deepEqual(written, [71]);
  } finally { mock.timers.reset(); }
});
test('taps_stale_failure_is_ignored', async () => {
  // A late rejection of an older write must not wipe a newer one.
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    let rejectA;
    const t = new TargetTaps({
      ms: 1500, giveUpMs: 6000, min: 50, max: 90,
      write: (v) => { written.push(v); return v === 71 ? new Promise((_, rej) => { rejectA = rej; }) : Promise.resolve(); },
    });
    t.step(1, 70, 0);
    mock.timers.tick(1500);                     // A: 71 sent, still in flight
    t.step(1, 70, 1500);
    mock.timers.tick(1500);                     // B: 72 sent
    rejectA(new Error('late'));
    await settleMicrotasks();
    assert.deepEqual(written, [71, 72]);
    eq(t.pending, 72); eq(t.written, 72);
  } finally { mock.timers.reset(); }
});
test('taps_fractional_steps_round_and_clamp', () => {
  // The schedule's eco offset steps by its entity's step (0.5 here) within its min/max.
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const written = [];
    const t = new TargetTaps({ ms: 800, giveUpMs: 6000, min: 0, max: 3, write: (v) => written.push(v) });
    t.step(0.1, 2, 0); t.step(0.1, 2, 0); t.step(0.1, 2, 0);
    eq(t.pending, 2.3);                         // not 2.3000000000000003
    t.step(0.5, 2, 0); t.step(0.5, 2, 0);
    eq(t.pending, 3);
    mock.timers.tick(800);
    assert.deepEqual(written, [3]);
  } finally { mock.timers.reset(); }
});

test('day_bar_before_first_uses_the_previous_days_last_period', () => {
  // Monday before wake: the thermostat still follows Sunday's (weekend) sleep level.
  const weekday = [
    { name: 'wake', time: '06:00', level: 'Comfort' }, { name: 'leave', time: '08:00', level: 'Eco' },
    { name: 'return', time: '17:00', level: 'Comfort' }, { name: 'sleep', time: '22:00', level: 'Eco' },
  ];
  const bar = dayBar(weekday, { name: 'sleep', level: 'Comfort' });
  eq(bar[0].level, 'Comfort'); eq(bar[0].flex, 360); eq(bar[0].label, 'sleep');
  eq(bar[bar.length - 1].level, 'Eco');
  eq(dayBar(weekday)[0].level, 'Eco');         // without one, the day's own last period
});

// --- System tab: safety bars (countdown from action_elapsed) and event-log wording ---
const mins = { heatRun: 3, heatOff: 5, coolRun: 4, coolOff: 6 };
// The relays follow the action here (call_heat while heating, call_cool while cooling).
const at = (action, elapsedS, extra = {}) => safetyRows({
  action, callHeat: action == null ? null : action === 'heating', callCool: action == null ? null : action === 'cooling',
  interlockFault: false, actionElapsedS: elapsedS, publishedAtMs: 1000, nowMs: 1000, mins, ...extra,
});

test('safety_running_unit_comes_from_the_relays', () => {
  // The interlock latch cuts W while the climate still says heating: no row may claim the
  // furnace is running, and its min off can't be timed (the trip time isn't published).
  const latched = at('heating', 60, { callHeat: false, interlockFault: true });
  for (const k of ['heatRun', 'heatOff', 'coolRun', 'coolOff']) eq(latched[k].val, '—');
  // W off but the action still says heating (no fault): don't count min off from the heat start.
  const stale = at('heating', 60, { callHeat: false });
  eq(stale.heatOff.val, '—'); eq(stale.heatRun.val, '—');
  // W on: the furnace rows, whatever the action says.
  eq(at('idle', 60, { callHeat: true }).heatRun.val, '2 min left');
  eq(at('idle', 60, { callCool: true }).coolOff.val, 'running');
});

test('safety_heating_counts_min_run', () => {
  const r = at('heating', 60);
  eq(r.heatRun.val, '2 min left'); closeTo(r.heatRun.frac, 1 / 3, 1e-9);
  eq(r.heatOff.val, 'running'); eq(r.heatOff.frac, 0);
  eq(r.coolRun.val, '✓ ok');
  eq(r.coolOff.val, '—'); // unknowable while the furnace runs
  eq(at('heating', 200).heatRun.val, '✓ ok');
  eq(at('heating', 200).heatRun.frac, 1);
});
test('safety_interpolates_since_publish', () => {
  const r = safetyRows({ action: 'cooling', callHeat: false, callCool: true, actionElapsedS: 0, publishedAtMs: 0, nowMs: 150_000, mins });
  eq(r.coolRun.val, '2 min left'); // 4 min − 2.5 min = 1.5 → ceil
  eq(r.heatOff.val, '—');
});
test('safety_idle_counts_min_off', () => {
  const r = at('idle', 120);
  eq(r.heatOff.val, '3 min left'); closeTo(r.heatOff.frac, 120 / 300, 1e-9);
  eq(r.coolOff.val, '4 min left');
  eq(r.heatRun.val, '✓ ok'); eq(r.heatRun.frac, 0);
  const done = at('off', 3600);
  eq(done.heatOff.val, '✓ ready'); eq(done.heatOff.frac, 0);
  eq(done.coolOff.val, '✓ ready');
  eq(at('fan', 60).heatOff.val, '4 min left');
});
test('safety_unknown_shows_dash', () => {
  for (const r of [at(null, 60), at('heating', null), safetyRows({ action: 'heating', callHeat: true, callCool: false, actionElapsedS: 60, publishedAtMs: 1000, nowMs: 1000, mins: { ...mins, heatRun: null } })]) {
    eq(r.heatRun.val, '—');
    eq(r.heatRun.frac, 0);
  }
  eq(at(null, 60).coolOff.val, '—');
});
test('event_text_plain_wording', () => {
  eq(eventText('call_heat', 'on').msg, 'furnace on');
  eq(eventText('call_heat', 'on').kind, 'heat');
  eq(eventText('call_heat', 'off').msg, 'furnace off');
  eq(eventText('call_cool', 'on').msg, 'ac on');
  eq(eventText('call_cool', 'on').kind, 'cool');
  eq(eventText('sensor_fault', 'on').msg, 'temperature sensor problem · heating and cooling paused');
  eq(eventText('sensor_fault', 'on').kind, 'fault');
  eq(eventText('sensor_fault', 'off').msg, 'temperature sensor ok again');
  eq(eventText('interlock_fault', 'on').msg, 'interlock tripped · heating and cooling paused');
  eq(eventText('interlock_fault', 'off').msg, 'interlock cleared');
  eq(eventText('schedule_hold', 'on').msg, 'hold started');
  eq(eventText('schedule_hold', 'off').msg, 'hold ended · following the schedule');
  eq(eventText('schedule_period', 'Leave').msg, 'schedule · leave period');
  eq(eventText('call_heat', 'unavailable').msg, 'thermostat offline');
  eq(eventText('call_cool', 'unavailable'), null); // one offline line, not six
  eq(eventText('schedule_period', 'unknown'), null);
  eq(eventText('nope', 'on'), null);
});
