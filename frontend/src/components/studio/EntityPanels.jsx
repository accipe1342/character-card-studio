/**
 * EntityPanels.jsx — extra tabs of the TEXT review editor (kept out of TextStudio.jsx):
 *   EntityChapters   what each chapter said about the entity, with the "roleplay starts after" point marked
 *   EntityMentions   every line of the text that names it, by chapter (no model call)
 *   PortraitSlot     a saved picture for a character; MAKE CARD carries it to the CHARACTER studio
 *   SecretsEditor    opt-in: facts only some characters know (each becomes a LORE entry filtered to them)
 */
import { useEffect, useState } from "react";
import { getEntityChapters, getEntityMentions, imageSrc, setEntityImage, setEntitySecrets, uploadImage } from "../../lib/api";
import { btnTool, hint, label } from "./textUi";

const box = { border: "1px solid var(--signal-border)", padding: "8px 10px", marginBottom: 8, fontSize: 12.5, lineHeight: 1.5 };

export function EntityTabs({ tab, setTab, isCharacter, extra = [] }) {
  const tabs = [["edit", "EDIT"], ["chapters", "BY CHAPTER"], ["mentions", "MENTIONS"], ...extra];
  return (
    <div role="tablist" aria-label="Entry views" style={{ display: "flex", gap: 4, marginTop: 10, flexWrap: "wrap" }}>
      {tabs.filter(([k]) => isCharacter || k !== "interview").map(([k, t]) => (
        <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "signal-btn signal-btn-active" : "signal-btn"}
          style={{ ...btnTool, padding: "5px 10px" }} onClick={() => setTab(k)}>{t}</button>
      ))}
    </div>
  );
}

export function EntityChapters({ entityId, onJump }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setD(null); setError("");
    getEntityChapters(entityId).then(setD).catch((e) => setError(e.message));
  }, [entityId]);
  if (error) return <div style={{ color: "#c84a3a", fontSize: 12, marginTop: 8 }}>⊗ {error}</div>;
  if (!d) return <div style={{ ...hint, marginTop: 8 }}>Loading…</div>;
  let markerShown = false;
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ ...hint, marginTop: 0, marginBottom: 8 }}>
        What each chapter's extraction said about {d.name}, in story order.
        {d.upto >= 0
          ? (d.cutoff
            ? ` Roleplay starts after "${d.start_label}": lore and cards use only the chapters above the line${d.later ? ` (${d.later} later chapter(s) left out)` : ""}.`
            : ` Roleplay starts after "${d.start_label}", but "only facts up to the starting point" is off, so everything is used.`)
          : " No starting point is set, so everything is used."}
        {d.edited && " This entry was edited by hand, so your text is used as it is."}
      </div>
      {!d.chapters.length && <div style={hint}>No chapter mentions this entry in its extraction (it may come from a manual merge).</div>}
      {d.chapters.map((c) => {
        const marker = d.upto >= 0 && c.after_start && !markerShown;
        if (marker) markerShown = true;
        return (
          <div key={c.chunk}>
            {marker && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "10px 0", color: "#c84a3a", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em" }}>
                <span style={{ flex: 1, borderTop: "1px dashed #c84a3a" }} /> ROLEPLAY STARTS HERE <span style={{ flex: 1, borderTop: "1px dashed #c84a3a" }} />
              </div>
            )}
            <div style={{ ...box, opacity: c.after_start && d.cutoff ? 0.55 : 1 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 4 }}>
                <button className="signal-btn" onClick={() => onJump && onJump(c.chunk)} title="Show this chunk"
                  style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontWeight: 700, color: "inherit", fontFamily: "inherit", fontSize: 12, textDecoration: onJump ? "underline" : "none" }}>
                  {c.chunk + 1}. {c.label}
                </button>
                {c.age && <span style={hint}>age: {c.age}</span>}
              </div>
              {c.facts ? <div>{c.facts}</div> : <div style={hint}>Named here, no facts noted.</div>}
              {c.voice?.length > 0 && <div style={{ ...hint, marginTop: 4 }}>Says: {c.voice.map((v) => `“${v}”`).join(" · ")}</div>}
              {c.relations?.length > 0 && <div style={{ ...hint, marginTop: 2 }}>Relations: {c.relations.map((r) => `${r.with} (${r.relation})`).join(", ")}</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function EntityMentions({ entityId }) {
  const [anyCase, setAnyCase] = useState(false);
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setD(null); setError("");
    getEntityMentions(entityId, anyCase).then(setD).catch((e) => setError(e.message));
  }, [entityId, anyCase]);
  if (error) return <div style={{ color: "#c84a3a", fontSize: 12, marginTop: 8 }}>⊗ {error}</div>;
  if (!d) return <div style={{ ...hint, marginTop: 8 }}>Searching the text…</div>;
  const shown = d.chapters.reduce((n, c) => n + c.lines.length, 0);
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700 }}>{d.total} line(s) in {d.chapters.length} chapter(s)</span>
        <label style={{ fontSize: 11, display: "flex", gap: 5, alignItems: "center" }}
          title="One-word names are matched with their capital letter so 'Will' or 'Rose' don't match ordinary words. Tick to ignore case.">
          <input type="checkbox" checked={anyCase} onChange={(e) => setAnyCase(e.target.checked)} /> ignore case
        </label>
      </div>
      <div style={{ ...hint, marginTop: 0, marginBottom: 8 }}>Searching for: {d.names.join(", ")}. Lines are quoted from your text, up to 4 per chapter{shown < d.total ? `; ${shown} of ${d.total} shown` : ""}.</div>
      {!d.total && <div style={hint}>The name and aliases never appear word for word. Check the aliases on the EDIT tab.</div>}
      {d.chapters.map((c) => (
        <div key={c.chunk} style={box}>
          <div style={{ ...label, margin: "0 0 4px" }}>{c.chunk + 1}. {c.label} · {c.count}</div>
          {c.lines.map((l, i) => <div key={i} style={{ marginBottom: 3 }}>“{l}”</div>)}
          {c.count > c.lines.length && <div style={hint}>+ {c.count - c.lines.length} more in this chapter</div>}
        </div>
      ))}
    </div>
  );
}

