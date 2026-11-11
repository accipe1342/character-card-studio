/**
 * RelationshipMap.jsx — who is linked to whom in a TEXT project, drawn as an SVG.
 *
 * Layout is a small Fruchterman–Reingold force simulation run once (no library): nodes push each other apart,
 * links pull their ends together, a weak pull keeps everything near the middle. Deterministic, so the same project
 * gives the same picture. Drag a node to move it; hover to highlight its links; click to see its relations.
 *
 * Squares are characters, diamonds factions; size grows with the number of links; filled = main characters.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { btn, btnTool, headingStyle, hint, panelStyle } from "./textUi";

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

const size = (nd) => 7 + Math.min(10, Math.sqrt(nd.degree || 0) * 3);

/** Copy of the SVG with the theme's CSS variables resolved, so the downloaded file looks the same anywhere. */
function svgForDownload(svg) {
  const css = getComputedStyle(document.documentElement);
  let txt = new XMLSerializer().serializeToString(svg);
  txt = txt.replace(/var\((--[\w-]+)\)/g, (_, v) => css.getPropertyValue(v).trim() || "#333");
  return `<?xml version="1.0" encoding="UTF-8"?>\n${txt}`;
}

export default function RelationshipMap({ graph, title, onClose, onOpen }) {
  const [showLonely, setShowLonely] = useState(false);
  const [seed, setSeed] = useState(0);
  const [hover, setHover] = useState(null);
  const [sel, setSel] = useState(null);
  const svgRef = useRef(null);
  const drag = useRef(null);
  const nodes = useMemo(() => (graph?.nodes || []).filter((n) => showLonely || n.degree > 0), [graph, showLonely]);
  const edges = graph?.edges || [];
  const [pos, setPos] = useState({});
  useEffect(() => {
    // re-layout: a different starting rotation each time RE-LAYOUT is pressed (seed), same picture otherwise
    const rot = [...nodes.slice(seed % Math.max(1, nodes.length)), ...nodes.slice(0, seed % Math.max(1, nodes.length))];
    setPos(layoutGraph(rot, edges));
  }, [nodes, edges, seed]);
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const shown = edges.filter((e) => pos[e.a] && pos[e.b]);
  const focus = hover ?? sel;
  const near = useMemo(() => {
    if (focus == null) return null;
    const s = new Set([focus]);
    shown.forEach((e) => { if (e.a === focus) s.add(e.b); if (e.b === focus) s.add(e.a); });
    return s;
  }, [focus, shown]);
  const labelsAlways = shown.length <= 24;

  function toSvg(evt) {
    const pt = svgRef.current.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    return pt.matrixTransform(svgRef.current.getScreenCTM().inverse());
  }
  function down(evt, id) {
    evt.stopPropagation();
    evt.currentTarget.setPointerCapture?.(evt.pointerId);
    drag.current = { id, moved: false };
  }
  function move(evt) {
    if (!drag.current) return;
    const p = toSvg(evt);
    drag.current.moved = true;
    setPos((ps) => ({ ...ps, [drag.current.id]: { x: Math.max(10, Math.min(W - 10, p.x)), y: Math.max(10, Math.min(H - 10, p.y)) } }));
  }
  function up(id) {
    const d = drag.current;
    drag.current = null;
    if (d && !d.moved) setSel((s) => (s === id ? null : id));
  }
  function download() {
    const blob = new Blob([svgForDownload(svgRef.current)], { type: "image/svg+xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(title || "relationships").replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "-") || "relationships"}-map.svg`;
    a.click(); URL.revokeObjectURL(a.href);
  }
  const selNode = sel != null ? byId[sel] : null;
  const selEdges = selNode ? shown.filter((e) => e.a === sel || e.b === sel) : [];
  const lonely = (graph?.nodes || []).filter((n) => !n.degree).length;

  return createPortal(
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 300, display: "flex",
      alignItems: "flex-start", justifyContent: "center", padding: "30px 16px", overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()} className="signal-panel" role="dialog" aria-label="Relationship map"
        style={{ ...panelStyle, width: "min(1180px, 100%)", padding: 18, boxShadow: "0 8px 32px rgba(0,0,0,0.3)" }}>
        <h2 className="signal-heading" style={headingStyle}>RELATIONSHIPS · {title}</h2>
        <div style={{ ...hint, marginTop: 0 }}>
          {nodes.length} {nodes.length === 1 ? "entry" : "entries"}, {shown.length} link(s), from the Relations of kept characters and factions
          {graph?.cutoff && graph?.upto >= 0 ? ", as of the starting point" : ""}. Drag to rearrange, click for details.
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-start", marginTop: 10 }}>
          <div style={{ flex: "1 1 640px", minWidth: 0, border: "1px solid var(--signal-border)", background: "var(--signal-bg-field)" }}>
            {!nodes.length ? (
              <div style={{ ...hint, padding: 40, textAlign: "center" }}>
                No links yet. Relations come from extraction, or add them on a character's EDIT tab (one per line: Name — relation).
              </div>
            ) : (
              <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`Relationship map of ${title}`}
                xmlns="http://www.w3.org/2000/svg" style={{ display: "block", touchAction: "none", fontFamily: "inherit" }}
                onPointerMove={move} onPointerLeave={() => setHover(null)} onClick={() => setSel(null)}>
                <rect width={W} height={H} fill="var(--signal-bg-field)" />
                <defs>
                  <pattern id="rm-grid" width="40" height="40" patternUnits="userSpaceOnUse">
                    <path d="M 40 0 L 0 0 0 40" fill="none" stroke="var(--signal-border)" strokeOpacity="0.12" strokeWidth="1" />
                  </pattern>
                </defs>
                <rect width={W} height={H} fill="url(#rm-grid)" />
                {shown.map((e) => {
                  const p = pos[e.a], q = pos[e.b];
                  const on = !near || (near.has(e.a) && near.has(e.b));
                  const label = e.a_to_b && e.b_to_a && e.a_to_b.toLowerCase() !== e.b_to_a.toLowerCase()
                    ? `${e.a_to_b} / ${e.b_to_a}` : (e.a_to_b || e.b_to_a);
                  const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2;
                  const roomy = Math.hypot(q.x - p.x, q.y - p.y) > 90;     // short links: label only in the side panel
                  return (
                    <g key={`${e.a}-${e.b}`} opacity={on ? 1 : 0.12}>
                      <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke="var(--signal-text)" strokeOpacity="0.55" strokeWidth={near && on ? 1.6 : 1} />
                      {label && roomy && (labelsAlways || (near && on)) && (
                        <text x={mx} y={my - 4} textAnchor="middle" fontSize="11" fill="var(--signal-text-dim)"
                          stroke="var(--signal-bg-field)" strokeWidth="3" paintOrder="stroke">{label.length > 34 ? label.slice(0, 33) + "…" : label}</text>
                      )}
                    </g>
                  );
                })}
                {nodes.map((nd) => {
                  const p = pos[nd.id];
                  if (!p) return null;
                  const s = size(nd), on = !near || near.has(nd.id), main = nd.tier === "main";
                  const fill = main ? "var(--signal-text)" : "var(--signal-bg-panel)";
                  return (
                    <g key={nd.id} transform={`translate(${p.x},${p.y})`} opacity={on ? 1 : 0.2} style={{ cursor: "grab" }}
                      onPointerDown={(e) => down(e, nd.id)} onPointerUp={() => up(nd.id)} onClick={(e) => e.stopPropagation()}
                      onPointerEnter={() => !drag.current && setHover(nd.id)} onPointerLeave={() => setHover(null)}
                      role="button" aria-label={nd.name} data-node={nd.name}>
                      {sel === nd.id && <rect x={-s - 5} y={-s - 5} width={2 * s + 10} height={2 * s + 10} fill="none" stroke="var(--signal-text)" strokeDasharray="3 3" />}
                      {nd.type === "faction"
                        ? <rect x={-s} y={-s} width={2 * s} height={2 * s} transform="rotate(45)" fill={fill} stroke="var(--signal-text)" strokeWidth="1.4" />
                        : <rect x={-s} y={-s} width={2 * s} height={2 * s} fill={fill} stroke="var(--signal-text)" strokeWidth="1.4" />}
                      <text y={s + 15} textAnchor="middle" fontSize="12.5" fontWeight={main ? 700 : 500} letterSpacing="0.04em"
                        fill="var(--signal-text)" stroke="var(--signal-bg-field)" strokeWidth="3.5" paintOrder="stroke">{nd.name}</text>
                    </g>
                  );
                })}
              </svg>
            )}
          </div>
          <div style={{ flex: "0 1 260px", minWidth: 220, fontSize: 12.5 }}>
            {selNode ? (<>
              <div style={{ fontWeight: 700, fontSize: 14, letterSpacing: "0.06em" }}>{selNode.name}</div>
              <div style={hint}>{selNode.type}{selNode.tier ? ` · ${selNode.tier}` : ""} · {selEdges.length} link(s)</div>
              <div style={{ marginTop: 8 }}>
                {selEdges.map((e) => {
                  const other = byId[e.a === sel ? e.b : e.a];
                  const mine = e.a === sel ? e.a_to_b : e.b_to_a, theirs = e.a === sel ? e.b_to_a : e.a_to_b;
                  return (
                    <div key={`${e.a}-${e.b}`} style={{ borderTop: "1px solid var(--signal-border)", padding: "6px 0" }}>
                      <button className="signal-btn" onClick={() => setSel(other.id)} style={{ background: "none", border: "none", padding: 0, fontWeight: 700, cursor: "pointer", color: "inherit", fontFamily: "inherit", textDecoration: "underline" }}>{other.name}</button>
                      {mine && <div>{selNode.name} → {mine}</div>}
                      {theirs && <div style={{ opacity: 0.75 }}>{other.name} → {theirs}</div>}
                    </div>
                  );
                })}
              </div>
              {onOpen && <button className="signal-btn" style={{ ...btn, width: "100%", marginTop: 8 }} onClick={() => onOpen(selNode.id)}>OPEN IN REVIEW</button>}
            </>) : (
              <div style={hint}>
                ■ character · ◆ faction<br />filled = main character<br />bigger = more links<br /><br />
                Click a name to see both sides of each relation.
              </div>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end", marginTop: 12, flexWrap: "wrap" }}>
          {lonely > 0 && (
            <label style={{ fontSize: 12, display: "flex", gap: 5, alignItems: "center", marginRight: "auto" }}>
              <input type="checkbox" checked={showLonely} onChange={(e) => setShowLonely(e.target.checked)} /> show {lonely} without links
            </label>
          )}
          <button className="signal-btn" style={btnTool} onClick={() => setSeed((s) => s + 1)}>RE-LAYOUT</button>
          <button className="signal-btn" style={btnTool} disabled={!nodes.length} onClick={download}>↓ SVG</button>
          <button className="signal-btn" style={btn} onClick={onClose}>CLOSE</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
