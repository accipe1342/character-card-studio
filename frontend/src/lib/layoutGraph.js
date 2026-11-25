/** Force-directed layout for the TEXT studio's relationship map. */

const W = 1000, H = 680;

export function layoutGraph(nodes, edges, { width = W, height = H, iterations = 350 } = {}) {
  const n = nodes.length;
  if (!n) return {};
  const idx = new Map(nodes.map((nd, i) => [nd.id, i]));
  // start on a spiral, most-linked first, so hubs settle in the middle
  const order = [...nodes.keys()].sort((a, b) => (nodes[b].degree || 0) - (nodes[a].degree || 0));
  const x = new Float64Array(n), y = new Float64Array(n);
  order.forEach((i, k) => {
    const r = 18 * Math.sqrt(k + 1), t = k * 2.399963;          // golden angle
    x[i] = width / 2 + r * Math.cos(t); y[i] = height / 2 + r * Math.sin(t);
  });
  const area = width * height, k = Math.sqrt(area / n) * 0.9;
  const E = edges.map((e) => [idx.get(e.a), idx.get(e.b)]).filter(([a, b]) => a != null && b != null);
  let temp = width / 8;
  const dx = new Float64Array(n), dy = new Float64Array(n);
  for (let it = 0; it < iterations; it++) {
    dx.fill(0); dy.fill(0);
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      let ux = x[i] - x[j], uy = y[i] - y[j];
      let d2 = ux * ux + uy * uy;
      if (d2 < 0.01) { ux = (i - j) * 0.1; uy = 0.1; d2 = ux * ux + uy * uy; }
      const f = (k * k) / d2;                                  // repulsion k²/d, applied along the unit vector
      dx[i] += ux * f; dy[i] += uy * f; dx[j] -= ux * f; dy[j] -= uy * f;
    }
    for (const [a, b] of E) {
      const ux = x[a] - x[b], uy = y[a] - y[b];
      const d = Math.sqrt(ux * ux + uy * uy) || 0.01;
      const f = d / k;                                         // attraction d²/k, along the unit vector
      dx[a] -= ux * f; dy[a] -= uy * f; dx[b] += ux * f; dy[b] += uy * f;
    }
    for (let i = 0; i < n; i++) {
      dx[i] += (width / 2 - x[i]) * 0.006 * k / 10;            // gentle gravity: unlinked nodes don't fly off
      dy[i] += (height / 2 - y[i]) * 0.006 * k / 10;
      const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1;
      const s = Math.min(d, temp) / d;
      x[i] += dx[i] * s; y[i] += dy[i] * s;
    }
    temp = Math.max(1.5, temp * 0.985);
  }
  // fit into the box with a margin for labels
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (let i = 0; i < n; i++) { minX = Math.min(minX, x[i]); maxX = Math.max(maxX, x[i]); minY = Math.min(minY, y[i]); maxY = Math.max(maxY, y[i]); }
  const m = 60, sx = (width - 2 * m) / Math.max(1, maxX - minX), sy = (height - 2 * m) / Math.max(1, maxY - minY);
  // fill the box: each axis scales on its own, but never more than 1.8x the other (shapes stay readable)
  let fx = Math.min(sx, 4), fy = Math.min(sy, 4);
  if (fx > fy * 1.8) fx = fy * 1.8;
  if (fy > fx * 1.8) fy = fx * 1.8;
  const ox = (width - (maxX - minX) * fx) / 2, oy = (height - (maxY - minY) * fy) / 2;
  const pos = {};
  nodes.forEach((nd, i) => { pos[nd.id] = { x: ox + (x[i] - minX) * fx, y: oy + (y[i] - minY) * fy }; });
  return pos;
}
