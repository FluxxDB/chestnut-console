import test from 'node:test';
import assert from 'node:assert/strict';
import { Adapter } from '../../config/www/chestnut/lib/adapter.js';

const MAC = 'AA:BB:CC:DD:EE:FF';
const DEV = 'ff35ffb8f402edcad071d15648476dda';
const STUB = 'aaaa0000stub';

// Registry entries in the real core.entity_registry format: "<MAC>/0/<domain>/<Name>".
function entry(entity_id, domain, name, extra = {}) {
  return {
    entity_id, unique_id: `${MAC}/0/${domain}/${name}`, device_id: DEV,
    platform: 'esphome', original_name: name, ...extra,
  };
}

function makeHass({ states = {}, registry, callWS } = {}) {
  const reg = registry || [
    entry('sensor.main_thermostat_room_temperature', 'sensor', 'Room Temperature'),
    entry('number.main_thermostat_set_target', 'number', 'Set Target'),
    entry('climate.main_thermostat_main_thermostat', 'climate', 'Main Thermostat'),
    entry('binary_sensor.main_thermostat_call_heat', 'binary_sensor', 'Call Heat'),
    // stale M3 stub: same object id, different device/platform
    { entity_id: 'sensor.room_temperature', unique_id: 'stub-room', device_id: STUB, platform: 'template', original_name: 'Room Temperature' },
  ];
  const calls = [];
  const wsCalls = [];
  const hass = {
    states,
    devices: {
      [DEV]: { id: DEV, name: 'Main Thermostat', name_by_user: null },
      [STUB]: { id: STUB, name: 'Stub', name_by_user: null },
    },
    entities: {},
    callService: async (domain, service, data) => { calls.push({ domain, service, data }); },
    callWS: callWS || (async (msg) => { wsCalls.push(msg); return msg.type === 'config/entity_registry/list' ? reg : {}; }),
    connection: {},
  };
  if (callWS) {
    const inner = callWS;
    hass.callWS = async (msg) => { wsCalls.push(msg); return msg.type === 'config/entity_registry/list' ? reg : inner(msg); };
  }
  return { hass, calls, wsCalls };
}

const st = (state, attributes = {}) => ({ state, attributes });

test('resolves_by_device', async () => {
  const { hass } = makeHass({ states: {
    'sensor.main_thermostat_room_temperature': st('70', { unit_of_measurement: '°F' }),
    'sensor.room_temperature': st('11', { unit_of_measurement: '°F' }),
  } });
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  const map = await a.resolve();
  assert.equal(map.room_temperature, 'sensor.main_thermostat_room_temperature');
  assert.equal(map.set_target, 'number.main_thermostat_set_target');
  assert.equal(map.main_thermostat, 'climate.main_thermostat_main_thermostat');
  assert.equal(map.call_heat, 'binary_sensor.main_thermostat_call_heat');
  assert.equal(a.num('room_temperature'), 70);
  assert.ok(!Object.values(map).includes('sensor.room_temperature'));
});

test('resolves_by_device uses name_by_user and falls back to entity_id suffix', async () => {
  const reg = [{ entity_id: 'sensor.tab5_room_temperature', unique_id: 'weird', device_id: DEV, platform: 'esphome' }];
  const { hass } = makeHass({ registry: reg });
  hass.devices[DEV] = { id: DEV, name: 'x', name_by_user: 'Tab5' };
  hass.states['sensor.tab5_room_temperature'] = st('71', { unit_of_measurement: '°F' });
  const a = new Adapter(hass, { deviceName: 'Tab5' });
  await a.resolve();
  assert.equal(a.num('room_temperature'), 71);
});

test('unavailable_is_dash', async () => {
  const states = { 'sensor.main_thermostat_room_temperature': st('unavailable', { unit_of_measurement: '°C' }) };
  const { hass } = makeHass({ states });
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  assert.equal(a.num('room_temperature'), null);
  for (const s of ['unknown', '', 'abc', 'NaN']) {
    states['sensor.main_thermostat_room_temperature'] = st(s, { unit_of_measurement: '°C' });
    assert.equal(a.num('room_temperature'), null, s);
  }
  assert.equal(a.num('nonexistent'), null);
  assert.equal(a.on('call_heat'), null);
  assert.equal(a.online(), false);
});

test('units_metric_read', async () => {
  const { hass } = makeHass({ states: {
    'sensor.main_thermostat_room_temperature': st('20', { unit_of_measurement: '°C' }),
    'number.main_thermostat_set_target': st('72', { unit_of_measurement: '°F' }),
  } });
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  assert.equal(a.num('room_temperature'), 68);
  assert.equal(a.num('set_target'), 72);
});

