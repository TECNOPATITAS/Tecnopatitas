/*
  Generador de códigos QR (ISO/IEC 18004) sin dependencias.
  Modo byte (UTF-8), versiones 1 a 10, niveles de corrección L / M / Q / H.
  Basado en el algoritmo estándar: Reed-Solomon sobre GF(256), 8 máscaras y penalización de las 4 reglas.
  Se valida decodificando los resultados con un lector independiente (ver pruebas-web/probar_qr.py).

  API:  TPQR.encode(texto, 'M')       → { version, size, ecc, modules[fila][columna] (1 = oscuro) }
        TPQR.toSvg(qr)               → string SVG (para descargar)
        TPQR.toSvgElement(qr)        → elemento <svg> (sin innerHTML)
        TPQR.toPngBlob(qr, escala)   → Promise<Blob> (PNG)
*/
(() => {
'use strict';

// ---------- GF(256), polinomio 0x11D ----------
const EXP = new Uint8Array(512), LOG = new Uint8Array(256);
(() => { let x = 1; for (let i = 0; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 256) x ^= 0x11d; } for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255]; })();
const mul = (a, b) => (a && b) ? EXP[LOG[a] + LOG[b]] : 0;
function generator(n) {                                       // Π (x − α^i), coeficientes de mayor a menor grado, sin el 1 inicial
  let g = [1];
  for (let i = 0; i < n; i++) {
    const ng = new Array(g.length + 1).fill(0);
    for (let j = 0; j < g.length; j++) { ng[j] ^= g[j]; ng[j + 1] ^= mul(g[j], EXP[i]); }
    g = ng;
  }
  return g.slice(1);
}
function remainder(data, n) {
  const g = generator(n), r = new Array(n).fill(0);
  for (const b of data) {
    const f = b ^ r.shift(); r.push(0);
    if (f) for (let i = 0; i < n; i++) r[i] ^= mul(g[i], f);
  }
  return r;
}

// ---------- Tablas: [ecc por bloque, bloques grupo 1, datos grupo 1, bloques grupo 2, datos grupo 2] por nivel L, M, Q, H ----------
const EC = {
  1: [[7, 1, 19, 0, 0], [10, 1, 16, 0, 0], [13, 1, 13, 0, 0], [17, 1, 9, 0, 0]],
  2: [[10, 1, 34, 0, 0], [16, 1, 28, 0, 0], [22, 1, 22, 0, 0], [28, 1, 16, 0, 0]],
  3: [[15, 1, 55, 0, 0], [26, 1, 44, 0, 0], [18, 2, 17, 0, 0], [22, 2, 13, 0, 0]],
  4: [[20, 1, 80, 0, 0], [18, 2, 32, 0, 0], [26, 2, 24, 0, 0], [16, 4, 9, 0, 0]],
  5: [[26, 1, 108, 0, 0], [24, 2, 43, 0, 0], [18, 2, 15, 2, 16], [22, 2, 11, 2, 12]],
  6: [[18, 2, 68, 0, 0], [16, 4, 27, 0, 0], [24, 4, 19, 0, 0], [28, 4, 15, 0, 0]],
  7: [[20, 2, 78, 0, 0], [18, 4, 31, 0, 0], [18, 2, 14, 4, 15], [26, 4, 13, 1, 14]],
  8: [[24, 2, 97, 0, 0], [22, 2, 38, 2, 39], [22, 4, 18, 2, 19], [26, 4, 14, 2, 15]],
  9: [[30, 2, 116, 0, 0], [22, 3, 36, 2, 37], [20, 4, 16, 4, 17], [24, 4, 12, 4, 13]],
  10: [[18, 2, 68, 2, 69], [26, 4, 43, 1, 44], [24, 6, 19, 2, 20], [28, 6, 15, 2, 16]]
};
const ALIGN = { 1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50] };
const LEVELS = { L: 0, M: 1, Q: 2, H: 3 };
const FORMAT_BITS = [1, 0, 3, 2];                             // L, M, Q, H
const dataCodewords = (v, l) => { const e = EC[v][l]; return e[1] * e[2] + e[3] * e[4]; };

function utf8(str) { return Array.from(new TextEncoder().encode(String(str))); }

