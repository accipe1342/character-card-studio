/**
 * LoreTools.jsx — extra LORE studio panels, kept out of LoreStudio.jsx:
 *   isAlwaysOn / entryTokens   helpers shared with the entry list
 *   BudgetMeter                always-on tokens vs SillyTavern's World Info budget
 *   AdvancedWI                 the rest of SillyTavern's per-entry settings (position, sticky, groups, ...)
 *   SimulatorPanel             paste chat text: which entries would fire, and why
 *   LinksPanel                 which entries mention which (recursion), orphans, loops
 *   TrashPanel                 deleted entries: restore or delete for good
 */
import { useEffect, useState } from "react";
import { simulateLore, getLoreGraph, listLoreTrash, restoreLoreEntry, emptyLoreTrash, deleteLoreEntry } from "../../lib/api";

export const ALWAYS_ON_TITLES = ["Story So Far", "Cast Roster", "Relationships"];
export const isAlwaysOn = (e) => (e.constant === null || e.constant === undefined ? ALWAYS_ON_TITLES.includes(e.title) : !!e.constant);
export const entryTokens = (e) => Math.max(1, Math.ceil((e.content_chars ?? (e.content || "").length) / 4));

const dim = { fontSize: 11, color: "var(--signal-text-dim)" };
const lbl = { fontSize: 10, letterSpacing: "0.08em", color: "var(--signal-text-dim)", marginBottom: 4, display: "block" };
const field = {
  padding: "6px 8px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-input)",
  color: "var(--signal-text)", fontFamily: "inherit", fontSize: 12, boxSizing: "border-box", width: "100%",
};
const sbtn = {
  padding: "6px 12px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-btn)",
  color: "var(--signal-text)", cursor: "pointer", fontFamily: "inherit", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em",
};
const panel = { border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)", padding: 14, marginBottom: 12 };

export function BudgetMeter({ entries, budget = 2048 }) {
  const on = entries.filter(isAlwaysOn);
  const always = on.reduce((n, e) => n + entryTokens(e), 0);
  const all = entries.reduce((n, e) => n + entryTokens(e), 0);
  const pct = Math.min(100, Math.round((always / budget) * 100));
  const color = pct >= 90 ? "#c84a3a" : pct >= 60 ? "#b8860b" : "var(--signal-text)";
  return (
    <div title={`Always-on entries are inserted first and use the World Info budget before any keyword entry. SillyTavern's default budget is ${budget} tokens (estimate: 4 characters per token).`}
      style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, letterSpacing: "0.06em", color: "var(--signal-text-dim)", marginBottom: 3 }}>
        <span>ALWAYS ON {on.length} · ~{always.toLocaleString()} / {budget.toLocaleString()} TOK</span>
        <span>ALL ~{all.toLocaleString()}</span>
      </div>
      <div role="meter" aria-label="Always-on share of the World Info budget" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
        style={{ height: 6, border: "1px solid var(--signal-border)", background: "var(--signal-bg-input)" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color }} />
      </div>
      {pct >= 90 && <div style={{ ...dim, color: "#c84a3a", marginTop: 3 }}>Always-on entries fill the budget: keyword entries will be cut. Shorten them or raise the budget in SillyTavern.</div>}
    </div>
  );
}

const POSITIONS = [
  ["", "Default for this type"], ["0", "Before character (↑Char)"], ["1", "After character (↓Char)"],
  ["2", "Top of Author's Note (↑AN)"], ["3", "Bottom of Author's Note (↓AN)"], ["4", "At depth (@D)"],
  ["5", "Before example messages (↑EM)"], ["6", "After example messages (↓EM)"],
];
const LOGIC = [["0", "AND ANY"], ["3", "AND ALL"], ["2", "NOT ANY"], ["1", "NOT ALL"]];
const listText = (v) => (Array.isArray(v) ? v.join(", ") : "");
const parseList = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
const numOrNull = (v, lo, hi) => (v === "" ? null : Math.max(lo, Math.min(hi, parseInt(v, 10) || 0)));