export function PortraitSlot({ entityId, image, onChange }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function pick(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true); setError("");
    try { const name = await uploadImage(f); await setEntityImage(entityId, name); onChange(name); }
    catch (er) { setError(er.message); }
    finally { setBusy(false); }
  }
  async function clear() {
    try { await setEntityImage(entityId, ""); onChange(""); } catch (er) { setError(er.message); }
  }
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10 }}>
      <label title="A picture for this character. MAKE CARD takes it to the CHARACTER studio as the card's portrait."
        style={{ width: 56, height: 72, border: "1px dashed var(--signal-border)", display: "grid", placeItems: "center", cursor: "pointer",
          overflow: "hidden", flex: "0 0 auto", fontSize: 10, color: "var(--signal-text-dim)", textAlign: "center" }}>
        {image ? <img src={imageSrc(image)} alt="Portrait" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : (busy ? "…" : "+ PICTURE")}
        <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" aria-label="Character picture" onChange={pick} style={{ display: "none" }} />
      </label>
      <div style={{ fontSize: 11, color: "var(--signal-text-dim)", lineHeight: 1.5 }}>
        {image ? <>Portrait saved. <button className="signal-btn" onClick={clear} style={{ ...btnTool, padding: "2px 6px", fontSize: 10 }}>REMOVE</button></>
          : "Optional portrait, used when you make a card."}
        {error && <div style={{ color: "#c84a3a" }}>⊗ {error}</div>}
      </div>
    </div>
  );
}

