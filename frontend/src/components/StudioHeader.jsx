/**
 * StudioHeader.jsx — the Signal UI page header under the tabs (large thin title on the left, a ":: subtitle" under
 * it, a hairline with a diamond and "||", and on the right what is open: the card, lorebook / entry or story the
 * studio tells the helper about) plus KeyFooter, the staff-line footer with key hints.
 */
import { useEffect, useRef } from "react";
import { toggleHelper } from "../lib/helperBus";
import { openKeys } from "../lib/keysBus";
import { useHeaderLink, useStudioContext } from "../lib/useStudioContext";

const TITLES = { character: ["character", "CHARACTER"], lore: ["lore", "LORE"], text: ["text", "TEXT"], config: ["config", "CONFIG"] };
const SUBS = {
  character: ["subtitle", "Preview image • Source data • Editable card"],
  lore: ["loreSubtitle", "World entries • factions • places • events"],
  text: ["textSubtitle", "Fanfiction & long text • chapters • characters • events"],
  config: ["configSubtitle", "Prompt templates • API keys"],
};

export default function StudioHeader({ mode, t = {}, onOpenLink }) {
  const ctx = useStudioContext(mode);
  const link = useHeaderLink(mode);
  const ref = useRef(null);
  // once the page scrolls, the tab row and toolbar turn solid (data-scrolled); once this header has left the
  // screen, the tab row shows what is open in its place (data-compact)
  useEffect(() => {
    const root = document.documentElement;
    const onScroll = () => {
      const y = window.scrollY || 0;
      const el = ref.current;
      root.toggleAttribute("data-scrolled", y > 4);
      root.toggleAttribute("data-compact", !!el && el.getBoundingClientRect().bottom < 56);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll);
      root.removeAttribute("data-scrolled"); root.removeAttribute("data-compact");
    };
  }, [mode]);
  const [tk, tf] = TITLES[mode] || ["", mode.toUpperCase()];
  const [sk, sf] = SUBS[mode] || ["", ""];
  const sub = String(t[sk] || sf).replace(/\s*•\s*/g, " · ");
  const label = ctx?.label ? String(ctx.label) : "";
  return (
    <header ref={ref} className="sui-header" style={{ display: "flex", alignItems: "flex-end", gap: 24, margin: "18px 0 18px", flexWrap: "wrap", textAlign: "left" }}>
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
        {link && (
          <button type="button" className="sui-ctx-link" onClick={() => onOpenLink?.(link)} title={t.openLorebook || "Open this card's lorebook in LORE"}>
            {link.label} →
          </button>
        )}
      </div>
    </header>
  );
}

const KEYS = {
  character: [["J / K", "FIELD"], ["CTRL+ENTER", "GENERATE"], ["CTRL+K", "SEARCH"], ["CTRL+/", "SCRIBE-01"], ["?", "KEYS"], ["", "EDITS AUTOSAVE"]],
  lore: [["CTRL+K", "SEARCH"], ["CTRL+/", "SCRIBE-01"], ["J / K", "NEXT ENTRY"], ["CTRL+S", "SAVE"], ["?", "KEYS"]],
  text: [["CTRL+K", "SEARCH"], ["CTRL+/", "SCRIBE-01"], ["J / K", "NEXT ENTITY"], ["?", "KEYS"]],
  config: [["CTRL+K", "SEARCH"], ["?", "KEYS"]],
};

/** the hints that do something when clicked */
const KEY_ACTIONS = { "CTRL+/": toggleHelper, "?": openKeys };

export function KeyFooter({ mode }) {
  return (
    <footer style={{ marginTop: 28, paddingBottom: 6 }}>
      <div className="sui-staff sui-staff-thin" aria-hidden="true"><i /><i /></div>
      <div className="sui-keys">
        <span style={{ marginRight: "auto" }}>CHARACTER CARD STUDIO</span>
        {(KEYS[mode] || KEYS.config).map(([k, v]) => (
          KEY_ACTIONS[k]
            ? <button key={k} type="button" onClick={KEY_ACTIONS[k]}
                style={{ background: "none", border: "none", padding: 0, font: "inherit", letterSpacing: "inherit", color: "inherit", cursor: "pointer" }}>
                {k} :: {v}
              </button>
            : <span key={v}>{k ? `${k} :: ` : ""}{v}</span>
        ))}
      </div>
    </footer>
  );
}
