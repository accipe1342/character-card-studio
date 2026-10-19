/**
 * AdminPanels.jsx — Config page sections: model presets per task, database backups, model usage.
 * Kept out of ConfigPage.jsx so that file stays about prompts and keys.
 */
import { useEffect, useRef, useState } from "react";
import { getPresets, savePresets, listBackups, makeBackup, restoreBackup, getUsage, getBundleContents, exportBundle, importBundle } from "../lib/api";

const TASKS = [
  ["extract", "TEXT extraction", "Many calls: use a fast, non-thinking model"],
  ["critic", "Critic", "A stronger model gives sharper critique"],
  ["card", "Character cards", "Generate Card and field regeneration"],
  ["lore", "Lore studio", "Wiki pages to lore entries"],
];

const panel = { border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)", padding: 20, textAlign: "left" };
const input = {
  padding: "8px 10px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-input)",
  color: "var(--signal-text)", fontFamily: "inherit", fontSize: 13, boxSizing: "border-box", width: "100%",
};
const btn = {
  padding: "8px 14px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-btn)",
  color: "var(--signal-text)", cursor: "pointer", fontFamily: "inherit", fontSize: 12, fontWeight: 700, letterSpacing: "0.06em",
};
const hint = { fontSize: 11, color: "var(--signal-text-dim)" };

