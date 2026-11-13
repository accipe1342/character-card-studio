/**
 * NierMenu.jsx — a toolbar button that opens a small drop-down (Generate ▾, Tools ▾, Export ▾).
 *
 *   <NierMenu label="EXPORT" align="right">
 *     <MenuItem onClick={...}>SillyTavern World Info (.json)</MenuItem>
 *     <MenuLabel>EMBED</MenuLabel> ... <MenuSep />
 *   </NierMenu>
 *
 * Closes on a pick, a click outside or Escape. Items are real buttons (role="menuitem"), so tests and keyboards
 * reach them the same way.
 */
import { Children, cloneElement, isValidElement, useEffect, useRef, useState } from "react";

export function MenuItem({ children, onClick, disabled, title, keepOpen, _close }) {
  return (
    <button type="button" role="menuitem" className="nier-menu-item" disabled={disabled} title={title} data-keep-open={keepOpen ? "" : undefined}
      onClick={(e) => { if (!keepOpen) _close?.(); onClick?.(e); }}>
      {children}
    </button>
  );
}

export function MenuLabel({ children }) {
  return <div className="nier-menu-label">{children}</div>;
}

export function MenuSep() {
  return <div className="nier-menu-sep" role="separator" />;
}

/** keepMounted: the items stay mounted while the menu is closed (for items that own a dialog, like Quick Replies). */
export default function NierMenu({ label, children, align = "left", primary = false, style, title, disabled, width, keepMounted = false }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  const close = () => setOpen(false);
  const kids = Children.map(children, (c) => (isValidElement(c) && c.type === MenuItem ? cloneElement(c, { _close: close }) : c));
  return (
    <div ref={ref} style={{ position: "relative", display: "inline-flex" }}>
      <button type="button" className={primary || open ? "signal-btn signal-btn-active" : "signal-btn"} aria-haspopup="menu" aria-expanded={open}
        disabled={disabled} title={title} onClick={() => setOpen((v) => !v)}
        style={{ padding: "10px 14px", border: "1px solid transparent", cursor: "pointer", letterSpacing: "0.14em", fontSize: 13, whiteSpace: "nowrap", ...style }}>
        {label} ▾
      </button>
      {(open || keepMounted) && (
        <div role="menu" aria-label={String(label)} className="nier-menu" hidden={!open}
          onClick={(e) => { if (e.target.closest && e.target.closest("button") && !e.target.closest("[data-keep-open]")) close(); }}
          style={{ top: "calc(100% + 6px)", [align === "right" ? "right" : "left"]: 0, minWidth: width || 240, display: open ? "block" : "none" }}>
          {kids}
        </div>
      )}
    </div>
  );
}
