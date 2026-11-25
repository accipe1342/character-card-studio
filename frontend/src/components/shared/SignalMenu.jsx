/**
 * SignalMenu.jsx — a toolbar button that opens a small drop-down (Generate ▾, Tools ▾, Export ▾).
 *
 *   <SignalMenu label="EXPORT" align="right">
 *     <MenuItem onClick={...}>SillyTavern World Info (.json)</MenuItem>
 *     <MenuLabel>EMBED</MenuLabel> ... <MenuSep />
 *   </SignalMenu>
 *
 * Closes on a pick, a click outside or Escape. Items are real buttons (role="menuitem"), so tests and keyboards
 * reach them the same way.
 */
import { Children, cloneElement, isValidElement, useEffect, useLayoutEffect, useRef, useState } from "react";

/** why: shown (dim, on the right) when the item is disabled, so an unavailable item says what it needs. */
export function MenuItem({ children, onClick, disabled, title, keepOpen, why, _close }) {
  return (
    <button type="button" role="menuitem" className="sui-menu-item" disabled={disabled} title={disabled && why ? why : title}
      data-keep-open={keepOpen ? "" : undefined} onClick={(e) => { if (!keepOpen) _close?.(); onClick?.(e); }}>
      {children}
      {disabled && why && <span className="why">{why}</span>}
    </button>
  );
}

export function MenuLabel({ children }) {
  return <div className="sui-menu-label">{children}</div>;
}

export function MenuSep() {
  return <div className="sui-menu-sep" role="separator" />;
}

/** keepMounted: the items stay mounted while the menu is closed (for items that own a dialog, like Quick Replies). */
export default function SignalMenu({ label, children, align = "left", primary = false, style, title, disabled, width, keepMounted = false,
  btnClass = "signal-btn", menuClass = "", ariaLabel, id, wrapStyle }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const pop = useRef(null);
  // Put the menu where it fits: sideways, so one near the right edge opens leftwards instead of off-screen, and
  // up or down, so one near the bottom is not cut off. Written straight onto the node before paint — as state
  // this would need one render to measure and another to move.
  useLayoutEffect(() => {
    const el = pop.current, anchor = ref.current;
    if (!open || !el || !anchor) return undefined;
    const GAP = 6, EDGE = 8;                 // 6px off the button, 8px clear of the window edge
    const place = () => {
      const put = (side) => { el.style.left = side === "right" ? "auto" : "0"; el.style.right = side === "right" ? "0" : "auto"; };
      put(align);
      el.style.maxHeight = "";
      el.style.top = `calc(100% + ${GAP}px)`;
      el.style.bottom = "auto";
      const b = anchor.getBoundingClientRect();
      const r = el.getBoundingClientRect();
      if (align === "left" && r.right > window.innerWidth - EDGE && b.right - r.width >= EDGE) put("right");
      else if (align === "right" && r.left < EDGE && b.left + r.width <= window.innerWidth - EDGE) put("left");
      // vertical: keep it below unless there is more room above, then cap it so a long list scrolls
      const below = window.innerHeight - b.bottom - GAP - EDGE;
      const above = b.top - GAP - EDGE;
      const upward = r.height > below && above > below;
      if (upward) {
        el.style.top = "auto";
        el.style.bottom = `calc(100% + ${GAP}px)`;
      }
      el.style.maxHeight = `${Math.max(140, Math.floor(upward ? above : below))}px`;
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);     // a menu inside a panel that scrolls moves with it
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open, align]);
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
    <div ref={ref} style={{ position: "relative", display: "inline-flex", ...wrapStyle }}>
      <button type="button" className={`${btnClass}${(primary || open) && btnClass === "signal-btn" ? " signal-btn-active" : ""}${(primary || open) && btnClass !== "signal-btn" ? " is-open" : ""}`} aria-haspopup="menu" aria-expanded={open} aria-label={ariaLabel} id={id} data-keep-open
        disabled={disabled} title={title} onClick={() => setOpen((v) => !v)}
        style={{ padding: "10px 14px", border: "1px solid transparent", cursor: "pointer", letterSpacing: "0.14em", fontSize: 13, whiteSpace: "nowrap", ...style }}>
        {label} ▾
      </button>
      {(open || keepMounted) && (
        <div ref={pop} role="menu" aria-label={String(label)} className={`sui-menu${menuClass ? ` ${menuClass}` : ""}`} hidden={!open} data-keep-open
          onClick={(e) => {
          if (!e.target.closest || !e.target.closest("button")) return;
          const keep = e.target.closest("[data-keep-open]");
          if (keep && keep !== e.currentTarget) return;   // a menu nested in this one owns the click
          close();
        }}
          style={{ minWidth: Math.min(width || 240, window.innerWidth - 16),
            maxWidth: "calc(100vw - 16px)", display: open ? "block" : "none" }}>
          {kids}
        </div>
      )}
    </div>
  );
}