test('on/str/online', async () => {
  const { hass } = makeHass({ states: {
    'binary_sensor.main_thermostat_call_heat': st('on'),
    'climate.main_thermostat_main_thermostat': st('heat'),
  } });
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  assert.equal(a.on('call_heat'), true);
  hass.states['binary_sensor.main_thermostat_call_heat'] = st('off');
  assert.equal(a.on('call_heat'), false);
  hass.states['binary_sensor.main_thermostat_call_heat'] = st('unavailable');
  assert.equal(a.on('call_heat'), null);
  assert.equal(a.str('main_thermostat'), 'heat');
  assert.equal(a.online(), true);
  hass.states['climate.main_thermostat_main_thermostat'] = st('unavailable');
  assert.equal(a.online(), false);
});

test('sim_absent_after_m4', async () => {
  const { hass } = makeHass();
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  assert.equal(a.simPresent(), false);
});

test('sim_unavailable_still_present', async () => {
  const registry = [
    entry('climate.main_thermostat_main_thermostat', 'climate', 'Main Thermostat'),
    entry('number.main_thermostat_sim_outdoor_f', 'number', 'Sim Outdoor F'),
  ];
  const { hass } = makeHass({ registry, states: { 'number.main_thermostat_sim_outdoor_f': st('unavailable') } });
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  assert.equal(a.simPresent(), true);
});

test('sim_orphaned_entry_is_absent', async () => {
  const registry = [entry('number.main_thermostat_sim_outdoor_f', 'number', 'Sim Outdoor F', { orphaned_timestamp: 123 })];
  const { hass } = makeHass({ registry });
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  assert.equal(a.simPresent(), false);
});

test('set_target_writes_entity_unit', async () => {
  const { hass, calls } = makeHass({ states: {
    'number.main_thermostat_set_target': st('20', { unit_of_measurement: '°C' }),
  } });
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  await a.setTargetF(68);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].domain, 'number');
  assert.equal(calls[0].service, 'set_value');
  assert.equal(calls[0].data.entity_id, 'number.main_thermostat_set_target');
  assert.ok(Math.abs(calls[0].data.value - 20) < 1e-9);
  hass.states['number.main_thermostat_set_target'] = st('68', { unit_of_measurement: '°F' });
  await a.setTargetF(70);
  assert.equal(calls[1].data.value, 70);
});

test('call passes entity_id plus data', async () => {
  const { hass, calls } = makeHass();
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  await a.call('number', 'set_value', 'set_target', { value: 5 });
  assert.deepEqual(calls[0], { domain: 'number', service: 'set_value', data: { entity_id: 'number.main_thermostat_set_target', value: 5 } });
});

test('history maps back to object ids and converts temperature', async () => {
  const t0 = Date.parse('2026-10-29T10:00:00Z');
  const { hass, wsCalls } = makeHass({
    states: { 'sensor.main_thermostat_room_temperature': st('20', { unit_of_measurement: '°C' }) },
    callWS: async () => ({
      'sensor.main_thermostat_room_temperature': [
        { s: '20', lu: t0 / 1000 }, { s: 'unavailable', lu: t0 / 1000 + 60 }, { s: '25', lu: t0 / 1000 + 120 },
      ],
    }),
  });
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  const h = await a.history(['room_temperature'], 6);
  const req = wsCalls.find((m) => m.type === 'history/history_during_period');
  assert.deepEqual(req.entity_ids, ['sensor.main_thermostat_room_temperature']);
  assert.equal(req.minimal_response, true);
  assert.equal(req.no_attributes, true);
  assert.equal(Date.parse(req.end_time) - Date.parse(req.start_time), 6 * 3600 * 1000);
  assert.deepEqual(h.room_temperature, [{ t: t0, v: 68 }, { t: t0 + 120000, v: 77 }]);
});

test('logbook returns newest first', async () => {
  const { hass, wsCalls } = makeHass({
    callWS: async () => [
      { when: 1, entity_id: 'binary_sensor.main_thermostat_call_heat', state: 'on', message: 'turned on' },
      { when: 3, entity_id: 'binary_sensor.main_thermostat_call_heat', state: 'off', message: 'turned off' },
      { when: '1970-01-01T00:00:02Z', entity_id: 'binary_sensor.main_thermostat_call_heat', message: 'x' },
    ],
  });
  const a = new Adapter(hass, { deviceName: 'Main Thermostat' });
  await a.resolve();
  const l = await a.logbook(['call_heat'], 2);
  const req = wsCalls.find((m) => m.type === 'logbook/get_events');
  assert.deepEqual(req.entity_ids, ['binary_sensor.main_thermostat_call_heat']);
  assert.deepEqual(l.map((e) => e.t), [3000, 2000, 1000]);
  assert.equal(l[0].msg, 'turned off');
});
