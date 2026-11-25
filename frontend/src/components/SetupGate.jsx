/**
 * SetupGate — the first-run wall, removed.
 *
 * A fresh install has no API key and no local server, so the first Generate fails with a model error
 * that explains nothing. This asks the backend whether anything is connected (GET /api/setup/status)
 * and, when nothing is, says so before the person starts and offers the three ways to fix it:
 * paste a key, point at a local server, or open CONFIG. It disappears the moment one works, and a
 * returning install never sees it.
 */
import { useCallback, useEffect, useState } from "react";

import SelectMenu from "./shared/SelectMenu";

const LINE = "var(--signal-line, #b9b29c)";
const DIM = "var(--signal-dim, #6f6a58)";
const REDUCED = typeof window !== "undefined"
  && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export default function SetupGate({ onOpenConfig }) {
  const [status, setStatus] = useState(null);      // null = not asked yet
  const [key, setKey] = useState("");
  const [provider, setProvider] = useState("nanogpt");
  const [localUrl, setLocalUrl] = useState("http://localhost:1234/v1");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("idle");      // idle -> checking -> done -> (unmounted)
  const [error, setError] = useState("");
  const [dismissed, setDismissed] = useState(false);

  const check = useCallback(async () => {
    try {
      const r = await fetch("/api/setup/status");
      setStatus(await r.json());
    } catch {
      setStatus({ ready: true });                  // never block the app because this one call failed
    }
  }, []);

  useEffect(() => { check(); }, [check]);

  async function save(body) {
    setBusy(true); setError(""); setPhase("checking");
    try {
      const r = await fetch("/api/config/env", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Could not save");
      const s = await (await fetch("/api/setup/status")).json();
      if (s.ready) {
        // say so before leaving: a panel that vanishes mid-click reads as a glitch
        setStatus(s);
        setPhase(REDUCED ? "gone" : "done");
        if (!REDUCED) setTimeout(() => setPhase("gone"), 700);
        return;
      }
      setStatus(s);
      if (!s.ready) {
        setError(s.local?.configured && !s.local?.reachable
          ? `Nothing answered at ${s.local.url}. Is the server running?`
          : "Saved, but still nothing connected.");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      setPhase((p) => (p === "checking" ? "idle" : p));
    }
  }

  if (!status || dismissed || phase === "gone") return null;
  if (status.ready && phase === "idle") return null;

  const field = { background: "rgba(255,255,255,0.35)", color: "inherit", border: "none",
    boxShadow: `inset 0 0 0 1px ${LINE}`, padding: "8px 10px", font: "inherit", fontSize: 13, width: "100%" };

  return (
    <div className="signal-panel" role="region" aria-label="Connect a model"
      style={{ margin: "0 0 16px", padding: "14px 16px", border: `1px solid ${LINE}`, textAlign: "left",
        overflow: "hidden", maxHeight: phase === "done" ? 0 : 420, opacity: phase === "done" ? 0 : 1,
        transition: REDUCED ? "none"
          : "max-height .32s var(--signal-soft), opacity .28s var(--signal-soft), padding .32s var(--signal-soft), margin .32s var(--signal-soft)",
        ...(phase === "done" ? { padding: "0 16px", margin: 0 } : null) }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span aria-hidden="true" style={{ width: 8, height: 8, flex: "none", boxSizing: "border-box",
          background: phase === "done" ? "currentColor" : "transparent", border: phase === "done" ? "none" : "1px solid currentColor",
          transition: REDUCED ? "none" : "background .2s linear" }} />
        <span style={{ letterSpacing: "0.22em", fontWeight: 500, fontSize: 12 }}>
          {phase === "done" ? "CONNECTED" : "FIRST RUN"}</span>
        <span style={{ color: DIM, fontSize: 12 }}>
          {phase === "done"
            ? `:: ${(status.providers || []).map((p) => p.label.toUpperCase()).join(" · ") || "READY"}`
            : ":: NO MODEL CONNECTED YET"}</span>
        <span style={{ flex: 1 }} />
        <button type="button" className="signal-btn" style={{ fontSize: 11, padding: "4px 10px" }}
          onClick={() => setDismissed(true)}>Skip for now</button>
      </div>

      <p style={{ margin: "10px 0 12px", fontSize: 13, lineHeight: 1.55, maxWidth: 640 }}>
        Everything here runs on your machine, but the writing itself needs a model. Connect one and this
        panel goes away. Generating without one just fails.
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={{ fontSize: 11, letterSpacing: "0.14em", color: DIM }}>
          PROVIDER
          <div style={{ marginTop: 4 }}>
            <SelectMenu label="Provider" value={provider} onChange={setProvider} width={210}
              options={[{ value: "nanogpt", label: "NanoGPT (key)" },
                        { value: "openrouter", label: "OpenRouter (key)" },
                        { value: "local", label: "Local server" }]}
              style={{ ...field, width: 180, display: "inline-flex", justifyContent: "space-between", gap: 8,
                       letterSpacing: "0.04em", textAlign: "left" }} />
          </div>
        </label>

        {provider === "local" ? (
          <label style={{ fontSize: 11, letterSpacing: "0.14em", color: DIM, flex: "1 1 280px" }}>
            ADDRESS
            <input value={localUrl} onChange={(e) => setLocalUrl(e.target.value)} style={{ ...field, marginTop: 4 }}
              placeholder="http://localhost:1234/v1" aria-label="Local server address" />
          </label>
        ) : (
          <label style={{ fontSize: 11, letterSpacing: "0.14em", color: DIM, flex: "1 1 280px" }}>
            API KEY
            <input value={key} onChange={(e) => setKey(e.target.value)} type="password" style={{ ...field, marginTop: 4 }}
              placeholder="Paste the key" aria-label="API key" />
          </label>
        )}

        <button type="button" className="signal-btn signal-btn-active" disabled={busy}
          style={{ padding: "9px 16px", fontSize: 12 }}
          onClick={() => save(provider === "local"
            ? { LOCAL_OPENAI_BASE_URL: localUrl.trim() }
            : { [provider === "nanogpt" ? "NANOGPT_API_KEY" : "OPENROUTER_API_KEY"]: key.trim() })}>
          {busy ? "CHECKING…" : "CONNECT"}
        </button>
      </div>

      <div aria-hidden="true" style={{ height: 2, marginTop: 12, overflow: "hidden",
        background: "rgba(110,105,91,0.25)", opacity: phase === "checking" && !REDUCED ? 1 : 0,
        transition: "opacity .2s linear" }}>
        <div className={phase === "checking" && !REDUCED ? "signal-scan" : undefined}
          style={{ height: "100%", width: "30%", background: "currentColor" }} />
      </div>

      {error && <div style={{ color: "var(--signal-accent, #863a29)", fontSize: 12, marginTop: 8 }}>⊗ {error}</div>}

      <div style={{ color: DIM, fontSize: 12, marginTop: 10, lineHeight: 1.5 }}>
        No key? NanoGPT and OpenRouter both sell credit; a local server (LM Studio, Ollama, KoboldCPP) needs none.
        {onOpenConfig && <> You can also set this up in <button type="button" onClick={onOpenConfig}
          style={{ background: "none", border: "none", font: "inherit", color: "inherit", textDecoration: "underline",
            cursor: "pointer", padding: 0 }}>CONFIG → API Keys</button>.</>}
      </div>
    </div>
  );
}
