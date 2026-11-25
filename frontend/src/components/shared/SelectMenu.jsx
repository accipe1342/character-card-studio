/**
 * SelectMenu.jsx — a drop-down that is part of the app instead of the browser.
 *
 * Same job as <select>: one value out of a list. A native select's list is drawn by the operating system (white
 * panel, blue highlight), which no stylesheet can reach, so this builds it from the menu the toolbars already use.
 *
 *   <SelectMenu label="Entry type" value={type} onChange={setType}
 *     options={[{ value: "place", label: "Place" }, "other"]} />
 *
 * options  array of {value, label} or plain strings
 * filter   a search box above the list; defaults to on once there are more than 12 options
 * tone     "console" puts it in SCRIBE-01's colours
 * Arrow keys and Home / End move, Enter picks, Escape closes, and a letter jumps to the first option starting with
 * it (what a native select gave for free).
 */
import { useRef, useState } from "react";
import SignalMenu, { MenuItem } from "./SignalMenu";

export default function SelectMenu({ value, onChange, options = [], label, width = 240, filter, disabled,
  placeholder = "Select…", tone = "page", style, title, id }) {
  const [q, setQ] = useState("");
  const boxRef = useRef(null);
  const opts = options.map((o) => (typeof o === "object" && o !== null ? o : { value: o, label: String(o) }));
  const current = opts.find((o) => String(o.value) === String(value ?? ""));
  const useFilter = filter ?? opts.length > 12;
  const needle = q.trim().toLowerCase();
  const shown = needle ? opts.filter((o) => String(o.label).toLowerCase().includes(needle)) : opts;

  function onKeyDown(e) {
    const items = [...(boxRef.current?.querySelectorAll('[role="menuitem"]') || [])];
    if (!items.length) return;
    const at = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      items[e.key === "ArrowDown" ? Math.min(items.length - 1, at + 1) : Math.max(0, at < 0 ? 0 : at - 1)]?.focus();
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      (e.key === "Home" ? items[0] : items[items.length - 1]).focus();
    } else if (!useFilter && e.key.length === 1 && /\S/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const hit = items.find((el) => el.textContent.trim().toLowerCase().startsWith(e.key.toLowerCase()));
      if (hit) { e.preventDefault(); hit.focus(); }
    }
  }

  return (
    <SignalMenu label={current ? current.label : placeholder} width={width} disabled={disabled}
      title={title || label} ariaLabel={label} style={style} id={id}
      btnClass={tone === "console" ? "scribe-btn" : "signal-btn"} menuClass={tone === "console" ? "is-console" : ""}>
      <div ref={boxRef} onKeyDown={onKeyDown}>
        {useFilter && (
          <div className="sui-menu-filter" data-keep-open>
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} aria-label={`Filter ${label || "the list"}`}
              placeholder="Filter…" onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); boxRef.current?.querySelector('[role="menuitem"]')?.focus(); } }} />
          </div>
        )}
        {shown.map((o) => (
          <MenuItem key={String(o.value)} onClick={() => onChange(o.value)} disabled={o.disabled}>
            {o.label}
            {String(o.value) === String(value ?? "") && <span style={{ marginLeft: "auto" }} aria-hidden="true">✓</span>}
          </MenuItem>
        ))}
        {!shown.length && <div className="sui-menu-label">Nothing matches “{q}”</div>}
      </div>
    </SignalMenu>
  );
}