export function SecretsEditor({ entity, characterNames, onChange }) {
  const saved = entity.secrets || [];
  const [open, setOpen] = useState(saved.length > 0);
  const [rows, setRows] = useState(saved);
  const [status, setStatus] = useState("");
  useEffect(() => { setRows(entity.secrets || []); setOpen((entity.secrets || []).length > 0); setStatus(""); }, [entity.id]);   // reset when another entry opens (not on every edit of this one)
  const others = characterNames.filter((n) => n !== entity.name);
  async function save(next) {
    setStatus("saving…");
    try { const r = await setEntitySecrets(entity.id, next); onChange(r.secrets); setStatus("✓ saved"); }
    catch (e) { setStatus(`⊗ ${e.message}`); }
  }
  const update = (i, patch, persist) => {
    const next = rows.map((r, k) => (k === i ? { ...r, ...patch } : r));
    setRows(next);
    if (persist) save(next);
  };
  const fallback = entity.entity_type === "character" ? entity.name : "";
  return (
    <div style={{ border: "1px dashed var(--signal-border)", padding: "6px 8px", marginTop: 12 }}>
      <button className="signal-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: "inherit", fontFamily: "inherit", fontSize: 11, fontWeight: 700, letterSpacing: "0.12em" }}>
        {open ? "▾" : "▸"} SECRETS · WHO KNOWS THIS{rows.length ? ` · ${rows.length}` : ""}
      </button>
      {open && (<>
        <div style={{ ...hint, marginTop: 4 }}>
          Optional. A fact only some characters know. Each one becomes its own LORE entry with SillyTavern's character filter,
          so it only reaches the prompt when one of them is speaking (solo or group chat). It is left out of the Data Bank.
          The filter uses SillyTavern's character names: if it renamed a card (e.g. "{entity.name}2"), pick it again in the entry's Filter to Characters.
        </div>
        {rows.map((r, i) => (
          <div key={i} style={{ borderTop: "1px solid var(--signal-border)", paddingTop: 6, marginTop: 6 }}>
            <textarea value={r.text} rows={2} aria-label={`Secret ${i + 1}`} placeholder="e.g. She is the one who took the ledger."
              onChange={(e) => update(i, { text: e.target.value })} onBlur={() => save(rows)}
              style={{ width: "100%", boxSizing: "border-box", fontFamily: "inherit", fontSize: 12.5, padding: 6, border: "1px solid var(--signal-border)", background: "var(--signal-bg-input)", color: "var(--signal-text)", resize: "vertical" }} />
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, alignItems: "center", marginTop: 4 }}>
              <span style={{ fontSize: 11, color: "var(--signal-text-dim)" }}>Known by:</span>
              {(r.known_by || []).map((n) => (
                <button key={n} className="signal-btn" title="Remove" onClick={() => update(i, { known_by: r.known_by.filter((x) => x !== n) }, true)}
                  style={{ ...btnTool, padding: "1px 6px", fontSize: 11 }}>{n} ✕</button>
              ))}
              {!(r.known_by || []).length && <span style={{ fontSize: 11 }}>{fallback ? `only ${fallback}` : "nobody yet (pick someone)"}</span>}
              <select value="" aria-label={`Who knows secret ${i + 1}`} onChange={(e) => e.target.value && update(i, { known_by: [...(r.known_by || []), e.target.value] }, true)}
                style={{ fontFamily: "inherit", fontSize: 11, padding: "2px 4px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-input)", color: "var(--signal-text)" }}>
                <option value="">+ add…</option>
                {[entity.name, ...others].filter((n) => !(r.known_by || []).includes(n)).map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
              <button className="signal-btn" onClick={() => { const next = rows.filter((_, k) => k !== i); setRows(next); save(next); }}
                style={{ ...btnTool, padding: "1px 6px", fontSize: 11, marginLeft: "auto" }}>DELETE</button>
            </div>
          </div>
        ))}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
          <button className="signal-btn" style={{ ...btnTool, padding: "3px 8px", fontSize: 11 }} disabled={rows.length >= 12}
            onClick={() => setRows((rs) => [...rs, { text: "", known_by: [] }])}>+ ADD A SECRET</button>
          {status && <span style={{ fontSize: 11, color: status.startsWith("⊗") ? "#c84a3a" : "var(--signal-text-dim)" }}>{status}</span>}
        </div>
      </>)}
    </div>
  );
}