/** The rest of SillyTavern's per-entry settings. Empty = the studio's default for the entry type. */
export function AdvancedWI({ entry, setEntry, t = {} }) {
  const [open, setOpen] = useState(false);
  const set = (k, v) => setEntry((p) => ({ ...p, [k]: v }));
  // comma lists are edited as text and parsed on blur, so typing a comma doesn't fight the input
  const [secText, setSecText] = useState(listText(entry.secondary_keys));
  const [filterText, setFilterText] = useState(listText(entry.char_filter));
  useEffect(() => { setSecText(listText(entry.secondary_keys)); setFilterText(listText(entry.char_filter)); }, [entry.id]);
  const changed = ["position", "sticky", "constant"].some((k) => entry[k] !== null && entry[k] !== undefined) || !!entry.cooldown || !!entry.delay
    || (entry.probability ?? 100) !== 100 || (entry.secondary_keys || []).length || entry.group_name || entry.vectorized || (entry.char_filter || []).length;
  const constVal = entry.constant === null || entry.constant === undefined ? "" : entry.constant ? "1" : "0";
  return (
    <div style={{ marginBottom: 14 }}>
      <button type="button" className="signal-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        style={{ ...sbtn, width: "100%", textAlign: "left" }}>
        {open ? "▾" : "▸"} {(t.advancedSt || "Advanced SillyTavern settings").toUpperCase()}{changed && !open ? " · customised" : ""}
      </button>
      {open && (
        <div style={{ border: "1px solid var(--signal-border)", borderTop: "none", padding: 12, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 10 }}>
          <label><span style={lbl}>ACTIVATION</span>
            <select style={field} value={constVal} onChange={(e) => set("constant", e.target.value === "" ? null : e.target.value === "1" ? 1 : 0)}>
              <option value="">Default ({ALWAYS_ON_TITLES.includes(entry.title) ? "always on" : "keywords"})</option>
              <option value="1">Always on (constant)</option>
              <option value="0">Keywords only</option>
            </select>
          </label>
          <label><span style={lbl}>POSITION</span>
            <select style={field} value={entry.position ?? ""} onChange={(e) => set("position", e.target.value === "" ? null : parseInt(e.target.value, 10))}>
              {POSITIONS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
            </select>
          </label>
          {entry.position === 4 && (
            <label title="Who the entry is sent as when inserted at depth"><span style={lbl}>ROLE (AT DEPTH)</span>
              <select style={field} value={entry.role ?? 0} onChange={(e) => set("role", parseInt(e.target.value, 10))}>
                <option value={0}>System</option><option value={1}>User</option><option value={2}>Assistant</option>
              </select>
            </label>
          )}
          <label title="Messages the entry stays active after it fires. Default: 2 for characters, 0 for the rest"><span style={lbl}>STICKY</span>
            <input style={field} type="number" min={0} max={1000} placeholder={entry.entry_type === "character" ? "default 2" : "default 0"}
              value={entry.sticky ?? ""} onChange={(e) => set("sticky", numOrNull(e.target.value, 0, 1000))} />
          </label>
          <label title="Messages it can't fire again after it fires"><span style={lbl}>COOLDOWN</span>
            <input style={field} type="number" min={0} max={1000} value={entry.cooldown ?? 0} onChange={(e) => set("cooldown", numOrNull(e.target.value, 0, 1000) ?? 0)} />
          </label>
          <label title="Only fires once the chat has at least this many messages"><span style={lbl}>DELAY</span>
            <input style={field} type="number" min={0} max={1000} value={entry.delay ?? 0} onChange={(e) => set("delay", numOrNull(e.target.value, 0, 1000) ?? 0)} />
          </label>
          <label title="Chance the entry is inserted when it is triggered"><span style={lbl}>PROBABILITY %</span>
            <input style={field} type="number" min={0} max={100} value={entry.probability ?? 100} onChange={(e) => set("probability", numOrNull(e.target.value, 0, 100) ?? 100)} />
          </label>
          <label style={{ gridColumn: "1 / -1" }} title="Optional filter: after a primary key matches, these decide whether the entry fires"><span style={lbl}>SECONDARY KEYS (COMMA-SEPARATED)</span>
            <div style={{ display: "flex", gap: 6 }}>
              <select style={{ ...field, width: "auto" }} value={entry.selective_logic ?? 0} onChange={(e) => set("selective_logic", parseInt(e.target.value, 10))} aria-label="Secondary key logic">
                {LOGIC.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
              <input style={field} value={secText} placeholder="e.g. night, festival" onChange={(e) => setSecText(e.target.value)}
                onBlur={() => set("secondary_keys", parseList(secText))} />
            </div>
          </label>
          <label title="Entries sharing a group: only one of them is inserted"><span style={lbl}>INCLUSION GROUP</span>
            <input style={field} value={entry.group_name || ""} placeholder="none" onChange={(e) => set("group_name", e.target.value)} />
          </label>
          <label title="Higher weight = more likely to win the group"><span style={lbl}>GROUP WEIGHT</span>
            <input style={field} type="number" min={1} max={1000} value={entry.group_weight ?? 100} onChange={(e) => set("group_weight", numOrNull(e.target.value, 1, 1000) ?? 100)} />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, alignSelf: "end" }} title="Prioritize: the highest Order in the group wins instead of a weighted draw">
            <input type="checkbox" checked={!!entry.group_prioritize} onChange={(e) => set("group_prioritize", e.target.checked ? 1 : 0)} /> Prioritize in group
          </label>
          <label style={{ gridColumn: "1 / -1" }} title="Only active for these character names (empty = everyone)"><span style={lbl}>ONLY FOR CHARACTERS (COMMA-SEPARATED)</span>
            <input style={field} value={filterText} placeholder="everyone" onChange={(e) => setFilterText(e.target.value)}
              onBlur={() => set("char_filter", parseList(filterText))} />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }} title="Can also fire by meaning (needs SillyTavern's Vector Storage extension)">
            <input type="checkbox" checked={!!entry.vectorized} onChange={(e) => set("vectorized", e.target.checked ? 1 : 0)} /> Vectorized
          </label>
          <button type="button" className="signal-btn" style={{ ...sbtn, alignSelf: "end" }}
            onClick={() => { setEntry((p) => ({ ...p, constant: null, position: null, role: 0, sticky: null, cooldown: 0, delay: 0, probability: 100,
              secondary_keys: [], selective_logic: 0, group_name: "", group_weight: 100, group_prioritize: 0, char_filter: [], vectorized: 0 })); setSecText(""); setFilterText(""); }}>
            RESET TO DEFAULTS
          </button>
        </div>
      )}
    </div>
  );
}

