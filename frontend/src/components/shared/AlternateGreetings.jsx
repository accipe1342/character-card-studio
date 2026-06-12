import { useState } from "react";
import { regenerateGreeting } from "../../lib/api";

export default function AlternateGreetings({ greetings = [], onChange, t = {}, cardId }) {
  const [busyIdx, setBusyIdx] = useState(null);
  const [regenPrompt, setRegenPrompt] = useState({});
  const [showPrompt, setShowPrompt] = useState({});
  const [error, setError] = useState("");

  function update(idx, val) {
    const next = [...greetings];
    next[idx] = val;
    onChange(next);
  }

  function add() {
    onChange([...greetings, ""]);
  }

  function remove(idx) {
    onChange(greetings.filter((_, i) => i !== idx));
  }

  async function handleRegen(idx) {
    if (!cardId) return;
    setBusyIdx(idx);
    setError("");
    try {
      const data = await regenerateGreeting(cardId, idx, regenPrompt[idx] || "");
      update(idx, data.greeting);
      setShowPrompt(p => ({ ...p, [idx]: false }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyIdx(null);
    }
  }

  const btnStyle = {
    padding: "4px 10px",
    border: "1px solid var(--nier-border)",
    background: "var(--nier-bg-btn)",
    color: "var(--nier-text)",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.06em",
  };

  return (
    <div style={{ marginTop: 10 }}>
      <div className="nier-divider" style={{ marginBottom: 10 }}>
        <div className="nier-divider-mark nier-divider-mark-left" />
        <div className="nier-divider-bar" />
        <span className="nier-divider-label">
          {t.alternateGreetings || "Alternate Greetings"}
          {greetings.length > 0 && ` (${greetings.length})`}
        </span>
        <div className="nier-divider-bar" />
        <div className="nier-divider-mark nier-divider-mark-right" />
      </div>

      {error && (
        <div style={{ color: "#c84a3a", fontSize: 12, marginBottom: 8 }}>{error}</div>
      )}

      {greetings.length === 0 && (
        <div style={{ fontSize: 12, color: "var(--nier-text-dim)", marginBottom: 8, textAlign: "center" }}>
          {t.noAlternateGreetings || "No alternate greetings. Add one below."}
        </div>
      )}

      {greetings.map((g, idx) => (
        <div key={idx} style={{ marginBottom: 12 }}>
          {/* Header row */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <span style={{ fontSize: 10, letterSpacing: "0.1em", color: "var(--nier-text-dim)" }}>
              :: {t.greeting || "GREETING"} {idx + 1}
            </span>
            <div style={{ display: "flex", gap: 5 }}>
              <button
                className="nier-btn"
                onClick={() => setShowPrompt(p => ({ ...p, [idx]: !p[idx] }))}
                style={btnStyle}
                title="Custom prompt for regeneration"
              >
                ✎
              </button>
              <button
                className="nier-btn"
                disabled={busyIdx !== null}
                onClick={() => handleRegen(idx)}
                style={{
                  ...btnStyle,
                  opacity: busyIdx !== null ? 0.5 : 1,
                  cursor: busyIdx !== null ? "not-allowed" : "pointer",
                }}
              >
                {busyIdx === idx ? "…" : "⟳ " + (t.regenerateField || "Regen")}
              </button>
              <button
                className="nier-btn"
                onClick={() => remove(idx)}
                style={{ ...btnStyle, color: "#c84a3a", borderColor: "#c84a3a" }}
              >
                ✕
              </button>
            </div>
          </div>

          {/* Optional custom prompt */}
          {showPrompt[idx] && (
            <input
              value={regenPrompt[idx] || ""}
              onChange={(e) => setRegenPrompt(p => ({ ...p, [idx]: e.target.value }))}
              placeholder="Custom instruction for this greeting..."
              style={{
                width: "100%",
                padding: "6px 10px",
                marginBottom: 4,
                border: "1px solid var(--nier-border)",
                background: "var(--nier-bg-input)",
                color: "var(--nier-text)",
                fontFamily: "inherit",
                fontSize: 12,
                boxSizing: "border-box",
              }}
            />
          )}

          {/* Textarea */}
          <textarea
            value={g}
            onChange={(e) => update(idx, e.target.value)}
            disabled={busyIdx === idx}
            rows={4}
            style={{
              width: "100%",
              padding: 10,
              border: "1px solid var(--nier-border)",
              background: busyIdx === idx ? "var(--nier-bg-mid)" : "var(--nier-bg-field)",
              color: busyIdx === idx ? "var(--nier-text-dim)" : "var(--nier-text)",
              resize: "vertical",
              fontFamily: "inherit",
              fontSize: 14,
              boxSizing: "border-box",
              transition: "background 0.2s",
            }}
            placeholder={t.greetingPlaceholder || "Enter an alternate opening message..."}
          />
        </div>
      ))}

      <button
        className="nier-btn"
        onClick={add}
        style={{
          ...btnStyle,
          width: "100%",
          padding: "8px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 6,
          fontSize: 12,
        }}
      >
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
          <line x1="5.5" y1="1" x2="5.5" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          <line x1="1" y1="5.5" x2="10" y2="5.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
        {t.addGreeting || "Add Alternate Greeting"}
      </button>
    </div>
  );
}
