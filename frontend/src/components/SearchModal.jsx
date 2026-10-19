/**
 * SearchModal.jsx — Ctrl+K (or the ⌕ button): search cards, lore entries, TEXT projects and entities, and jump there.
 * Arrow keys move, Enter opens, Esc closes.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { searchAll } from "../lib/api";

const groupLabel = { cards: "CARDS", lore: "LORE ENTRIES", texts: "TEXT PROJECTS", entities: "TEXT ENTITIES" };

export default function SearchModal({ open, onClose, onPick, t = {} }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [sel, setSel] = useState(0);
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  // reopening keeps the last search, selected, so typing replaces it
  useEffect(() => { if (open) { setSel(0); setTimeout(() => { inputRef.current?.focus(); inputRef.current?.select(); }, 20); } }, [open]);
  useEffect(() => {
    if (!open) return;
    if (q.trim().length < 2) { setRes(null); return; }
    const tm = setTimeout(() => {
      searchAll(q.trim()).then((r) => { setRes(r); setSel(0); setError(""); }).catch((e) => setError(e.message));
    }, 180);
    return () => clearTimeout(tm);
  }, [q, open]);
  const flat = useMemo(() => {
    if (!res) return [];
    const out = [];
    for (const g of ["cards", "lore", "entities", "texts"]) for (const it of res[g] || []) out.push({ group: g, ...it });
    return out;
  }, [res]);
  if (!open) return null;
  function pick(it) { onPick(it); onClose(); }
  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(flat.length - 1, s + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === "Enter" && flat[sel]) { e.preventDefault(); pick(flat[sel]); }
  }
  let lastGroup = null;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 400,
      display: "flex", justifyContent: "center", alignItems: "flex-start", padding: "10vh 16px 16px" }}>
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label={t.searchAll || "Search everything"} className="signal-panel"
        style={{ width: "min(640px, 100%)", background: "var(--signal-bg-panel)", border: "1px solid var(--signal-border)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.3)", color: "var(--signal-text)" }}>
        <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
          placeholder={`${t.searchAll || "Search everything"}: cards, lore, fics…`} aria-label={t.searchAll || "Search everything"}
          style={{ width: "100%", boxSizing: "border-box", padding: "14px 16px", border: "none", borderBottom: "1px solid var(--signal-border)",
            background: "var(--signal-bg-input)", color: "var(--signal-text)", fontFamily: "inherit", fontSize: 16, outline: "none" }} />
        <div style={{ maxHeight: "60vh", overflowY: "auto" }} role="listbox">
          {error && <div style={{ color: "#c84a3a", padding: 12, fontSize: 13 }}>⊗ {error}</div>}
          {q.trim().length >= 2 && res && !flat.length && <div style={{ padding: 14, fontSize: 13, color: "var(--signal-text-dim)" }}>Nothing found for “{q}”.</div>}
          {q.trim().length < 2 && <div style={{ padding: 14, fontSize: 12, color: "var(--signal-text-dim)" }}>Type at least 2 letters. ↑↓ to move, Enter to open, Esc to close.</div>}
          {flat.map((it, i) => {
            const head = it.group !== lastGroup ? groupLabel[it.group] : null;
            lastGroup = it.group;
            const title = it.name || it.title;
            const sub = it.group === "lore" ? `${it.entry_type} · ${it.project || "no project"}`
              : it.group === "entities" ? `${it.entity_type} · ${it.project}` : it.group === "texts" ? "TEXT project" : "card";
            return (
              <div key={`${it.group}${it.id}`}>
                {head && <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--signal-text-dim)", padding: "10px 16px 4px" }}>{head}</div>}
                <div role="option" aria-selected={i === sel} onMouseEnter={() => setSel(i)} onClick={() => pick(it)}
                  style={{ padding: "8px 16px", cursor: "pointer", borderLeft: `3px solid ${i === sel ? "var(--signal-text)" : "transparent"}`,
                    background: i === sel ? "var(--signal-bg-mid)" : "transparent" }}>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{title} <span style={{ fontSize: 11, fontWeight: 400, color: "var(--signal-text-dim)" }}>· {sub}</span></div>
                  {it.snippet && <div style={{ fontSize: 12, color: "var(--signal-text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.snippet}</div>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