const POS_SHORT = { 0: "↑Char", 1: "↓Char", 2: "↑AN", 3: "↓AN", 4: "@D", 5: "↑EM", 6: "↓EM", 7: "Outlet" };

export function SimulatorPanel({ project, onOpen, onClose, t = {} }) {
  const [text, setText] = useState("");
  const [budget, setBudget] = useState(2048);
  const [whole, setWhole] = useState(false);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run() {
    setBusy(true); setError("");
    try { setRes(await simulateLore(project?.id, text, budget, whole)); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const Row = ({ r, dropped }) => (
    <div style={{ display: "flex", gap: 8, padding: "6px 8px", borderBottom: "1px solid var(--signal-border)", fontSize: 12, alignItems: "baseline", flexWrap: "wrap", opacity: dropped ? 0.7 : 1 }}>
      <button className="signal-btn" onClick={() => r.lore_id && onOpen(r.lore_id)} style={{ background: "none", border: "none", padding: 0, color: "inherit", cursor: "pointer", fontWeight: 700, fontFamily: "inherit", fontSize: 12, textDecoration: dropped ? "line-through" : "none" }}>{r.title}</button>
      <span style={dim}>{r.entry_type} · order {r.order} · {POS_SHORT[r.position] || r.position} · ~{r.tokens} tok</span>
      <span style={{ flexBasis: "100%", ...dim, color: dropped ? "#c84a3a" : "var(--signal-text-dim)" }}>{dropped ? `✕ ${r.dropped}` : r.why}{r.notes?.length ? ` · ${r.notes.join(" · ")}` : ""}</span>
    </div>
  );
  return (
    <section style={panel} aria-label="Activation test">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 13, letterSpacing: "0.08em" }}>:: {(t.testActivation || "Test activation").toUpperCase()}</strong>
        <span style={dim}>{project ? project.project_name : "All entries"}</span>
        <button className="signal-btn" onClick={onClose} aria-label="Close activation test" style={{ ...sbtn, marginLeft: "auto" }}>✕</button>
      </div>
      <div style={{ ...dim, marginBottom: 8 }}>Paste the last few chat messages. Shows which entries SillyTavern would insert, why, and which the token budget would cut. Probability, sticky and cooldown depend on the live chat and are listed as notes.</div>
      <textarea style={{ ...field, height: 110, resize: "vertical", fontSize: 13 }} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="{{user}}: Have you seen Rikku since the temple?" aria-label="Chat text to test" />
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
        <label style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "center" }}>Budget
          <input type="number" min={100} max={200000} step={256} value={budget} onChange={(e) => setBudget(parseInt(e.target.value, 10) || 2048)} style={{ ...field, width: 90 }} />
        </label>
        <label style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "center" }} title="SillyTavern's 'Match whole words' setting">
          <input type="checkbox" checked={whole} onChange={(e) => setWhole(e.target.checked)} /> Match whole words
        </label>
        <button className="signal-btn" style={{ ...sbtn, marginLeft: "auto", background: "var(--signal-btn-active-bg)", color: "var(--signal-btn-active-text)" }}
          disabled={busy || !text.trim()} onClick={run}>{busy ? "TESTING…" : "▶ RUN TEST"}</button>
      </div>
      {error && <div style={{ color: "#c84a3a", fontSize: 12, marginTop: 8 }}>⊗ {error}</div>}
      {res && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
            {res.activated.length} inserted · ~{res.tokens.toLocaleString()} / {res.budget.toLocaleString()} tokens · {res.dropped.length} cut · {res.inactive} not triggered
          </div>
          <div style={{ border: "1px solid var(--signal-border)", maxHeight: 340, overflowY: "auto" }}>
            {res.activated.map((r) => <Row key={`a${r.lore_id}`} r={r} />)}
            {res.dropped.map((r) => <Row key={`d${r.lore_id}`} r={r} dropped />)}
            {!res.activated.length && !res.dropped.length && <div style={{ ...dim, padding: 8 }}>Nothing would fire for this text.</div>}
          </div>
          {res.blocked.length > 0 && <div style={{ ...dim, marginTop: 6 }}>Held back by secondary keys: {res.blocked.map((b) => b.title).join(", ")}</div>}
        </div>
      )}
    </section>
  );
}

