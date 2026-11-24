#!/usr/bin/env node
// Usage: node tests/visual/tools/regions.mjs <diff.png> [--gap N] [--limit N]
// Prints clusters of differing pixels in a pixelmatch diff image as bounding
// boxes, largest first: x,y,w,h,count. Differing pixels are pixelmatch's
// diffColor (pure red, 255,0,0); anti-aliasing (yellow) and unchanged (grey)
// pixels are ignored. Pixels closer than --gap px (default 8) join one cluster.
import fs from 'node:fs';
import { PNG } from 'pngjs';

const args = process.argv.slice(2);
const opt = (name, dflt) => {
  const i = args.indexOf(name);
  if (i === -1) return dflt;
  const v = Number(args.splice(i, 2)[1]);
  if (!Number.isFinite(v) || v < 1) throw new Error(`${name} needs a positive number`);
  return v;
};
const gap = opt('--gap', 8);
const limit = opt('--limit', Infinity);
const file = args[0];
if (!file) {
  console.error('usage: regions.mjs <diff.png> [--gap N] [--limit N]');
  process.exit(2);
}

const png = PNG.sync.read(fs.readFileSync(file));
const { width, height, data } = png;

// Bin differing pixels into gap x gap cells, then join neighbouring cells.
const cols = Math.ceil(width / gap);
const rows = Math.ceil(height / gap);
const cells = new Map(); // cell index -> { x0, y0, x1, y1, count }
let total = 0;
for (let y = 0; y < height; y++) {
  for (let x = 0; x < width; x++) {
    const i = (y * width + x) * 4;
    if (data[i] === 255 && data[i + 1] === 0 && data[i + 2] === 0) {
      total++;
      const c = Math.floor(y / gap) * cols + Math.floor(x / gap);
      const cell = cells.get(c);
      if (cell) {
        cell.x0 = Math.min(cell.x0, x); cell.y0 = Math.min(cell.y0, y);
        cell.x1 = Math.max(cell.x1, x); cell.y1 = Math.max(cell.y1, y);
        cell.count++;
      } else cells.set(c, { x0: x, y0: y, x1: x, y1: y, count: 1 });
    }
  }
}

const parent = new Map([...cells.keys()].map((k) => [k, k]));
const find = (k) => { while (parent.get(k) !== k) { parent.set(k, parent.get(parent.get(k))); k = parent.get(k); } return k; };
for (const k of cells.keys()) {
  const cx = k % cols, cy = Math.floor(k / cols);
  for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
    const nx = cx + dx, ny = cy + dy;
    if ((dx || dy) && nx >= 0 && ny >= 0 && nx < cols && ny < rows && cells.has(ny * cols + nx)) {
      const a = find(k), b = find(ny * cols + nx);
      if (a !== b) parent.set(a, b);
    }
  }
}

const clusters = new Map();
for (const [k, c] of cells) {
  const r = find(k);
  const acc = clusters.get(r);
  if (acc) {
    acc.x0 = Math.min(acc.x0, c.x0); acc.y0 = Math.min(acc.y0, c.y0);
    acc.x1 = Math.max(acc.x1, c.x1); acc.y1 = Math.max(acc.y1, c.y1);
    acc.count += c.count;
  } else clusters.set(r, { ...c });
}

const sorted = [...clusters.values()].sort((a, b) => b.count - a.count || a.y0 - b.y0 || a.x0 - b.x0);
console.log(`# ${file}: ${width}x${height}, ${total} differing px (${((total / (width * height)) * 100).toFixed(2)}%), ${sorted.length} clusters (gap ${gap})`);
console.log('x,y,w,h,count');
for (const c of sorted.slice(0, limit)) {
  console.log(`${c.x0},${c.y0},${c.x1 - c.x0 + 1},${c.y1 - c.y0 + 1},${c.count}`);
}
