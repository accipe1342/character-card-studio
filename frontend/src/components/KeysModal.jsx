/**
 * KeysModal.jsx — the "?" sheet: every key the app listens for, grouped by where it works.
 *
 * Opened by pressing ? anywhere (when the cursor is not in a text box) or from the "? :: KEYS" hint in the footer,
 * which fires openKeys() from lib/keysBus. Only keys that are really wired up belong in GROUPS below: the sheet is
 * a promise to the reader.
 */
import { useEffect } from "react";

const GROUPS = [
  ["Anywhere", [
    ["CTRL+K", "Search and commands"],
    ["CTRL+/", "Show or hide SCRIBE-01"],
    ["?", "This sheet"],
    ["ESC", "Close a dialog, menu or pending delete"],
  ]],
  ["Character", [
    ["J / K", "Next / previous field"],
    ["CTRL+ENTER", "Generate the card from the source"],
    ["", "Edits to a field save themselves"],
  ]],
  ["Lore", [
    ["J / K", "Next / previous entry"],
    ["CTRL+S", "Save the open entry"],
    ["X  or  DEL", "Move the entry to the trash (press twice)"],
    ["U", "Undo the last delete"],
  ]],
  ["Text", [
    ["J / K", "Next / previous entity"],
    ["↑ / ↓", "The same, either works"],
    ["CTRL+S", "Save the open entity"],
    ["X", "Keep or unkeep the entity"],
    ["DEL", "Delete the entity"],
    ["U", "Undo the last delete"],
  ]],
  ["SCRIBE-01", [
    ["ENTER", "Send what you typed"],
    ["SHIFT+ENTER", "New line instead of sending"],
    ["CTRL+/", "Hide to the bar, or bring it back"],
  ]],
];

export default function KeysModal({ open, onClose, t = {} }) {
  useEffect(() => {
    if (!open) return undefined;
    const esc = (e) => { if (e.key === "Escape") { e.preventDefault(); onClose(); } };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 400,
      display: "flex", justifyContent: "center", alignItems: "flex-start", padding: "8vh 16px 16px", overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label={t.keysTitle || "Keyboard shortcuts"}
        style={{ width: "min(1000px, 100%)", background: "var(--signal-bg-panel)", border: "1px solid var(--signal-border)",
          boxShadow: "5px 5px 0 var(--signal-shadow, rgba(78,75,66,.25)), 0 10px 30px rgba(0,0,0,0.25)",
          color: "var(--signal-text)", padding: 20, boxSizing: "border-box" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
          <span style={{ font: "300 28px var(--signal-font, inherit)", letterSpacing: "0.24em" }}>{t.keysTitle || "KEYS"}</span>
          <span style={{ fontSize: 12, letterSpacing: "0.14em", color: "var(--signal-text-dim)", textTransform: "uppercase" }}>
            :: {t.keysHint || "press ? anywhere"}
          </span>
          <span style={{ flex: 1 }} />
          <button type="button" className="signal-btn" onClick={onClose} style={{ padding: "8px 14px", letterSpacing: "0.14em" }}>
            ✕ {t.close || "CLOSE"}
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "20px 28px" }}>
          {GROUPS.map(([name, rows]) => (
            <div key={name}>
              <div className="sui-label" style={{ borderBottom: "1px solid var(--signal-border)", paddingBottom: 5, marginBottom: 5,
                fontSize: 11, fontWeight: 500, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--signal-text-dim)" }}>{name}</div>
              {rows.map(([k, label]) => (
                <div key={label} style={{ display: "flex", gap: 12, padding: "5px 0", fontSize: 13 }}>
                  <span style={{ flex: 1, color: k ? "var(--signal-text)" : "var(--signal-text-dim)" }}>{label}</span>
                  <span style={{ fontSize: 11, fontWeight: 500, letterSpacing: "0.1em", color: "var(--signal-text-dim)", whiteSpace: "nowrap" }}>{k}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16, paddingTop: 10, borderTop: "1px solid var(--signal-border)", fontSize: 12, color: "var(--signal-text-dim)" }}>
          {t.keysFootnote || "Single-letter keys work when the cursor is not in a text box."}
        </div>
      </div>
    </div>
  );
}