export function LinksPanel({ project, onOpen, onClose, t = {} }) {
  const [g, setG] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { setG(null); getLoreGraph(project.id).then(setG).catch((e) => setError(e.message)); }, [project.id]);
  const title = (id) => g?.nodes.find((n) => n.lore_id === id)?.title || "?";
  const out = {};
  (g?.edges || []).forEach((e) => { (out[e.from] = out[e.from] || []).push(e); });
  const Link = ({ id }) => (
    <button className="signal-btn" onClick={() => onOpen(id)} style={{ background: "none", border: "none", padding: 0, color: "inherit", cursor: "pointer", fontFamily: "inherit", fontSize: 12, textDecoration: "underline" }}>{title(id)}</button>
  );
  return (
    <section style={panel} aria-label="Entry links">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <strong style={{ fontSize: 13, letterSpacing: "0.08em" }}>:: {(t.links || "Links").toUpperCase()}</strong>
        <span style={dim}>An entry that mentions another entry's key pulls it in by recursion.</span>
        <button className="signal-btn" onClick={onClose} aria-label="Close links" style={{ ...sbtn, marginLeft: "auto" }}>✕</button>
      </div>
      {error && <div style={{ color: "#c84a3a", fontSize: 12 }}>⊗ {error}</div>}
      {!g && !error && <div style={dim}>Loading…</div>}
      {g && (<>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12, marginBottom: 8 }}>
          <span>{g.nodes.length} entries</span><span>{g.edges.length} links</span>
          <span title="Never mentioned by another entry and mention no other entry">{g.orphans.length} unlinked</span>
          <span title="Not always on and no keys: never fires" style={{ color: g.no_keys.length ? "#c84a3a" : undefined }}>{g.no_keys.length} without keys</span>
          <span title="Two entries that mention each other">{g.loops.length} mutual pairs</span>
        </div>
        {g.no_keys.length > 0 && <div style={{ ...dim, color: "#c84a3a", marginBottom: 6 }}>Never fire (no keys): {g.no_keys.join(", ")}</div>}
        {g.loops.length > 0 && <div style={{ ...dim, marginBottom: 6 }}>Mention each other: {g.loops.map((l) => l.join(" ⇄ ")).join(" · ")}</div>}
        {g.orphans.length > 0 && <div style={{ ...dim, marginBottom: 6 }}>Unlinked (only their own keys bring them in): {g.orphans.join(", ")}</div>}
        <div style={{ border: "1px solid var(--signal-border)", maxHeight: 300, overflowY: "auto" }}>
          {g.nodes.filter((n) => out[n.lore_id]).map((n) => (
            <div key={n.lore_id} style={{ padding: "6px 8px", borderBottom: "1px solid var(--signal-border)", fontSize: 12 }}>
              <Link id={n.lore_id} /> <span style={dim}>→</span>{" "}
              {out[n.lore_id].map((e, i) => (
                <span key={e.to}>{i > 0 && ", "}<Link id={e.to} />{!e.live && <span style={dim} title="Recursion is switched off for one side"> (off)</span>}</span>
              ))}
            </div>
          ))}
          {!g.edges.length && <div style={{ ...dim, padding: 8 }}>No entry mentions another entry's keys.</div>}
        </div>
      </>)}
    </section>
  );
}

