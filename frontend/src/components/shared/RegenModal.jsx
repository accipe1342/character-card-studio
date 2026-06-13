/**
 * RegenModal.jsx — Field regeneration modal
 * ===========================================
 * A modal dialog that appears when regenerating a field or the
 * full card. Allows the user to enter a custom prompt that is
 * appended to the default generation prompt.
 *
 * PROPS
 * -----
 * open             Whether the modal is visible
 * onClose()        Called when the modal is dismissed
 * onConfirm(prompt) Called with the custom prompt string on confirm
 * fieldName        Name of the field being regenerated (for display)
 * t                Translation strings
 *
 * HOW TO EXTEND
 * -------------
 * - Add prompt presets: add a dropdown of common prompt modifiers
 *   (e.g. "Make it shorter", "Add more detail") that populate the
 *   text input when selected.
 * - Add history: show the last 3 custom prompts used for this field.
 */

export default function RegenModal({ value, onChange, onClose, onSubmit, t = {} }) {
  const fieldLabel =
    value.mode === "full"
      ? "Full Card"
      : value.mode === "structured"
        ? "Structured Profile"
        : value.fieldName.replaceAll("_", " ");

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        display: "grid",
        placeItems: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: "min(600px, 92vw)",
          background: "var(--signal-bg-panel)",
          border: "1px solid var(--signal-border)",
          padding: "24px 24px 20px",
          boxShadow: "4px 4px 0 rgba(0,0,0,0.18)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ marginBottom: 18 }}>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--signal-text-dim)",
              marginBottom: 4,
            }}
          >
            Regenerate
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "var(--signal-text)" }}>
            {fieldLabel}
          </div>
        </div>

        {/* Divider */}
        <div style={{ borderTop: "1px solid #c8c0ae", marginBottom: 18 }} />

        {/* Custom prompt */}
        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "#555",
              marginBottom: 6,
            }}
          >
            Custom prompt
          </div>
          <textarea
            value={value.customPrompt}
            onChange={(e) =>
              onChange((prev) => ({ ...prev, customPrompt: e.target.value }))
            }
            rows={4}
            placeholder="e.g. make this more dramatic, focus on combat style, be more concise..."
            style={{
              width: "100%",
              padding: "10px 12px",
              border: "1px solid var(--signal-border)",
              background: "var(--signal-bg-field)",
              color: "var(--signal-text)",
              resize: "vertical",
              fontFamily: "inherit",
              fontSize: 14,
              boxSizing: "border-box",
              maxHeight: 160,
              overflowY: "auto",
            }}
          />
        </div>

        {/* Checkboxes */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 22 }}>
          {[
            { key: "includeCurrentCard", label: t.includeCardContext || "Include current card context" },
            { key: "includeSource",      label: t.includeSourceContext || "Include source context" },
          ].map(({ key, label }) => (
            <label
              key={key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                cursor: "pointer",
                userSelect: "none",
                fontSize: 14,
                color: "var(--signal-text)",
              }}
            >
              {/* Custom checkbox */}
              <span
                style={{
                  width: 18,
                  height: 18,
                  flexShrink: 0,
                  border: "1.5px solid #3a3a3a",
                  background: value[key] ? "#2b2b2b" : "#f7f2e7",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "background 0.15s",
                }}
              >
                {value[key] && (
                  <svg width="11" height="9" viewBox="0 0 11 9" fill="none">
                    <path d="M1 4L4 7.5L10 1" stroke="#f5f1e8" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
              </span>
              <input
                type="checkbox"
                checked={value[key]}
                onChange={(e) =>
                  onChange((prev) => ({ ...prev, [key]: e.target.checked }))
                }
                style={{ display: "none" }}
              />
              {label}
            </label>
          ))}
        </div>

        {/* Buttons */}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            onClick={onClose}
            style={{
              padding: "9px 16px",
              border: "1px solid var(--signal-border)",
              background: "var(--signal-bg-btn)",
              color: "var(--signal-text)",
              cursor: "pointer",
              fontFamily: "inherit",
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            Cancel
          </button>
          <button
            onClick={onSubmit}
            style={{
              padding: "9px 16px",
              border: "1px solid var(--signal-border)",
              background: "var(--signal-btn-active-bg)",
              color: "var(--signal-text-inv)",
              cursor: "pointer",
              fontFamily: "inherit",
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            Regenerate
          </button>
        </div>
      </div>
    </div>
  );
}