// ---------- Flujo de bits y bloques ----------
function buildCodewords(bytes, v, l) {
  const bits = [];
  const put = (val, len) => { for (let i = len - 1; i >= 0; i--) bits.push((val >>> i) & 1); };
  put(0b0100, 4); put(bytes.length, v < 10 ? 8 : 16);
  bytes.forEach(b => put(b, 8));
  const cap = dataCodewords(v, l) * 8;
  put(0, Math.min(4, cap - bits.length));
  while (bits.length % 8) bits.push(0);
  const data = [];
  for (let i = 0; i < bits.length; i += 8) { let b = 0; for (let j = 0; j < 8; j++) b = (b << 1) | bits[i + j]; data.push(b); }
  for (let pad = 0xEC; data.length < cap / 8; pad ^= 0xEC ^ 0x11) data.push(pad);
  const [eccLen, n1, d1, n2, d2] = EC[v][l];
  const blocks = [];
  let k = 0;
  for (let i = 0; i < n1 + n2; i++) { const len = i < n1 ? d1 : d2; blocks.push(data.slice(k, k + len)); k += len; }
  const eccs = blocks.map(b => remainder(b, eccLen));
  const out = [];
  const maxData = Math.max(d1, d2);
  for (let i = 0; i < maxData; i++) blocks.forEach(b => { if (i < b.length) out.push(b[i]); });
  for (let i = 0; i < eccLen; i++) eccs.forEach(e => out.push(e[i]));
  return out;
}

