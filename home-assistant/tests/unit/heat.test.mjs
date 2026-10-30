import test from 'node:test';
import assert from 'node:assert/strict';
import { heatColor, HeatField, fieldInputs } from '../../config/www/chestnut/lib/heat.js';

function deepClose(a, b, tol) {
  assert.equal(a.length, b.length);
  for (let i = 0; i < a.length; i++) assert.ok(Math.abs(a[i] - b[i]) <= tol, `index ${i}: ${a[i]} vs ${b[i]} (tol ${tol})`);
}
const HEAT = { roomF: 71.3, outdoorF: 30, heat: true, cool: false, fanOn: false, frozen: false };

test('heat_scale_ends', () => { deepClose(heatColor(60).slice(0, 3), [42, 127, 255], 1); deepClose(heatColor(80).slice(0, 3), [218, 92, 44], 1); });
test('heat_scale_alpha', () => { assert.equal(heatColor(70)[3], 0.9); });
test('heat_scale_clamps', () => { deepClose(heatColor(40), heatColor(60), 0); deepClose(heatColor(108), heatColor(80), 0); });
test('heat_scale_monotonic_red', () => { for (let t = 60; t < 80; t += 0.5) assert.ok(heatColor(t + 0.5)[0] >= heatColor(t)[0] - 1e-9); });
test('field_mean_pinned', () => {
  const f = new HeatField();
  for (let i = 0; i < 200; i++) f.step(1 / 30, HEAT);
  assert.ok(Math.abs(f.mean() - 71.3) < 1e-3);
});
test('field_heat_warmer_at_vent', () => {
  const f = new HeatField();
  for (let i = 0; i < 120; i++) f.step(1 / 30, HEAT);
  assert.ok(f.T[3 * f.w + 14] > f.mean());
  assert.ok(Math.abs(f.mean() - 71.3) < 1e-3);
});
test('field_cool_colder_at_vent', () => {
  const f = new HeatField();
  for (let i = 0; i < 120; i++) f.step(1 / 30, { ...HEAT, heat: false, cool: true });
  assert.ok(f.T[3 * f.w + 14] < f.mean());
});
test('field_frozen_holds', () => {
  const f = new HeatField();
  for (let i = 0; i < 30; i++) f.step(1 / 30, HEAT);
  const before = Float32Array.from(f.T);
  f.step(1 / 30, { ...HEAT, frozen: true, roomF: 50 });
  deepClose(f.T, before, 0);
});
test('field_to_image_data', () => {
  const f = new HeatField();
  const d = new Uint8ClampedArray(f.w * f.h * 4);
  f.toImageData(d);
  assert.equal(d[3], Math.round(0.9 * 255));
});

// fieldInputs: what the room view feeds HeatField.step from a live reading and the outdoor value.
const LIVE = { room: 70.4, sensorFault: false, heat: true, cool: false, air: true };
test('field_inputs_no_outdoor_keeps_animating', () => {
  for (const out of [null, undefined, NaN]) {
    const r = fieldInputs(LIVE, out);
    assert.equal(r.frozen, false, `outdoor ${out}`);
    assert.equal(r.outdoorF, 70.4);
    assert.equal(r.roomF, 70.4);
  }
});
test('field_inputs_passes_outdoor_and_calls', () => {
  assert.deepEqual(fieldInputs(LIVE, 20), { roomF: 70.4, outdoorF: 20, heat: true, cool: false, fanOn: true, frozen: false });
});
test('field_inputs_freezes_on_fault_bad_room_or_offline', () => {
  assert.equal(fieldInputs({ ...LIVE, sensorFault: true }, 20).frozen, true);
  assert.equal(fieldInputs({ ...LIVE, room: null }, 20).frozen, true);
  assert.equal(fieldInputs({ ...LIVE, room: NaN }, null).frozen, true);
  const off = fieldInputs(null, 20);
  assert.equal(off.frozen, true);
  assert.equal(off.heat || off.cool || off.fanOn, false);
});
test('field_inputs_no_outdoor_never_poisons_field', () => {
  const f = new HeatField();
  for (let i = 0; i < 60; i++) f.step(1 / 30, fieldInputs(LIVE, null));
  assert.ok(Number.isFinite(f.mean()) && Math.abs(f.mean() - 70.4) < 1e-3, String(f.mean()));
});