export function TrashPanel({ project, onChanged, onClose, refreshKey, t = {} }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [confirmEmpty, setConfirmEmpty] = useState(false);
  async function load() {
    try { setItems((await listLoreTrash(project?.id)).entries || []); } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [project?.id, refreshKey]);
  async function restore(id) {
    try { await restoreLoreEntry(id); await load(); onChanged && onChanged(); } catch (e) { setError(e.message); }
  }
  async function purge(id) {
    try { await deleteLoreEntry(id, true); await load(); } catch (e) { setError(e.message); }
  }
  async function empty() {
    if (!confirmEmpty) { setConfirmEmpty(true); return; }
    setConfirmEmpty(false);
    try { await emptyLoreTrash(project?.id); await load(); } catch (e) { setError(e.message); }
  }
  return (
    <section style={panel} aria-label="Trash">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 13, letterSpacing: "0.08em" }}>:: {(t.trash || "Trash").toUpperCase()}</strong>
        <span style={dim}>{project ? project.project_name : "All projects"} · deleted entries stay here until you empty it</span>
        {items?.length > 0 && <button className="signal-btn" onClick={empty} style={{ ...sbtn, marginLeft: "auto", color: "#c84a3a", borderColor: confirmEmpty ? "#c84a3a" : undefined }}>
          {confirmEmpty ? "CLICK AGAIN TO EMPTY" : "EMPTY TRASH"}</button>}
        <button className="signal-btn" onClick={onClose} aria-label="Close trash" style={{ ...sbtn, marginLeft: items?.length ? 0 : "auto" }}>✕</button>
      </div>
      {error && <div style={{ color: "#c84a3a", fontSize: 12 }}>⊗ {error}</div>}
      {items && !items.length && <div style={dim}>The trash is empty.</div>}
      <div style={{ maxHeight: 260, overflowY: "auto" }}>
        {(items || []).map((e) => (
          <div key={e.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "5px 8px", borderBottom: "1px solid var(--signal-border)", fontSize: 12 }}>
            <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.title || "Untitled"} <span style={dim}>· {e.entry_type}</span></span>
            <button className="signal-btn" style={sbtn} onClick={() => restore(e.id)}>RESTORE</button>
            <button className="signal-btn" style={{ ...sbtn, color: "#c84a3a" }} onClick={() => purge(e.id)} aria-label={`Delete ${e.title} for good`}>✕</button>
          </div>
        ))}
      </div>
    </section>
  );
}