// ---------- Matriz ----------
function makeMatrix(v) {
  const size = 17 + 4 * v;
  const m = Array.from({ length: size }, () => new Uint8Array(size));
  const fn = Array.from({ length: size }, () => new Uint8Array(size));
  const set = (x, y, dark) => { m[y][x] = dark ? 1 : 0; fn[y][x] = 1; };
  for (let i = 0; i < size; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0); }
  const finder = (cx, cy) => {
    for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) {
      const x = cx + dx, y = cy + dy;
      if (x >= 0 && x < size && y >= 0 && y < size) set(x, y, Math.max(Math.abs(dx), Math.abs(dy)) !== 2 && Math.max(Math.abs(dx), Math.abs(dy)) !== 4);
    }
  };
  finder(3, 3); finder(size - 4, 3); finder(3, size - 4);
  const pos = ALIGN[v], last = pos.length - 1;
  pos.forEach((px, i) => pos.forEach((py, j) => {
    if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) return;
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) set(px + dx, py + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
  }));
  return { size, m, fn, set };
}
function drawFormat(mx, l, mask) {
  const data = (FORMAT_BITS[l] << 3) | mask;
  let rem = data;
  for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
  const bits = ((data << 10) | rem) ^ 0x5412;
  const bit = i => ((bits >>> i) & 1) === 1;
  const { size, set } = mx;
  for (let i = 0; i <= 5; i++) set(8, i, bit(i));
  set(8, 7, bit(6)); set(8, 8, bit(7)); set(7, 8, bit(8));
  for (let i = 9; i < 15; i++) set(14 - i, 8, bit(i));
  for (let i = 0; i < 8; i++) set(size - 1 - i, 8, bit(i));
  for (let i = 8; i < 15; i++) set(8, size - 15 + i, bit(i));
  set(8, size - 8, true);                                     // módulo oscuro fijo
}
function drawVersion(mx, v) {
  if (v < 7) return;
  let rem = v;
  for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1F25);
  const bits = (v << 12) | rem;
  for (let i = 0; i < 18; i++) {
    const dark = ((bits >>> i) & 1) === 1, a = mx.size - 11 + (i % 3), b = Math.floor(i / 3);
    mx.set(a, b, dark); mx.set(b, a, dark);
  }
}
function placeData(mx, cw) {
  const { size, m, fn } = mx;
  let i = 0;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vert = 0; vert < size; vert++) for (let j = 0; j < 2; j++) {
      const x = right - j, upward = ((right + 1) & 2) === 0, y = upward ? size - 1 - vert : vert;
      if (!fn[y][x] && i < cw.length * 8) { m[y][x] = (cw[i >>> 3] >>> (7 - (i & 7))) & 1; i++; }
    }
  }
}
const MASKS = [
  (r, c) => (r + c) % 2 === 0,
  (r, c) => r % 2 === 0,
  (r, c) => c % 3 === 0,
  (r, c) => (r + c) % 3 === 0,
  (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
  (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
  (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
  (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0
];
function applyMask(mx, mask) {
  const { size, m, fn } = mx, f = MASKS[mask];
  for (let r = 0; r < size; r++) for (let c = 0; c < size; c++) if (!fn[r][c] && f(r, c)) m[r][c] ^= 1;
}
function penalty(m, size) {
  let p = 0;
  const line = get => {                                       // reglas 1 y 3 sobre una fila o columna
    let run = 1;
    for (let i = 1; i < size; i++) {
      if (get(i) === get(i - 1)) { run++; if (run === 5) p += 3; else if (run > 5) p++; } else run = 1;
    }
    const at = i => (i < 0 || i >= size) ? 0 : get(i);
    for (let i = 0; i + 7 <= size; i++) {
      if (get(i) === 1 && get(i + 1) === 0 && get(i + 2) === 1 && get(i + 3) === 1 && get(i + 4) === 1 && get(i + 5) === 0 && get(i + 6) === 1) {
        const before = !at(i - 1) && !at(i - 2) && !at(i - 3) && !at(i - 4);
        const after = !at(i + 7) && !at(i + 8) && !at(i + 9) && !at(i + 10);
        if (before) p += 40;
        if (after) p += 40;
      }
    }
  };
  for (let i = 0; i < size; i++) { line(j => m[i][j]); line(j => m[j][i]); }
  let dark = 0;
  for (let r = 0; r < size; r++) for (let c = 0; c < size; c++) {
    dark += m[r][c];
    if (r + 1 < size && c + 1 < size && m[r][c] === m[r][c + 1] && m[r][c] === m[r + 1][c] && m[r][c] === m[r + 1][c + 1]) p += 3;
  }
  const total = size * size;
  p += (Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1) * 10;
  return p;
}

function encode(text, level) {
  const l = LEVELS[level || 'M'];
  if (l === undefined) throw new Error('Nivel de corrección no válido.');
  const bytes = utf8(text);
  let v = 0;
  for (let k = 1; k <= 10; k++) {
    if (4 + (k < 10 ? 8 : 16) + 8 * bytes.length <= dataCodewords(k, l) * 8) { v = k; break; }
  }
  if (!v) throw new Error('El texto es demasiado largo para el código QR.');
  const cw = buildCodewords(bytes, v, l);
  let best = null, bestScore = Infinity;
  for (let mask = 0; mask < 8; mask++) {
    const mx = makeMatrix(v);
    drawFormat(mx, l, 0); drawVersion(mx, v);                 // reserva las zonas de formato y versión
    placeData(mx, cw);
    applyMask(mx, mask);
    drawFormat(mx, l, mask);
    const score = penalty(mx.m, mx.size);
    if (score < bestScore) { bestScore = score; best = mx; }
  }
  return { version: v, size: best.size, ecc: level || 'M', modules: best.m };
}

// ---------- Dibujo ----------
function darkPath(qr, border) {                               // un solo <path>: tramos horizontales de módulos oscuros
  const parts = [];
  for (let r = 0; r < qr.size; r++) {
    let c = 0;
    while (c < qr.size) {
      if (!qr.modules[r][c]) { c++; continue; }
      let e = c; while (e < qr.size && qr.modules[r][e]) e++;
      parts.push('M' + (c + border) + ',' + (r + border) + 'h' + (e - c) + 'v1h-' + (e - c) + 'z');
      c = e;
    }
  }
  return parts.join('');
}
function toSvg(qr, opts) {
  const o = Object.assign({ border: 4, dark: '#000000', light: '#ffffff', label: 'Código QR' }, opts);
  const n = qr.size + o.border * 2;
  const safe = s => String(s).replace(/[^#a-zA-Z0-9 áéíóúñÁÉÍÓÚÑ.,:-]/g, '');
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + n + ' ' + n + '" width="' + n * 8 + '" height="' + n * 8 + '" shape-rendering="crispEdges" role="img" aria-label="' + safe(o.label) + '">' +
    '<rect width="' + n + '" height="' + n + '" fill="' + safe(o.light) + '"/><path d="' + darkPath(qr, o.border) + '" fill="' + safe(o.dark) + '"/></svg>';
}
function toSvgElement(qr, opts) {
  const o = Object.assign({ border: 4, dark: '#000000', light: '#ffffff', label: 'Código QR' }, opts);
  const NS = 'http://www.w3.org/2000/svg', n = qr.size + o.border * 2;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 ' + n + ' ' + n);
  svg.setAttribute('shape-rendering', 'crispEdges');
  svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', o.label);
  const bg = document.createElementNS(NS, 'rect');
  bg.setAttribute('width', n); bg.setAttribute('height', n); bg.setAttribute('fill', o.light);
  const path = document.createElementNS(NS, 'path');
  path.setAttribute('d', darkPath(qr, o.border)); path.setAttribute('fill', o.dark);
  svg.append(bg, path);
  return svg;
}
function toPngBlob(qr, scale) {
  const s = scale || 10, border = 4, n = (qr.size + border * 2) * s;
  const cv = document.createElement('canvas'); cv.width = n; cv.height = n;
  const ctx = cv.getContext('2d');
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, n, n);
  ctx.fillStyle = '#000000';
  for (let r = 0; r < qr.size; r++) for (let c = 0; c < qr.size; c++) if (qr.modules[r][c]) ctx.fillRect((c + border) * s, (r + border) * s, s, s);
  return new Promise((res, rej) => cv.toBlob(b => b ? res(b) : rej(new Error('No se pudo crear la imagen.')), 'image/png'));
}

window.TPQR = Object.freeze({ encode, toSvg, toSvgElement, toPngBlob });
})();