function BundlePanel({ showToast, setError, onImported, t = {} }) {
  const [contents, setContents] = useState(null);
  const [sel, setSel] = useState({ text_ids: [], lore_ids: [], card_ids: [] });
  const [linked, setLinked] = useState(true);
  const [busy, setBusy] = useState("");
  const fileRef = useRef(null);
  const load = () => getBundleContents().then(setContents).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  const toggle = (k, id) => setSel((s) => ({ ...s, [k]: s[k].includes(id) ? s[k].filter((x) => x !== id) : [...s[k], id] }));
  const count = sel.text_ids.length + sel.lore_ids.length + sel.card_ids.length;
  async function onExport() {
    setBusy("export"); setError("");
    try {
      const blob = await exportBundle({ ...sel, include_linked: linked });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `card-studio-bundle-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }
  async function onImport(file) {
    if (!file) return;
    setBusy("import"); setError("");
    try {
      const r = await importBundle(file);
      const a = r.added || {};
      showToast && showToast(`Imported ${a.text_projects || 0} text, ${a.lore_crawls || 0} lore project(s), ${a.cards || 0} card(s)`);
      await load(); onImported && onImported();
    } catch (e) { setError(e.message); }
    finally { setBusy(""); if (fileRef.current) fileRef.current.value = ""; }
  }
  const List = ({ title, items, k, render }) => (
    <div style={{ flex: "1 1 220px", minWidth: 0 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", marginBottom: 4 }}>{title} ({items.length})</div>
      <div style={{ maxHeight: 180, overflowY: "auto", border: "1px solid var(--signal-border)" }}>
        {!items.length && <div style={{ ...hint, padding: 6 }}>None</div>}
        {items.map((it) => (
          <label key={it.id} style={{ display: "flex", gap: 6, alignItems: "center", padding: "4px 8px", fontSize: 12, borderBottom: "1px solid var(--signal-border)", cursor: "pointer" }}>
            <input type="checkbox" checked={sel[k].includes(it.id)} onChange={() => toggle(k, it.id)} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{render(it)}</span>
          </label>
        ))}
      </div>
    </div>
  );
  return (
    <section className="signal-panel signal-screen-panel" style={panel}>
      <h2 className="signal-heading" style={{ margin: "0 0 6px", fontSize: 15 }}>{t.projectBundles || "Project bundles"}</h2>
      <div style={{ ...hint, marginBottom: 10 }}>
        One .zip with the chosen TEXT projects, LORE projects and cards, to move them to another computer or keep them safe.
        It also holds ready-to-use SillyTavern lorebook and card JSON files. Importing adds everything as new; nothing is overwritten.
      </div>
      {!contents && <div style={hint}>Loading…</div>}
      {contents && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <List title="TEXT" k="text_ids" items={contents.text_projects} render={(p) => p.name + (p.lore_project_id ? " · in LORE" : "")} />
          <List title="LORE" k="lore_ids" items={contents.lore_projects} render={(p) => `${p.name} · ${p.entries}`} />
          <List title="CARDS" k="card_ids" items={contents.cards} render={(c) => c.name + (c.from_text ? " · from TEXT" : "")} />
        </div>
      )}
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
        <label style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "center" }} title="A TEXT project brings its LORE project and the cards made from it">
          <input type="checkbox" checked={linked} onChange={(e) => setLinked(e.target.checked)} /> Include linked lore and cards
        </label>
        <input ref={fileRef} type="file" accept=".zip" style={{ display: "none" }} onChange={(e) => onImport(e.target.files?.[0])} aria-label="Bundle file to import" />
        <button className="signal-btn" style={{ ...btn, marginLeft: "auto" }} disabled={busy === "import"} onClick={() => fileRef.current?.click()}>
          {busy === "import" ? "IMPORTING…" : `↑ ${(t.importBundle || "Import bundle").toUpperCase()}`}</button>
        <button className="signal-btn" style={{ ...btn, background: "var(--signal-btn-active-bg)", color: "var(--signal-btn-active-text)" }}
          disabled={!count || busy === "export"} onClick={onExport}>{busy === "export" ? "PACKING…" : `↓ ${(t.exportSelected || "Export selected").toUpperCase()}${count ? ` (${count})` : ""}`}</button>
      </div>
    </section>
  );
}

export default function AdminPanels({ showToast, t = {} }) {
  const [presets, setPresets] = useState(null);
  const [backups, setBackups] = useState([]);
  const [usage, setUsage] = useState(null);
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [confirmRestore, setConfirmRestore] = useState(null);

  useEffect(() => {
    getPresets().then(setPresets).catch((e) => setError(e.message));
    refreshBackups();
  }, []);
  useEffect(() => { getUsage(days).then(setUsage).catch(() => setUsage(null)); }, [days]);

  async function refreshBackups() {
    try { setBackups((await listBackups()).backups || []); } catch (e) { setError(e.message); }
  }
  async function onSavePresets() {
    setBusy("presets"); setError("");
    try { await savePresets(presets); showToast && showToast("Model presets saved"); }
    catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }
  async function onBackup() {
    setBusy("backup"); setError("");
    try { const r = await makeBackup(); showToast && showToast(`Backup saved: ${r.name}`); await refreshBackups(); }
    catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }
  async function onRestore(name) {
    if (confirmRestore !== name) { setConfirmRestore(name); return; }
    setBusy("restore"); setError(""); setConfirmRestore(null);
    try {
      const r = await restoreBackup(name);
      showToast && showToast(`Restored ${name}. Your previous data was backed up as ${r.safety_backup}. Refresh the page.`);
      await refreshBackups();
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }
  const setPreset = (task, key, val) => setPresets((p) => ({ ...p, [task]: { ...(p?.[task] || {}), [key]: val } }));
  const kb = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

  return (
    <>
      {error && (
        <div style={{ color: "#c84a3a", fontSize: 13, padding: "8px 12px", border: "1px solid #c84a3a", display: "flex", justifyContent: "space-between" }}>
          <span>⊗ {error}</span>
          <button onClick={() => setError("")} aria-label="Dismiss error" style={{ background: "none", border: "none", color: "inherit", cursor: "pointer" }}>✕</button>
        </div>
      )}

      <section className="signal-panel signal-screen-panel" style={panel}>
        <h2 className="signal-heading" style={{ margin: "0 0 6px", fontSize: 15 }}>{t.modelPresets || "Model presets"}</h2>
        <div style={{ ...hint, marginBottom: 12 }}>Preselected in each studio. Leave a model empty to use the provider default from the keys below.</div>
        {!presets && <div style={hint}>Loading…</div>}
        {presets && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14 }}>
            {TASKS.map(([task, label, tip]) => (
              <div key={task}>
                <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.06em" }}>{label}</div>
                <div style={{ ...hint, marginBottom: 4 }}>{tip}</div>
                <div style={{ display: "flex", gap: 6 }}>
                  <select aria-label={`${label} provider`} value={presets[task]?.provider || ""} onChange={(e) => setPreset(task, "provider", e.target.value)}
                    style={{ ...input, width: "auto" }}>
                    <option value="">Any</option>
                    <option value="nanogpt">NanoGPT</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="local">Local</option>
                  </select>
                  <input aria-label={`${label} model`} value={presets[task]?.model || ""} onChange={(e) => setPreset(task, "model", e.target.value)}
                    placeholder="e.g. deepseek/deepseek-v4.1-flash" style={{ ...input, flex: 1, minWidth: 0 }} />
                </div>
              </div>
            ))}
          </div>
        )}
        <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end" }}>
          <button className="signal-btn" style={{ ...btn, background: "var(--signal-btn-active-bg)", color: "var(--signal-btn-active-text)" }}
            disabled={busy === "presets" || !presets} onClick={onSavePresets}>{busy === "presets" ? "SAVING…" : (t.savePresets || "Save presets").toUpperCase()}</button>
        </div>
      </section>

      <BundlePanel showToast={showToast} setError={setError} onImported={refreshBackups} t={t} />

      <section className="signal-panel signal-screen-panel" style={panel}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
          <h2 className="signal-heading" style={{ margin: 0, fontSize: 15 }}>{t.backups || "Backups"}</h2>
          <button className="signal-btn" style={{ ...btn, marginLeft: "auto" }} disabled={busy === "backup"} onClick={onBackup}>
            {busy === "backup" ? "BACKING UP…" : (t.backUpNow || "Back up now").toUpperCase()}</button>
        </div>
        <div style={{ ...hint, marginBottom: 10 }}>
          Copies of your database (cards, lore, texts) in data/backups. One is made each time the backend starts (at most hourly);
          the newest 12 are kept. Restoring first backs up what you have now.
        </div>
        {backups.length === 0 && <div style={hint}>No backups yet.</div>}
        <div style={{ maxHeight: 260, overflowY: "auto", border: backups.length ? "1px solid var(--signal-border)" : "none" }}>
          {backups.map((b) => (
            <div key={b.name} style={{ display: "flex", gap: 10, alignItems: "center", padding: "6px 10px", borderBottom: "1px solid var(--signal-border)", fontSize: 12, flexWrap: "wrap" }}>
              <span style={{ fontFamily: "monospace", flex: "1 1 260px", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{b.name}</span>
              <span style={hint}>{b.created} · {kb(b.bytes)}</span>
              <button className="signal-btn" style={{ ...btn, padding: "4px 10px", borderColor: confirmRestore === b.name ? "#c84a3a" : undefined,
                color: confirmRestore === b.name ? "#c84a3a" : undefined }} disabled={busy === "restore"} onClick={() => onRestore(b.name)}>
                {confirmRestore === b.name ? "CLICK AGAIN TO RESTORE" : (t.restore || "Restore").toUpperCase()}</button>
            </div>
          ))}
        </div>
      </section>

      <section className="signal-panel signal-screen-panel" style={panel}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
          <h2 className="signal-heading" style={{ margin: 0, fontSize: 15 }}>{t.modelUsage || "Model usage"}</h2>
          <select aria-label="Period" value={days} onChange={(e) => setDays(parseInt(e.target.value))} style={{ ...input, width: "auto", marginLeft: "auto" }}>
            <option value={1}>Today</option><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={365}>Last year</option>
          </select>
        </div>
        <div style={{ ...hint, marginBottom: 10 }}>Calls and tokens as reported by the provider. Local servers may not report tokens.</div>
        {!usage || !usage.rows.length ? <div style={hint}>No model calls in this period.</div> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
              <thead><tr>{["Model", "Calls", "Prompt tokens", "Reply tokens", "Time (s)", "Last used"].map((h) => (
                <th key={h} style={{ textAlign: h === "Model" ? "left" : "right", padding: "6px 8px", borderBottom: "1px solid var(--signal-border)", fontWeight: 700 }}>{h}</th>))}</tr></thead>
              <tbody>
                {usage.rows.map((r) => (
                  <tr key={r.provider + r.model}>
                    <td style={{ padding: "5px 8px", fontFamily: "monospace" }}>{r.provider}/{r.model || "default"}</td>
                    <td style={{ padding: "5px 8px", textAlign: "right" }}>{(r.calls || 0).toLocaleString()}</td>
                    <td style={{ padding: "5px 8px", textAlign: "right" }}>{(r.prompt_tokens || 0).toLocaleString()}</td>
                    <td style={{ padding: "5px 8px", textAlign: "right" }}>{(r.completion_tokens || 0).toLocaleString()}</td>
                    <td style={{ padding: "5px 8px", textAlign: "right" }}>{r.seconds ?? 0}</td>
                    <td style={{ padding: "5px 8px", textAlign: "right" }}>{String(r.last_used || "").slice(0, 16)}</td>
                  </tr>
                ))}
                <tr style={{ fontWeight: 700 }}>
                  <td style={{ padding: "6px 8px", borderTop: "1px solid var(--signal-border)" }}>Total</td>
                  <td style={{ padding: "6px 8px", textAlign: "right", borderTop: "1px solid var(--signal-border)" }}>{usage.total.calls.toLocaleString()}</td>
                  <td style={{ padding: "6px 8px", textAlign: "right", borderTop: "1px solid var(--signal-border)" }}>{usage.total.prompt_tokens.toLocaleString()}</td>
                  <td style={{ padding: "6px 8px", textAlign: "right", borderTop: "1px solid var(--signal-border)" }}>{usage.total.completion_tokens.toLocaleString()}</td>
                  <td colSpan={2} style={{ borderTop: "1px solid var(--signal-border)" }} />
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
