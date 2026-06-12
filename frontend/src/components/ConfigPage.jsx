import { useState, useEffect } from "react";

const DEFAULT_CHAR_TEMPLATE = `You are converting scraped fandom wiki data into a SillyTavern character card.

Rules:
- Do not invent facts not present in the source data.
- Keep the character canon-consistent.
- Rewrite for roleplay usefulness, not wiki style.
- Make personality behavioral, not just a list of adjectives.
- Keep first_mes short, natural, and in character.
- Do not write actions or dialogue for {{user}}.
- Output valid JSON only.

Source data:
{source_json}`;

const DEFAULT_FIELD_TEMPLATE = `You are rewriting a single field of a SillyTavern character card.

Field: {field_name}
Character: {char_name}
Custom instruction: {custom_instruction}

Source data:
{source_json}

Current card:
{card_json}

Output valid JSON only with the updated field.`;

const DEFAULT_LORE_TEMPLATE = `Generate SillyTavern lorebook entries from this wiki page.

Page: {title}
{content}

Create one entry per distinct entity. Include the main subject, each ability/skill separately, items, factions, locations, events.

Output: {"entries": [{"title":"...","entry_type":"...","keywords":["..."],"content":"..."}]}`;

export default function ConfigPage({ t = {}, showToast }) {
  const TABS = [
    { key: "character", label: t.characterGeneration || "Character Generation", templateKey: "character_generation_template", defaultVal: DEFAULT_CHAR_TEMPLATE,
      vars: ["{source_json}"], hint: "Available: {source_json} — the full scraped wiki data" },
    { key: "field", label: t.fieldRegeneration || "Field Regeneration", templateKey: "field_regeneration_template", defaultVal: DEFAULT_FIELD_TEMPLATE,
      vars: ["{field_name}", "{char_name}", "{custom_instruction}", "{source_json}", "{card_json}"],
      hint: "Available: {field_name}, {char_name}, {custom_instruction}, {source_json}, {card_json}" },
    { key: "lore", label: t.loreGeneration || "Lore Generation", templateKey: "lore_generation_template", defaultVal: DEFAULT_LORE_TEMPLATE,
      vars: ["{title}", "{content}"], hint: "Available: {title}, {content}" },
  ];
  const [activeTab, setActiveTab] = useState("character");
  const [templates, setTemplates] = useState({
    character_generation_template: "",
    field_regeneration_template: "",
    lore_generation_template: "",
    use_templates: false,
  });
  const [envKeys, setEnvKeys] = useState({
    NANOGPT_API_KEY: "",
    OPENROUTER_API_KEY: "",
    NANOGPT_MODEL: "",
    OPENROUTER_MODEL: "",
  });
  const [showKeys, setShowKeys] = useState({});
  const [saving, setSaving] = useState(false);
  const [savingEnv, setSavingEnv] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/config/prompts").then(r => r.json()).then(data => setTemplates(data)).catch(() => {});
    fetch("/api/config/env").then(r => r.json()).then(data => setEnvKeys(data)).catch(() => {});
  }, []);

  async function saveTemplates() {
    setSaving(true); setError("");
    try {
      const res = await fetch("/api/config/prompts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(templates),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      if (showToast) showToast("Templates saved");
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  async function saveEnv() {
    setSavingEnv(true); setError("");
    try {
      const res = await fetch("/api/config/env", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(envKeys),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      if (showToast) showToast("API keys saved");
    } catch (e) { setError(e.message); }
    finally { setSavingEnv(false); }
  }

  function insertVar(v) {
    const tab = TABS.find(t => t.key === activeTab);
    if (!tab) return;
    setTemplates(prev => ({
      ...prev,
      [tab.templateKey]: (prev[tab.templateKey] || "") + v,
    }));
  }

  const tab = TABS.find(t => t.key === activeTab);

  const inputStyle = {
    padding: "10px 12px",
    border: "1px solid var(--nier-border)",
    background: "var(--nier-bg-input)",
    color: "var(--nier-text)",
    fontFamily: "inherit",
    fontSize: 13,
    boxSizing: "border-box",
    width: "100%",
  };

  const btnStyle = {
    padding: "10px 16px",
    border: "1px solid var(--nier-border)",
    background: "var(--nier-bg-btn)",
    color: "var(--nier-text)",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: "0.06em",
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <h1 className="nier-title nier-heading" style={{ textAlign: "center", marginBottom: 4 }}>
        Config
      </h1>
      <p style={{ textAlign: "center", color: "var(--nier-text-dim)", marginBottom: 24, letterSpacing: "0.04em" }}>
        Prompt templates • API keys
      </p>

      {error && (
        <div style={{ color: "#c84a3a", border: "1px solid #c84a3a", padding: "10px 14px", marginBottom: 16, fontSize: 13 }}>
          ⊗ {error}
        </div>
      )}

      {/* ── Prompt Templates ─────────────────────────────── */}
      <section className="nier-panel nier-screen-panel" style={{
        border: "1px solid var(--nier-border)", background: "var(--nier-bg-panel)", padding: 20, marginBottom: 20,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 className="nier-heading" style={{ margin: 0, fontSize: 15 }}>Prompt Templates</h2>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13 }}>
            <span style={{
              width: 16, height: 16, border: "1.5px solid var(--nier-border)",
              background: templates.use_templates ? "var(--nier-btn-active-bg)" : "var(--nier-bg-field)",
              display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
            }}>
              {templates.use_templates && (
                <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                  <path d="M1 3.5L3.5 6.5L9 1" stroke="var(--nier-text-inv)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </span>
            <input type="checkbox" checked={templates.use_templates}
              onChange={e => setTemplates(p => ({ ...p, use_templates: e.target.checked }))}
              style={{ display: "none" }} />
            Use custom templates
          </label>
        </div>

        {/* Tab bar */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--nier-border)", marginBottom: 14, gap: 0 }}>
          {TABS.map(t => (
            <button key={t.key}
              className={activeTab === t.key ? "nier-btn nier-btn-active" : "nier-btn"}
              onClick={() => setActiveTab(t.key)}
              style={{ padding: "8px 14px", fontSize: 12, fontWeight: 700, border: "none",
                borderBottom: activeTab === t.key ? "2px solid var(--nier-text)" : "2px solid transparent",
                cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.06em" }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Hint + variable chips */}
        <div style={{ fontSize: 11, color: "var(--nier-text-dim)", marginBottom: 8 }}>
          {tab?.hint}
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
          {tab?.vars.map(v => (
            <button key={v} className="nier-btn" onClick={() => insertVar(v)}
              style={{ padding: "3px 10px", fontSize: 11, fontFamily: "monospace", border: "1px solid var(--nier-border)", cursor: "pointer" }}>
              {v}
            </button>
          ))}
          <button className="nier-btn" onClick={() => setTemplates(p => ({ ...p, [tab.templateKey]: tab.defaultVal }))}
            style={{ padding: "3px 10px", fontSize: 11, border: "1px solid var(--nier-border)", cursor: "pointer", marginLeft: "auto", color: "var(--nier-text-dim)" }}>
            Reset to default
          </button>
        </div>

        <textarea
          value={templates[tab?.templateKey] ?? ""}
          onChange={e => setTemplates(p => ({ ...p, [tab.templateKey]: e.target.value }))}
          rows={18}
          placeholder={`Paste your custom ${tab?.label.toLowerCase()} prompt here...\n\nLeave empty to use the built-in default.`}
          style={{ ...inputStyle, resize: "vertical" }}
        />

        <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
          <button className="nier-btn" onClick={saveTemplates} disabled={saving}
            style={{ ...btnStyle, opacity: saving ? 0.5 : 1, background: "var(--nier-btn-active-bg)", color: "var(--nier-text-inv)" }}>
            {saving ? (t.saving || "Saving...") : (t.saveTemplates || "Save Templates")}
          </button>
        </div>
      </section>

      {/* ── API Keys ─────────────────────────────────────── */}
      <section className="nier-panel nier-screen-panel" style={{
        border: "1px solid var(--nier-border)", background: "var(--nier-bg-panel)", padding: 20,
      }}>
        <h2 className="nier-heading" style={{ margin: "0 0 16px", fontSize: 15 }}>API Keys</h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          {[
            { key: "NANOGPT_API_KEY", label: t.nanogptKey || "NanoGPT API Key", placeholder: "sk-...", isKey: true },
            { key: "OPENROUTER_API_KEY", label: t.openrouterKey || "OpenRouter API Key", placeholder: "sk-or-...", isKey: true },
            { key: "NANOGPT_MODEL", label: t.nanogptModel || "Default NanoGPT Model", placeholder: "zai-org/glm-4.7:thinking", isKey: false },
            { key: "OPENROUTER_MODEL", label: t.openrouterModel || "Default OpenRouter Model", placeholder: "openai/gpt-4o-mini", isKey: false },
            { key: "LOCAL_OPENAI_BASE_URL", label: "Local Server Base URL", placeholder: "http://localhost:1234/v1", isKey: false },
            { key: "LOCAL_MODEL", label: "Local Model Name", placeholder: "local-model", isKey: false },
            { key: "LOCAL_API_KEY", label: "Local API Key (if required)", placeholder: "local", isKey: true },
          ].map(({ key, label, placeholder, isKey }) => (
            <label key={key} style={{ fontSize: 12, color: "var(--nier-text-dim)", display: "flex", flexDirection: "column", gap: 4 }}>
              {label}
              <div style={{ position: "relative" }}>
                <input
                  type={isKey && !showKeys[key] ? "password" : "text"}
                  value={envKeys[key] || ""}
                  onChange={e => setEnvKeys(p => ({ ...p, [key]: e.target.value }))}
                  placeholder={placeholder}
                  style={{ ...inputStyle, paddingRight: isKey ? 40 : undefined }}
                  autoComplete="off"
                />
                {isKey && (
                  <button onClick={() => setShowKeys(p => ({ ...p, [key]: !p[key] }))}
                    style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                      background: "none", border: "none", cursor: "pointer", color: "var(--nier-text-dim)", fontSize: 13 }}>
                    {showKeys[key] ? "◎" : "○"}
                  </button>
                )}
              </div>
            </label>
          ))}
        </div>

        <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end" }}>
          <button className="nier-btn" onClick={saveEnv} disabled={savingEnv}
            style={{ ...btnStyle, opacity: savingEnv ? 0.5 : 1, background: "var(--nier-btn-active-bg)", color: "var(--nier-text-inv)" }}>
            {savingEnv ? (t.saving || "Saving...") : (t.saveKeys || "Save Keys")}
          </button>
        </div>
      </section>
    </div>
  );
}
