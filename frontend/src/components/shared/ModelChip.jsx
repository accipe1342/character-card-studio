/**
 * ModelChip.jsx — the toolbar chip "NANOGPT · DEFAULT ▾". It opens a small panel holding the provider select and
 * the model picker (passed as children), so the two no longer need a row of their own.
 * Closes on a click outside or Escape.
 */
import { useEffect, useRef, useState } from "react";

const NAMES = { nanogpt: "NANOGPT", openrouter: "OPENROUTER", local: "LOCAL" };

export default function ModelChip({ provider, model, children, t = {} }) {
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
  const short = model ? String(model).split("/").pop() : (t.defaultModel || "DEFAULT");
  return (
    <div ref={ref} style={{ position: "relative", display: "inline-flex", minWidth: 0 }}>
      <button type="button" className="sui-chip-btn" aria-haspopup="dialog" aria-expanded={open}
        title={`${t.providerModel || "Provider and model"}: ${NAMES[provider] || provider}${model ? ` / ${model}` : ""}`}
        onClick={() => setOpen((v) => !v)}>
        <span className="sui-chip-text">{NAMES[provider] || String(provider || "").toUpperCase()} · {String(short).toUpperCase()}</span> ▾
      </button>
      {open && (
        <div role="dialog" aria-label={t.providerModel || "Provider and model"} className="sui-menu sui-chip-pop">
          <div className="sui-menu-label" style={{ padding: "0 0 6px" }}>{t.providerModel || "Provider and model"}</div>
          {children}
        </div>
      )}
    </div>
  );
}
