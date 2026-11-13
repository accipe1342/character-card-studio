/**
 * StudioHeader.jsx — the Signal UI page header under the tabs (large thin title on the left, a ":: subtitle" under
 * it, a hairline with a diamond and "||", and on the right what is open: the card, lorebook / entry or story the
 * studio tells the helper about) plus KeyFooter, the staff-line footer with key hints.
 */
import { useEffect, useState } from "react";
import { getHelperContext, onHelperContext, toggleHelper } from "../lib/helperBus";

const TITLES = { character: ["character", "CHARACTER"], lore: ["lore", "LORE"], text: ["text", "TEXT"], config: ["config", "CONFIG"] };
const SUBS = {
  character: ["subtitle", "Preview image • Source data • Editable card"],
  lore: ["loreSubtitle", "World entries • factions • places • events"],
  text: ["textSubtitle", "Fanfiction & long text • chapters • characters • events"],
  config: ["configSubtitle", "Prompt templates • API keys"],
};

function useStudioContext(mode) {
  const [ctx, setCtx] = useState(() => getHelperContext(mode));
  useEffect(() => {
    setCtx(getHelperContext(mode));
    return onHelperContext((studio, c) => { if (studio === mode) setCtx(c); });
  }, [mode]);
  return ctx;
}

export default function StudioHeader({ mode, t = {} }) {
  const ctx = useStudioContext(mode);
  const [tk, tf] = TITLES[mode] || ["", mode.toUpperCase()];
  const [sk, sf] = SUBS[mode] || ["", ""];
  const sub = String(t[sk] || sf).replace(/\s*•\s*/g, " · ");
  const label = ctx?.label ? String(ctx.label) : "";
  return (
    <header style={{ display: "flex", alignItems: "flex-end", gap: 24, margin: "18px 0 18px", flexWrap: "wrap", textAlign: "left" }}>
      <div>
        <h1 className="sui-title">{String(t[tk] || tf).toUpperCase()}</h1>
        <div className="sui-sub">:: {sub}</div>
      </div>
      <div aria-hidden="true" style={{ flex: "1 1 120px", marginBottom: 8, display: "flex", alignItems: "center", gap: 6, color: "var(--signal-text)" }}>
        <span className="sui-diamond" />
        <span style={{ flex: 1, height: 1, background: "var(--signal-text)", opacity: 0.5 }} />
        <span style={{ fontSize: 11, letterSpacing: "0.2em" }}>||</span>
      </div>
      <div className="sui-ctx" style={{ marginBottom: 4, minWidth: 120 }}>
        {label ? label.split(" / ").map((x, i) => <div key={i}>{x}</div>) : <div>{mode === "config" ? "SETTINGS" : "NOTHING OPEN"}</div>}
      </div>
    </header>
  );
}

const KEYS = {
  character: [["CTRL+K", "SEARCH"], ["CTRL+/", "SCRIBE-01"], ["", "EDITS AUTOSAVE"]],
  lore: [["CTRL+K", "SEARCH"], ["CTRL+/", "SCRIBE-01"], ["J / K", "NEXT ENTRY"], ["CTRL+S", "SAVE"]],
  text: [["CTRL+K", "SEARCH"], ["CTRL+/", "SCRIBE-01"], ["J / K", "NEXT ENTITY"]],
  config: [["CTRL+K", "SEARCH"]],
};

export function KeyFooter({ mode }) {
  return (
    <footer style={{ marginTop: 28, paddingBottom: 6 }}>
      <div className="sui-staff sui-staff-thin" aria-hidden="true"><i /><i /></div>
      <div className="sui-keys">
        <span style={{ marginRight: "auto" }}>CHARACTER CARD STUDIO</span>
        {(KEYS[mode] || KEYS.config).map(([k, v]) => (
          k === "CTRL+/"
            ? <button key={k} type="button" onClick={toggleHelper}
                style={{ background: "none", border: "none", padding: 0, font: "inherit", letterSpacing: "inherit", color: "inherit", cursor: "pointer" }}>
                {k} :: {v}
              </button>
            : <span key={v}>{k ? `${k} :: ` : ""}{v}</span>
        ))}
      </div>
    </footer>
  );
}
