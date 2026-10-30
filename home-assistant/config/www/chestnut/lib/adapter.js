// The only layer that touches Home Assistant's `hass` object.
import { toF, fromF } from './rules.js';

const DEAD = new Set(['unavailable', 'unknown', '']);
const TEMP_UNITS = new Set(['°C', '°F']);

// Real ESPHome unique_id: "<MAC>/0/<esphome type>/<Entity Name>", e.g.
// "AA:BB:CC:DD:EE:FF/0/sensor/Room Temperature" -> object id "room_temperature".
// The type segment is the ESPHome type and need not equal the HA entity_id domain
// (text_sensor -> sensor.*, datetime -> time.*), so only the LAST segment is used.
// config/entity_registry/list returns full entries incl. unique_id (partial_json_repr).
function slug(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

function objectIdOf(entry) {
  const uid = String(entry.unique_id || '');
  const parts = uid.split('/');
  if (parts.length >= 4) return slug(parts[parts.length - 1]);
  const m = uid.match(new RegExp(`-${entry.entity_id.split('.')[0]}-(.+)$`));
  return m ? slug(m[1]) : null;
}

function toMs(v) {
  if (typeof v === 'number') return v < 1e11 ? v * 1000 : v; // HA sends epoch seconds (history minimal_response `lu`, logbook `when`)
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? ms : null;
}

export class Adapter {
  constructor(hass, { deviceName }) {
    this.hass = hass;
    this.deviceName = deviceName;
    this.map = {};
    this.entries = [];
    this.found = null; // after resolve(): whether a device named deviceName exists
  }

  // Async: the frontend registry lacks unique_id, so ask the websocket for full entries.
  async resolve() {
    const hass = this.hass;
    const ids = Object.values(hass.devices || {})
      .filter((d) => (d.name_by_user || d.name) === this.deviceName)
      .map((d) => d.id);
    this.found = ids.length > 0;
    const all = await hass.callWS({ type: 'config/entity_registry/list' });
    const mine = all.filter((e) => ids.includes(e.device_id) && e.platform === 'esphome');
    const map = {};
    const entries = [];
    for (const e of mine) {
      let obj = objectIdOf(e);
      if (!obj && e.original_name) obj = slug(e.original_name);
      if (!obj) {
        entries.push({ ...e, objectId: null });
        continue;
      }
      map[obj] = e.entity_id;
      entries.push({ ...e, objectId: obj });
    }
    this.map = map;
    this.entries = entries;
    return map;
  }

  // Map hit first; else fallback: a registry entry whose entity_id is <domain>.<anything>_<objId>.
  _id(objId) {
    if (this.map[objId]) return this.map[objId];
    const hit = this.entries.find((e) => e.entity_id.split('.')[1].endsWith(`_${objId}`));
    return hit ? hit.entity_id : undefined;
  }

  _state(objId) {
    const id = this._id(objId);
    return id ? this.hass.states[id] : undefined;
  }

  str(objId) {
    const s = this._state(objId);
    return s ? s.state : null;
  }

  num(objId) {
    const s = this._state(objId);
    if (!s || DEAD.has(s.state)) return null;
    const n = Number(s.state);
    if (!Number.isFinite(n)) return null;
    const unit = s.attributes && s.attributes.unit_of_measurement;
    return TEMP_UNITS.has(unit) ? toF(n, unit) : n;
  }

  on(objId) {
    const s = this._state(objId);
    if (!s || s.state === 'unavailable' || s.state === 'unknown') return null;
    if (s.state === 'on') return true;
    if (s.state === 'off') return false;
    return null;
  }

  // An attribute of a live entity (null when absent, unavailable or unknown), e.g. the
  // climate's hvac_action / fan_mode / fan_modes.
  attr(objId, name) {
    const s = this._state(objId);
    if (!s || DEAD.has(s.state) || !s.attributes) return null;
    return s.attributes[name] ?? null;
  }

  // When HA last wrote the entity's state (ms), e.g. to interpolate action_elapsed.
  updatedMs(objId) {
    const s = this._state(objId);
    if (!s) return null;
    const v = s.last_updated ?? s.last_changed;
    return v == null ? null : toMs(v);
  }

  // The device registry entry of the resolved device (hass.devices: sw_version etc.), or null.
  deviceEntry() {
    const e = this.entries.find((x) => x.device_id);
    return (e && this.hass.devices && this.hass.devices[e.device_id]) || null;
  }

  online() {
    const s = this._state('main_thermostat');
    return !!s && s.state !== 'unavailable';
  }

  // Rule: an active registry entry for the device with object id sim_* means present (even if
  // its state is unavailable); none means absent. Evidence (HA 2026.10): when the firmware stops
  // providing an ESPHome entity, HA moves it from `entities` to `deleted_entities`, so an entry in
  // the active list == provided by the firmware. (orphaned_timestamp exists only on deleted entries.)
  simPresent() {
    return this.entries.some((e) => (e.objectId || '').startsWith('sim_'));
  }

  _unit(objId) {
    const s = this._state(objId);
    return s && s.attributes ? s.attributes.unit_of_measurement : undefined;
  }

  call(domain, service, objId, data = {}) {
    return this.hass.callService(domain, service, { entity_id: this._id(objId), ...data });
  }

  // number.set_value of a °F value, written in the entity's own unit (HA shows a temperature
  // number such as set_target or comfort_target in °C when it runs metric).
  setNumberF(objId, f) {
    return this.call('number', 'set_value', objId, { value: fromF(f, this._unit(objId)) });
  }

  setTargetF(f) {
    return this.setNumberF('set_target', f);
  }

  // A number's min / max / step in °F (converted like num() for a temperature unit), or null.
  // HA's step in °C says nothing reliable about the device's °F step (M2 uses whole °F), so a
  // number shown in °C steps by 1 °F.
  rangeF(objId) {
    const lo = this.attr(objId, 'min');
    const hi = this.attr(objId, 'max');
    const step = this.attr(objId, 'step');
    if (![lo, hi].every((v) => typeof v === 'number' && Number.isFinite(v))) return null;
    const unit = this._unit(objId);
    if (unit !== '°C') return { min: lo, max: hi, step: typeof step === 'number' && step > 0 ? step : 1 };
    return { min: Math.round(toF(lo, unit)), max: Math.round(toF(hi, unit)), step: 1 };
  }

  async history(objIds, hours) {
    const end = new Date();
    const start = new Date(end.getTime() - hours * 3600 * 1000);
    const byEntity = {};
    for (const o of objIds) if (this._id(o)) byEntity[this._id(o)] = o;
    const res = await this.hass.callWS({
      type: 'history/history_during_period',
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      entity_ids: Object.keys(byEntity),
      minimal_response: true,
      no_attributes: true,
    });
    const out = {};
    for (const o of objIds) out[o] = [];
    for (const [eid, rows] of Object.entries(res || {})) {
      const o = byEntity[eid];
      if (!o) continue;
      const unit = this._unit(o);
      for (const r of rows) {
        const t = toMs(r.lu ?? r.last_updated ?? r.lc ?? r.last_changed);
        if (t == null || DEAD.has(r.s ?? r.state)) continue;
        const raw = r.s ?? r.state;
        const n = Number(raw);
        out[o].push({ t, v: Number.isFinite(n) ? (TEMP_UNITS.has(unit) ? toF(n, unit) : n) : raw });
      }
    }
    return out;
  }

  async logbook(objIds, hours) {
    const end = new Date();
    const start = new Date(end.getTime() - hours * 3600 * 1000);
    const ids = objIds.map((o) => this._id(o)).filter(Boolean);
    const res = await this.hass.callWS({
      type: 'logbook/get_events',
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      entity_ids: ids,
    });
    const byEntity = {};
    for (const o of objIds) if (this._id(o)) byEntity[this._id(o)] = o;
    return (res || [])
      .map((e) => ({
        t: toMs(e.when),
        objId: byEntity[e.entity_id] ?? null,
        state: e.state ?? null,
        msg: e.message || (e.state ? `changed to ${e.state}` : ''),
      }))
      .filter((e) => e.t != null)
      .sort((a, b) => b.t - a.t);
  }
}
