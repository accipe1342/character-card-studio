/** Shared styles and small pieces for the TEXT studio and its panels. */

export const panelStyle = {
  border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)",
  padding: 14, textAlign: "left", minWidth: 0,
};
export const headingStyle = { marginTop: 0, textAlign: "center" };
export const btn = {
  padding: "10px 14px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-btn)",
  color: "var(--signal-text)", cursor: "pointer", fontFamily: "inherit", fontSize: 13,
  fontWeight: 700, letterSpacing: "0.06em",
};
export const btnPrimary = { ...btn, background: "var(--signal-btn-active-bg)", color: "var(--signal-btn-active-text)" };
export const btnSm = { ...btn, padding: "4px 9px", fontSize: 11 };
export const input = {
  width: "100%", padding: "10px 12px", border: "1px solid var(--signal-border)",
  background: "var(--signal-bg-input)", color: "var(--signal-text)", fontFamily: "inherit",
  fontSize: 14, boxSizing: "border-box", outline: "none",
};
export const label = { fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--signal-text-dim)", margin: "12px 0 5px" };
export const hint = { fontSize: 11, color: "var(--signal-text-dim)", marginTop: 4, lineHeight: 1.45 };

// review toolbars: equal-width buttons that wrap as a grid, so rows stay aligned at any panel width
export const toolbarGrid = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(118px, 1fr))", gap: 6 };
export const btnTool = {
  padding: "7px 10px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-btn)",
  color: "var(--signal-text)", cursor: "pointer", fontFamily: "inherit", fontSize: 11, fontWeight: 700,
  letterSpacing: "0.08em", whiteSpace: "nowrap", textAlign: "center",
};

// Fast, non-thinking model per provider. Extraction makes many calls, so a "thinking" model is far too slow.
export const DEFAULT_MODELS = { nanogpt: "deepseek/deepseek-v4.1-flash" };

export function Divider({ label: text, style }) {
  return (
    <div className="signal-divider" style={style}>
      <div className="signal-divider-mark signal-divider-mark-left" />
      <div className="signal-divider-bar" />
      <span className="signal-divider-label">{text}</span>
      <div className="signal-divider-bar" />
      <div className="signal-divider-mark signal-divider-mark-right" />
    </div>
  );
}
