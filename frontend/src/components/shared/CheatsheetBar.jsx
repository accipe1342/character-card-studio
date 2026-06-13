/**
 * CheatsheetBar.jsx — SillyTavern variable reference
 * ====================================================
 * A collapsible toolbar showing SillyTavern template variables
 * ({{char}}, {{user}}, etc.). Clicking a variable inserts it at
 * the cursor position in the active textarea.
 *
 * PROPS
 * -----
 * onInsert(variable)  Called with the variable string when clicked
 * t                   Translation strings
 *
 * VARIABLES SHOWN
 * ---------------
 * {{char}}    Character name
 * {{user}}    User/player name
 * {{persona}} User persona description
 * {{random}}  Random element from a list
 * <br>        Line break
 *
 * HOW TO EXTEND
 * -------------
 * - Add more variables: add entries to the VARIABLES array inside
 *   the component. Each entry has a label and a value to insert.
 * - Change insert behaviour: edit the onInsert call. Currently the
 *   parent (CharacterStudio) handles the actual textarea insertion.
 */

import { useState } from "react";

// ── Token counting ────────────────────────────────────────────────────────────
function countTokens(text) {
  if (!text) return 0;
  const str = Array.isArray(text) ? text.join(" ") : String(text);
  const words = str.trim().split(/\s+/).filter(Boolean);
  let tokens = 0;
  for (const w of words) {
    tokens += 1 + Math.floor(Math.max(0, w.length - 4) / 4);
  }
  return tokens;
}

function tokenColor(count) {
  if (count < 200) return "#9a4a4a";
  if (count < 400) return "#b04a4a";
  if (count < 700) return "#c8603a";
  return "#c84a3a";
}

// ── Cheatsheet data ───────────────────────────────────────────────────────────
const SECTIONS = [
  {
    label: "Values",
    rows: [
      { left: "{{char}}",      mid: "Main value",    right: "{{user}}" },
      { left: "<{{char}}>",    mid: "Open tag",      right: "</{{char}}>" },
      { left: "<{{user}}>",    mid: "Close tag",     right: "</{{user}}>" },
    ],
  },
  {
    label: "Blocks",
    rows: [
      { left: "[<tag>",   mid: "Global tag",    right: "</tag>]" },
      { left: "<tag>",    mid: "Inner tag",     right: "</tag>" },
      { left: "[tag]",    mid: "Bracket text",  right: "![tag]" },
    ],
  },
  {
    label: "Misc",
    rows: [
      { left: "{{// (TEXT",  mid: null, right: "*TEXT*",   extra: '"TEXT"' },
    ],
    more: [
      { left: "<START>",        right: "<appearance>" },
      { left: "</appearance>",  right: "<persona>" },
      { left: "</persona>",     right: "<body>" },
      { left: "</body>",        right: "<quirks>" },
      { left: "</quirks>",      right: "<history>" },
      { left: "</history>",     right: null },
    ],
  },
];

