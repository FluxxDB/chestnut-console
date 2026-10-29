// Heat colour scale and room heat field. Pure, dependency-free (no DOM, no canvas).
// Ported from docs/design-mockups/ha-dashboard/Main.dc.html (heatColor, initField, sample, stepField, drawField).

const toLin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
const toLab = (r, g, b) => {
  r = toLin(r); g = toLin(g); b = toLin(b);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
};
const fromLab = (L, A, B) => {
  const l = Math.pow(L + 0.3963377774 * A + 0.2158037573 * B, 3);
  const m = Math.pow(L - 0.1055613458 * A - 0.0638541728 * B, 3);
  const s = Math.pow(L - 0.0894841775 * A - 1.291485548 * B, 3);
  const enc = (c) => 255 * Math.max(0, Math.min(1, c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055));
  return [
    enc(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    enc(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    enc(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ];
};

const LAB_COLD = toLab(42, 127, 255);  // 60 F  #2a7fff
const LAB_HOT = toLab(218, 92, 44);    // 80 F  #da5c2c

// Two colours blended in OKLab, smoothstepped, clamped to 60..80 F. Returns [r, g, b, a] with r,g,b in 0..255 and a = 0.9.
export function heatColor(tempF) {
  const f = (Math.max(60, Math.min(80, tempF)) - 60) / 20;
  const k = f * f * (3 - 2 * f);
  const rgb = fromLab(
    LAB_COLD[0] + (LAB_HOT[0] - LAB_COLD[0]) * k,
    LAB_COLD[1] + (LAB_HOT[1] - LAB_COLD[1]) * k,
    LAB_COLD[2] + (LAB_HOT[2] - LAB_COLD[2]) * k,
  );
  return [rgb[0], rgb[1], rgb[2], 0.9];
}

const SUPPLY_HEAT_F = 108;
const SUPPLY_COOL_F = 55;

export class HeatField {
  constructor(w = 64, h = 40) {
    this.w = w; this.h = h;
    this.T = new Float32Array(w * h).fill(70);
    this.T2 = new Float32Array(w * h);
    this.vents = [{ x: 14, y: 1, dx: 0, dy: 1 }, { x: 42, y: 1, dx: 0, dy: 1 }, { x: 62, y: 28, dx: -1, dy: 0 }];
    this.U = new Float32Array(w * h);
    this.V = new Float32Array(w * h);
    this._time = 0;
    this._primed = false;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let u = 0, v = 0;
        for (const vt of this.vents) {
          const rx = x - vt.x, ry = y - vt.y;
          const along = rx * vt.dx + ry * vt.dy;
          if (along <= 0) continue;
          const perp = Math.abs(rx * vt.dy - ry * vt.dx);
          const wdt = 2 + along * 0.35;
          const k = Math.exp(-along / 26) * Math.exp(-(perp * perp) / (2 * wdt * wdt));
          u += vt.dx * k; v += vt.dy * k;
        }
        const rx = 5 - x, ry = 38 - y, d = Math.hypot(rx, ry) + 1;
        u += (rx / d) * 0.25 * Math.exp(-d / 40);
        v += (ry / d) * 0.25 * Math.exp(-d / 40);
        this.U[y * w + x] = u;
        this.V[y * w + x] = v;
      }
    }
  }

  _sample(T, x, y) {
    const W = this.w, H = this.h;
    x = Math.max(0, Math.min(W - 1.001, x));
    y = Math.max(0, Math.min(H - 1.001, y));
    const x0 = x | 0, y0 = y | 0, fx = x - x0, fy = y - y0;
    const i = y0 * W + x0;
    return (T[i] * (1 - fx) + T[i + 1] * fx) * (1 - fy) + (T[i + W] * (1 - fx) + T[i + W + 1] * fx) * fy;
  }

  // inputs: {roomF, outdoorF, heat, cool, fanOn, frozen}. frozen:true leaves the field untouched.
  step(dt, inputs) {
    if (inputs.frozen) return;
    const { roomF, outdoorF, heat, cool, fanOn } = inputs;
    const W = this.w, H = this.h, T = this.T, T2 = this.T2;
    if (!this._primed) { T.fill(roomF); this._primed = true; }
    this._time += dt;
    const air = !!(heat || cool || fanOn);
    const sp = air ? 9 : 0;
    const tt = this._time;
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const i = y * W + x;
        let u = this.U[i], v = this.V[i];
        if (air) { u += 0.12 * Math.sin(tt * 0.05 + y * 0.21); v += 0.12 * Math.cos(tt * 0.04 + x * 0.17); }
        T2[i] = sp ? this._sample(T, x - u * sp * dt, y - v * sp * dt) : T[i];
      }
    }
    for (let y = 1; y < H - 1; y++) {
      for (let x = 1; x < W - 1; x++) {
        const i = y * W + x;
        T[i] = T2[i] + 0.18 * (T2[i - 1] + T2[i + 1] + T2[i - W] + T2[i + W] - 4 * T2[i]);
      }
    }
    for (let x = 0; x < W; x++) { T[x] = T2[x]; T[(H - 1) * W + x] = T2[(H - 1) * W + x]; }
    for (let y = 0; y < H; y++) { T[y * W] = T2[y * W]; T[y * W + W - 1] = T2[y * W + W - 1]; }
    if (heat || cool) {
      const sup = heat ? SUPPLY_HEAT_F : SUPPLY_COOL_F;
      for (const vt of this.vents) {
        for (let oy = -1; oy <= 1; oy++) for (let ox = -1; ox <= 1; ox++) {
          const x = vt.x + ox, y = vt.y + oy;
          if (x < 0 || y < 0 || x >= W || y >= H) continue;
          T[y * W + x] += (sup - T[y * W + x]) * 0.35;
        }
      }
    }
    for (let x = 0; x < W; x++) {
      T[x] += (outdoorF - T[x]) * 0.004;
      T[(H - 1) * W + x] += (outdoorF - T[(H - 1) * W + x]) * 0.004;
    }
    for (let y = 0; y < H; y++) {
      const win = (y > 8 && y < 16) || (y > 23 && y < 31);   // window rows 9-15 and 24-30 on the left wall
      T[y * W] += (outdoorF - T[y * W]) * (win ? 0.02 : 0.005);
      T[y * W + W - 1] += (outdoorF - T[y * W + W - 1]) * 0.003;
    }
    const corr = roomF - this.mean();
    for (let i = 0; i < T.length; i++) T[i] += corr;
  }

  mean() {
    const T = this.T;
    let sum = 0;
    for (let i = 0; i < T.length; i++) sum += T[i];
    return sum / T.length;
  }

  // Fill an RGBA Uint8ClampedArray (w*h*4) from the field.
  toImageData(data) {
    const T = this.T;
    for (let i = 0; i < T.length; i++) {
      const c = heatColor(T[i]);
      const o = i * 4;
      data[o] = c[0]; data[o + 1] = c[1]; data[o + 2] = c[2]; data[o + 3] = c[3] * 255;
    }
    return data;
  }
}