// ── Component ─────────────────────────────────────────────────────────────────
export default function CheatsheetBar({ textareaRef, value, onChange, t = {}, totalTokens = 0 }) {
  const [open, setOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const tokens = countTokens(value);

  function insertTag(text) {
    if (!text) return;
    const el = textareaRef?.current;
    if (!el) {
      onChange((value || "") + text);
      return;
    }
    const start = el.selectionStart ?? (value || "").length;
    const end = el.selectionEnd ?? start;
    const before = (value || "").slice(0, start);
    const after = (value || "").slice(end);
    onChange(before + text + after);
    requestAnimationFrame(() => {
      el.focus();
      el.selectionStart = start + text.length;
      el.selectionEnd = start + text.length;
    });
  }

  const chip = (label, extraStyle = {}) => (
    <button
      key={label}
      className="signal-btn"
      onClick={() => insertTag(label)}
      title={`Insert: ${label}`}
      style={{
        padding: "4px 10px",
        fontSize: 12,
        fontFamily: "monospace",
        letterSpacing: 0,
        cursor: "pointer",
        border: "1px solid var(--signal-border)",
        whiteSpace: "nowrap",
        ...extraStyle,
      }}
    >
      {label}
    </button>
  );

  const midLabel = (text) => (
    <span style={{
      fontSize: 11,
      color: "var(--signal-text-dim)",
      letterSpacing: "0.04em",
      whiteSpace: "nowrap",
      padding: "0 4px",
    }}>
      {text}
    </span>
  );

  return (
    <div style={{ marginBottom: 4 }}>
      {/* Toggle bar + token count */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: open ? 6 : 0 }}>
        <button
          className="signal-btn"
          onClick={() => setOpen(o => !o)}
          style={{
            padding: "3px 10px",
            fontSize: 11,
            letterSpacing: "0.08em",
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            gap: 5,
            border: "1px solid var(--signal-border)",
          }}
        >
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
            <rect x="0.5" y="0.5" width="4" height="4" stroke="currentColor" strokeWidth="1"/>
            <rect x="6.5" y="0.5" width="4" height="4" stroke="currentColor" strokeWidth="1"/>
            <rect x="0.5" y="6.5" width="4" height="4" stroke="currentColor" strokeWidth="1"/>
            <rect x="6.5" y="6.5" width="4" height="4" stroke="currentColor" strokeWidth="1"/>
          </svg>
          CHEATSHEET {open ? "▴" : "▾"}
        </button>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
          <div style={{ fontSize: 11, letterSpacing: "0.06em", color: tokenColor(tokens) }}>
            <span style={{ opacity: 0.6 }}>~</span>
            <span style={{ fontWeight: 700 }}>{tokens}</span>
            <span style={{ opacity: 0.6 }}> {t.tokens || "tokens"}</span>
          </div>
          <div style={{
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: "0.04em",
            color: totalTokens > 2000 ? "#c84a3a" : totalTokens > 1000 ? "#c8923a" : "#9a4a4a",
          }}>
            <span style={{ opacity: 0.6, fontSize: 10, fontWeight: 400 }}>total ~</span>
            {totalTokens}
            <span style={{ opacity: 0.6, fontSize: 10, fontWeight: 400 }}> {t.tokens || "tokens"}</span>
          </div>
        </div>
      </div>

      {/* Cheatsheet panel */}
      {open && (
        <div style={{
          border: "1px solid var(--signal-border)",
          background: "var(--signal-bg-panel)",
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
          marginBottom: 6,
        }}>
          {SECTIONS.map(section => (
            <div key={section.label}>
              {/* Section label */}
              <div style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.12em",
                color: "var(--signal-text-dim)",
                textTransform: "uppercase",
                marginBottom: 6,
                borderBottom: "1px solid var(--signal-border)",
                paddingBottom: 3,
              }}>
                {section.label}
              </div>

              {/* Rows */}
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {section.rows.map((row, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    {chip(row.left)}
                    {row.mid && midLabel(row.mid)}
                    {row.right && chip(row.right)}
                    {row.extra && chip(row.extra)}
                  </div>
                ))}

                {/* More toggle */}
                {section.more && (
                  <>
                    <button
                      className="signal-btn"
                      onClick={() => setMoreOpen(o => !o)}
                      style={{
                        padding: "5px",
                        fontSize: 11,
                        fontWeight: 700,
                        letterSpacing: "0.06em",
                        border: "1px solid var(--signal-border)",
                        marginTop: 2,
                        width: "100%",
                      }}
                    >
                      {moreOpen ? "Less ▴" : "More ▾"}
                    </button>

                    {moreOpen && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 2 }}>
                        {section.more.reduce((rows, item, idx) => {
                          if (idx % 2 === 0) rows.push([item]);
                          else rows[rows.length - 1].push(item);
                          return rows;
                        }, []).map((pair, i) => (
                          <div key={i} style={{ display: "flex", gap: 6 }}>
                            {chip(pair[0].left)}
                            {pair[1]?.left && chip(pair[1].left)}
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          <div style={{ fontSize: 10, color: "var(--signal-text-dim)", letterSpacing: "0.04em" }}>
            Click to insert at cursor ·{" "}
            <a
              href="https://docs.sillytavern.app/usage/core-concepts/characterdesign/#replacement-tags-macros"
              target="_blank" rel="noreferrer"
              style={{ color: "var(--signal-text-dim)" }}
            >
              Full guide ↗
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
