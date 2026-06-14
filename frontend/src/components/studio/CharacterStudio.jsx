/**
 * CharacterStudio.jsx — Character card editor
 * =============================================
 * The main character card creation and editing interface.
 * Manages the full lifecycle: scrape → generate → edit → save → export.
 *
 * LAYOUT
 * ------
 * Left column:   URL input, action buttons, job status, batch generate
 * Middle column: Field editor (Natural view) or structured profile grid
 * Right column:  Preview panel (image + card preview + export PNG)
 *
 * STATE
 * -----
 * url             Wiki URL to scrape
 * source          Scraped source object returned by the scrape job
 * sourceId        DB id of the saved source
 * card            The current card object being edited
 * cardId          DB id of the saved card (null if not yet saved)
 * characterViewMode  "natural" | "structured"
 * selectedField   Which natural-view field is currently active
 *                 ("description" | "personality" | "scenario" |
 *                  "first_mes" | "mes_example")
 * provider        "nanogpt" | "openrouter" | "local"
 * model           Model ID string
 * loading         True while any job is running
 * mainJob         Current job object from GET /api/job/:id
 * error           Error string (displayed in UI)
 * fieldBusy       Field name currently being regenerated (or null)
 * batchMode       Whether batch generate UI is expanded
 * batchUrls       Array of URLs for batch generation
 * batchResults    Results from the last batch job
 * glitchActive    Triggers one-shot glitch animation (unused currently)
 * typingField     Field name currently being typed into by animation
 * typingText      Current partial text during typing animation
 * flashSave       True briefly after save to trigger flash animation
 *
 * KEY HANDLERS
 * ------------
 * handleScrape()          Starts a scrape job for the current URL
 * handleGenerate()        Starts a card generation job from scraped source
 * handleBatchGenerate()   Starts batch generation from batchUrls
 * handleSaveCard()        Saves current card to DB, triggers flash
 * handleExportCard()      Exports card JSON (natural or structured)
 * handleRegenerateField() Regenerates a single field with optional prompt
 * loadModels(provider)    Fetches model list for the current provider
 *
 * PROPS
 * -----
 * card, setCard, cardId, setCardId   Lifted to App.jsx for library sync
 * imageFile, setImageFile            Card image file object
 * imageUrl, setImageUrl              Card image preview URL
 * t                                  Translation strings from i18n.js
 * showToast(msg)                     App-level toast notification
 *
 * HOW TO EXTEND
 * -------------
 * - Add a new action button: add to the "Row 2: actions" div and write
 *   a handler function above the return statement.
 * - Add a new natural-view field: add to the FIELDS array and add the
 *   key to DEFAULT_STRUCTURED_PROFILE in database.py.
 * - Add a new structured field: add to the structured profile grid
 *   section and update preview.py and database.py.
 * - Change generation behaviour: edit handleGenerate() which calls
 *   startCharacterGenerate() from api.js.
 */

import React, { useEffect, useState, useRef, useCallback } from "react";
import CheatsheetBar from "../shared/CheatsheetBar";
import AlternateGreetings from "../shared/AlternateGreetings";
import PreviewPanel from "../shared/PreviewPanel";
import SourcePanel from "../shared/SourcePanel";
import RegenModal from "../shared/RegenModal";
import MainJobStatus from "../shared/MainJobStatus";
import {
  getJob,
  regenerateField,
  regenerateFullCard,
  saveCard,
  startCharacterGenerate,
  startBatchGenerate,
  startScrape,
  newBlankCard,
  fetchModels,
  getImageProxyUrl,
} from "../../lib/api";

export default function CharacterStudio({
  t = {},
  showToast,
  imageFile,
  setImageFile,
  imageUrl,
  setImageUrl,
  url,
  setUrl,
  source,
  setSource,
  sourceId,
  setSourceId,
  card,
  setCard,
  cardId,
  setCardId,
  characterViewMode,
  setCharacterViewMode,
  selectedField,
  setSelectedField,
  customPrompt,
  setCustomPrompt,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mainJob, setMainJob] = useState(null);
  const [provider, setProvider] = useState("nanogpt");
  const [model, setModel] = useState("");
  const [modelList, setModelList] = useState([]);
  const [modelSearch, setModelSearch] = useState("");
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(false);
  const modelRef = useRef(null);
  const textareaRef = useRef(null);

  const [fieldBusy, setFieldBusy] = useState(null);
  const [fieldElapsed, setFieldElapsed] = useState(0);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const [glitchActive, setGlitchActive] = useState(false);
  const [typingField, setTypingField] = useState(null);
  const [typingText, setTypingText] = useState("");
  const [flashSave, setFlashSave] = useState(false);
  const [batchUrls, setBatchUrls] = useState(["", ""]);
  const [batchResults, setBatchResults] = useState(null);
  // Fields that live at card top-level, not in structured_profile
  const NATURAL_FIELDS = new Set(["description","personality","scenario","first_mes","mes_example","tags"]);

  function countTokens(text) {
    if (!text) return 0;
    const str = Array.isArray(text) ? text.join(" ") : String(text);
    const words = str.trim().split(/\s+/).filter(Boolean);
    let t = 0;
    for (const w of words) t += 1 + Math.floor(Math.max(0, w.length - 4) / 4);
    return t;
  }

  const totalCardTokens = React.useMemo(() => {
    if (!card) return 0;
    const naturalFields = ["description", "personality", "scenario", "first_mes", "mes_example"];
    const spFields = card.structured_profile ? Object.values(card.structured_profile) : [];
    const naturalText = naturalFields.map(f => card[f] || "").join(" ");
    const spText = spFields.map(v => Array.isArray(v) ? v.join(" ") : String(v || "")).join(" ");
    return countTokens(naturalText + " " + spText);
  }, [card]);

  const [regenModal, setRegenModal] = useState({
    open: false,
    fieldName: "",
    mode: "field",
    customPrompt: "",
    includeCurrentCard: true,
    includeSource: true,
  });



  // Close model dropdown when clicking outside
  useEffect(() => {
    function handleClick(e) {
      if (modelRef.current && !modelRef.current.contains(e.target)) {
        setModelDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  async function loadModels(prov) {
    setModelsLoading(true);
    setModelList([]);
    try {
      const models = await fetchModels(prov);
      setModelList(models);
    } catch (e) {
      console.error("Failed to load models:", e);
    } finally {
      setModelsLoading(false);
    }
  }

  function openRegenModal(fieldName, mode = "field") {
    setRegenModal({
      open: true,
      fieldName,
      mode,
      customPrompt: customPrompt || "",
      includeCurrentCard: true,
      includeSource: true,
    });
  }

  function closeRegenModal() {
    setRegenModal((prev) => ({ ...prev, open: false }));
  }

  function handleImageChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    const objectUrl = URL.createObjectURL(file);
    setImageFile(file);
    setImageUrl(objectUrl);
  }

  async function pollJob(jobId, onDone) {
    const interval = setInterval(async () => {
      try {
        const data = await getJob(jobId);
        setMainJob(data);

        if (data.status === "done") {
          clearInterval(interval);
          onDone?.(data);
          setLoading(false);
        }

        if (data.status === "failed") {
          clearInterval(interval);
          setError(data.error || data.message || "Job failed");
          setLoading(false);
        }
      } catch (err) {
        clearInterval(interval);
        setError(err.message);
        setLoading(false);
      }
    }, 800);
  }

  async function handleScrape() {
    try {
      setLoading(true);
      setError("");
      setCard(null);
      setCardId(null);
      setMainJob(null);

      const data = await startScrape(url);

      pollJob(data.job_id, (jobData) => {
        const src = jobData.result.source;
        setSource(src);
        setSourceId(jobData.result.source_id);
        // Auto-fill image from infobox if no image set yet
        const infoboxImg = src?.normalized?.infobox_image;
        if (infoboxImg && !imageFile) {
          setImageUrl(getImageProxyUrl(infoboxImg));
        }
      });
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  async function handleGenerate() {
    if (!sourceId) return;

    try {
      setLoading(true);
      setError("");
      setMainJob(null);

      const data = await startCharacterGenerate(sourceId, provider, model);

      pollJob(data.job_id, (jobData) => {
        const generatedCard = jobData.result.card;
        // Merge sex -> gender if gender is missing
        if (generatedCard.structured_profile && !generatedCard.structured_profile.gender && generatedCard.structured_profile.sex) {
          generatedCard.structured_profile.gender = generatedCard.structured_profile.sex;
        }
        setCard(generatedCard);
        setCardId(jobData.result.card_id);

      });
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  // Field regen timer
  useEffect(() => {
    if (!fieldBusy) { setFieldElapsed(0); return; }
    setFieldElapsed(0);
    const id = setInterval(() => setFieldElapsed(s => s + 1), 1000);
    return () => clearInterval(id);
  }, [fieldBusy]);

  async function handleNewCard() {
    try {
      setError("");
      setLoading(false);
      setMainJob(null);
      setSource(null);
      setSourceId(null);
      setUrl("");
      setImageFile(null);
      setImageUrl(null);
      setBatchMode(false);
      setBatchResults(null);
      const data = await newBlankCard();
      setCard(data.card);
      setCardId(data.card_id);
      setSourceId(data.source_id);

    } catch (err) {
      setError(err.message);
    }
  }

  async function handleBatchGenerate() {
    const urls = batchUrls.filter(u => u.trim());
    if (!urls.length) return;
    try {
      setLoading(true);
      setError("");
      setMainJob(null);
      setBatchResults(null);
      const data = await startBatchGenerate(urls, provider, model);
      pollJob(data.job_id, (jobData) => {
        setBatchResults(jobData.result);
        setBatchMode(false);
      });
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  async function handleSaveCard() {
    if (!card || !cardId) return;
    try {
      setError("");
      await saveCard(cardId, card);
      if (showToast) showToast(t.savedOk || "Card saved");
      // Flash animation
      setFlashSave(false);
      setTimeout(() => setFlashSave(true), 50);
      setTimeout(() => setFlashSave(false), 900);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRegenerateFullCard() {
    if (!cardId) return;

    try {
      setLoading(true);
      setError("");
      setMainJob({
        status: "running",
        stage: "regenerating_full_card",
        progress: 25,
        message: "Regenerating full card...",
      });

      const data = await regenerateFullCard(cardId);

      setCard(data.card);
      setCardId(data.card_id);
      setMainJob({
        status: "done",
        stage: "done",
        progress: 100,
        message: "Full card regeneration complete.",
      });
    } catch (err) {
      setError(err.message);
      setMainJob({
        status: "failed",
        stage: "failed",
        progress: 100,
        message: err.message,
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleRegenerateField(fieldName, options = {}) {
    if (!cardId) return;

    try {
      setError("");
      setFieldBusy(fieldName);

      const data = await regenerateField(cardId, fieldName, options);

      if (characterViewMode === "structured") {
        const nextValue =
          data.result?.structured_profile?.[fieldName] ??
          data.result?.[fieldName] ??
          data.new_value ??
          "";

        setCard((prev) => ({
          ...prev,
          structured_profile: {
            ...(prev?.structured_profile || {}),
            [fieldName]: nextValue,
          },
        }));
      } else {
        const nextValue = data.result?.[fieldName] ?? data.new_value ?? "";
        // Typing animation for text fields
        if (typeof nextValue === "string" && nextValue.length > 0) {
          setTypingField(fieldName);
          setTypingText("");
          let i = 0;
          const speed = Math.max(8, Math.min(25, Math.floor(3000 / nextValue.length)));
          const iv = setInterval(() => {
            i++;
            setTypingText(nextValue.slice(0, i));
            if (i >= nextValue.length) {
              clearInterval(iv);
              setTypingField(null);
              setCard((prev) => ({ ...prev, [fieldName]: nextValue }));
            }
          }, speed);
        } else {
          setCard((prev) => ({ ...prev, [fieldName]: nextValue }));
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setFieldBusy(null);
    }
  }

  async function submitRegenModal() {
    setCustomPrompt(regenModal.customPrompt);

    const options = {
      customPrompt: regenModal.customPrompt,
      includeCurrentCard: regenModal.includeCurrentCard,
      includeSource: regenModal.includeSource,
    };

    const { mode, fieldName } = regenModal;
    closeRegenModal();

    if (mode === "full") {
      await handleRegenerateFullCard();
      return;
    }

    await handleRegenerateField(fieldName, options);
  }

  function updateCardField(field, value) {
    setCard((prev) => ({ ...prev, [field]: value }));
  }
  function updateStructuredField(field, value) {
    const isListField = [
      "appearance",
      "non_human_appearance",
      "personal_parts",
      "clothing",
      "accessories",
      "speech",
      "personality_traits",
      "kinks",
      "likes",
      "dislikes",
      "loves",
      "hates",
    ].includes(field);

    setCard((prev) => ({
      ...prev,
      structured_profile: {
        ...(prev?.structured_profile || {}),
        [field]: isListField
          ? value
              .split("\n")
              .map((x) => x.trim())
              .filter(Boolean)
          : value,
      },
    }));
  }

  function updateAlternateGreetings(greetings) {
    setCard((prev) => ({ ...prev, alternate_greetings: greetings }));
  }

  function handleExportStructured() {
    if (!card?.structured_profile) return;

    const blob = new Blob([JSON.stringify(card.structured_profile, null, 2)], {
      type: "application/json",
    });

    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = `${card.name || "card"}_structured_profile.json`;
    a.click();
    URL.revokeObjectURL(objectUrl);
  }

  function handleExportCard() {
    if (!card) return;

    // Export structured profile JSON if structured view is active, otherwise full card
    const isStructured = characterViewMode === "structured";
    const data = isStructured ? card.structured_profile : card;
    const filename = isStructured
      ? `${card.name || "card"}_structured_profile.json`
      : `${card.name || "card"}.json`;

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <>
      <h1 className="signal-title signal-heading" style={{ marginTop: 0, marginBottom: 4, display: 'block', textAlign: 'center' }}>Character Card Studio</h1>
      <p style={{ color: "var(--signal-text-dim)" }}>
        {t.subtitle || "Preview image • Source data • Editable card"}
      </p>

      {/* Row 1: inputs */}
      <div
        style={{
          display: "flex",
          gap: 12,
          marginBottom: 8,
          flexWrap: "wrap",
        }}
      >
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste a wiki URL"
          style={{
            flex: "1 1 260px",
            minWidth: 0,
            padding: 12,
            border: "1px solid var(--signal-border)",
            background: "var(--signal-bg-field)",
            color: "var(--signal-text)",
          }}
        />

        <select
          value={provider}
          onChange={(e) => {
            setProvider(e.target.value);
            setModel("");
            setModelSearch("");
            setModelList([]);
          }}
          style={inputStyle}
        >
          <option value="nanogpt">NanoGPT</option>
          <option value="openrouter">OpenRouter</option>
          <option value="local">Local (OpenAI-compatible)</option>
        </select>

        {/* Model picker — Signal UI style */}
        <div ref={modelRef} style={{ position: "relative", minWidth: 260 }}>
          {/* Trigger input */}
          <div style={{
            display: "flex",
            border: "1px solid var(--signal-border)",
            background: "var(--signal-bg-field)",
          }}>
            <input
              value={modelDropdownOpen ? modelSearch : (model || "")}
              onChange={(e) => { setModelSearch(e.target.value); setModel(e.target.value); }}
              onFocus={() => { setModelDropdownOpen(true); setModelSearch(model || ""); }}
              placeholder={t.modelOptional || "Model (optional)"}
              style={{
                flex: 1, padding: "12px 10px", border: "none",
                background: "transparent", color: "var(--signal-text)",
                fontFamily: "inherit", fontSize: "inherit",
                outline: "none", minWidth: 0,
              }}
            />
            <button
              onClick={() => {
                if (modelDropdownOpen) { setModelDropdownOpen(false); }
                else { setModelDropdownOpen(true); }
              }}
              style={{
                padding: "0 12px", border: "none",
                borderLeft: "1px solid var(--signal-border)",
                background: "var(--signal-bg-panel)", cursor: "pointer",
                color: "var(--signal-text)", fontSize: 12,
              }}
            >
              {modelDropdownOpen ? "▴" : "▾"}
            </button>
          </div>

          {modelDropdownOpen && (
            <div style={{
              position: "absolute", top: "100%", left: 0, right: 0,
              background: "var(--signal-bg-panel)", border: "1px solid var(--signal-border)",
              borderTop: "none", zIndex: 500,
              display: "flex", flexDirection: "column",
              maxHeight: 340,
            }}>
              {/* Search bar */}
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "8px 12px", borderBottom: "1px solid var(--signal-border)",
                background: "var(--signal-bg-mid)",
              }}>
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                  <circle cx="5.5" cy="5.5" r="4.5" stroke="#888" strokeWidth="1.2"/>
                  <line x1="9" y1="9" x2="12" y2="12" stroke="#888" strokeWidth="1.2" strokeLinecap="round"/>
                </svg>
                <input
                  autoFocus
                  value={modelSearch}
                  onChange={(e) => setModelSearch(e.target.value)}
                  placeholder="Search models..."
                  style={{
                    flex: 1, border: "none", background: "transparent",
                    color: "var(--signal-text)", fontFamily: "inherit", fontSize: 13,
                    outline: "none",
                  }}
                />
              </div>

              {/* Fetch button */}
              <button
                onClick={() => loadModels(provider)}
                disabled={modelsLoading}
                className={modelsLoading ? "signal-fetch-btn signal-fetch-btn-loading" : "signal-fetch-btn"}
                style={{
                  margin: "8px 10px 4px",
                  padding: "8px 12px",
                  border: "1px solid var(--signal-border)",
                  cursor: modelsLoading ? "not-allowed" : "pointer",
                  fontFamily: "inherit",
                  fontSize: 12,
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                }}
              >
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                  <circle cx="6.5" cy="6.5" r="5.5" stroke="currentColor" strokeWidth="1"/>
                  <circle cx="6.5" cy="6.5" r="2.5" stroke="currentColor" strokeWidth="1"/>
                  <circle cx="6.5" cy="6.5" r="0.8" fill="currentColor"/>
                  <line x1="1" y1="6.5" x2="4" y2="6.5" stroke="currentColor" strokeWidth="1"/>
                  <line x1="9" y1="6.5" x2="12" y2="6.5" stroke="currentColor" strokeWidth="1"/>
                </svg>
                {modelsLoading ? "SCANNING…" : "FETCH MODELS FROM API"}
              </button>

              {/* Model count */}
              {modelList.length > 0 && (
                <div style={{
                  padding: "3px 12px 6px",
                  fontSize: 11, color: "var(--signal-text-dim)",
                  letterSpacing: "0.06em",
                }}>
                  {modelList.length} {provider === "openrouter" ? "OpenRouter" : provider === "nanogpt" ? "NanoGPT" : "local"} models
                </div>
              )}

              {/* Model list */}
              <div style={{ overflowY: "auto", flex: 1 }}>
                {!modelsLoading && modelList.length === 0 && (
                  <div style={{ padding: "12px", color: "var(--signal-text-dim)", fontSize: 13, textAlign: "center" }}>
                    Press FETCH MODELS to load
                  </div>
                )}
                {modelList
                  .filter((m) =>
                    !modelSearch ||
                    m.id.toLowerCase().includes(modelSearch.toLowerCase()) ||
                    m.name.toLowerCase().includes(modelSearch.toLowerCase())
                  )
                  .map((m) => (
                    <div
                      key={m.id}
                      onClick={() => { setModel(m.id); setModelSearch(""); setModelDropdownOpen(false); }}
                      style={{
                        padding: "9px 12px",
                        cursor: "pointer",
                        borderBottom: "1px solid var(--signal-border)",
                        background: model === m.id ? "var(--signal-btn-active-bg)" : "transparent",
                        color: model === m.id ? "var(--signal-btn-active-text)" : "var(--signal-text)",
                      }}
                      onMouseEnter={(e) => { if (model !== m.id) e.currentTarget.style.background = "var(--signal-bg-mid)"; }}
                      onMouseLeave={(e) => { if (model !== m.id) e.currentTarget.style.background = "transparent"; }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600 }}>
                        {m.name}
                      </div>
                      <div style={{ fontSize: 10, opacity: 0.55, marginTop: 2, display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <span>{m.id}</span>
                        {m.context && <span>{(m.context / 1000).toFixed(0)}k ctx</span>}
                        {m.per_token && <span>${(parseFloat(m.per_token) * 1_000_000).toFixed(2)}/1M tok</span>}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>

      </div>

      {/* Row 2: actions */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <button onClick={handleNewCard} className="signal-btn" style={buttonStyle}>
          {t.newCard || "New Card"}
        </button>

        <button onClick={handleScrape} disabled={loading} className="signal-btn" style={buttonStyle}>
          {loading ? (t.working || "Working...") : (t.scrape || "Scrape")}
        </button>

        <button
          onClick={() => setSourceOpen(true)}
          disabled={!source}
          className="signal-btn"
          style={buttonStyle}
        >
          {t.viewSource || "View Source"}
        </button>

        <button
          onClick={handleGenerate}
          disabled={loading || !sourceId}
          className="signal-btn"
          style={buttonStyle}
        >
          {t.generateCard || "Generate Card"}
        </button>

        <button
          className="signal-btn"
          onClick={() => { setBatchMode(b => !b); setBatchResults(null); }}
          style={buttonStyle}
        >
          {batchMode ? (t.cancelBatch || "Cancel Batch") : (t.batchGenerate || "Batch Generate")}
        </button>

        <button onClick={handleExportCard} disabled={!card} className="signal-btn" style={buttonStyle}>
          {characterViewMode === "structured"
            ? (t.exportStructuredJson || "Export Structured JSON")
            : (t.exportCardJson || "Export Card JSON")}
        </button>
      </div>

      {batchMode && (
        <div style={{
          border: "1px solid var(--signal-border)",
          background: "var(--signal-bg-panel)",
          padding: 14,
          marginBottom: 16,
        }}>
          <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 10, letterSpacing: "0.08em" }}>
            {t.batchTitle || ":: BATCH CHARACTER GENERATION"}
          </div>
          <div style={{ fontSize: 12, color: "var(--signal-text-dim)", marginBottom: 10 }}>
            {t.batchHint || "Paste up to 10 wiki URLs — each will be scraped and generated as a separate card."}
          </div>
          {batchUrls.map((u, i) => (
            <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
              <input
                value={u}
                onChange={e => { const n = [...batchUrls]; n[i] = e.target.value; setBatchUrls(n); }}
                placeholder={`https://...fandom.com/wiki/Character${i + 1}`}
                style={{
                  flex: 1, padding: "7px 10px",
                  border: "1px solid var(--signal-border)",
                  background: "var(--signal-bg-field)",
                  color: "var(--signal-text)",
                  fontFamily: "inherit", fontSize: 13,
                }}
              />
              {batchUrls.length > 2 && (
                <button
                  className="signal-btn"
                  onClick={() => setBatchUrls(prev => prev.filter((_, idx) => idx !== i))}
                  style={{ ...buttonStyle, color: "#c84a3a", borderColor: "#c84a3a", padding: "7px 10px" }}
                >✕</button>
              )}
            </div>
          ))}
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            {batchUrls.length < 10 && (
              <button className="signal-btn" onClick={() => setBatchUrls(p => [...p, ""])} style={{ ...buttonStyle, fontSize: 12 }}>
                + Add URL
              </button>
            )}
            <button
              className="signal-btn"
              onClick={handleBatchGenerate}
              disabled={loading || batchUrls.filter(u => u.trim()).length === 0}
              style={{ ...buttonStyle, fontWeight: 700 }}
            >
              {loading ? "Generating..." : `Generate ${batchUrls.filter(u => u.trim()).length} Card(s)`}
            </button>
          </div>
        </div>
      )}

      {batchResults && (
        <div style={{
          border: "1px solid var(--signal-border)",
          background: "var(--signal-bg-panel)",
          padding: 14,
          marginBottom: 16,
        }}>
          <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8, letterSpacing: "0.08em" }}>
            :: BATCH RESULTS
          </div>
          {batchResults.cards?.map((c, i) => (
            <div key={i} style={{ fontSize: 13, marginBottom: 4, color: "var(--signal-text)" }}>
              ✓ {c.name || "Unnamed"} — <span style={{ opacity: 0.6, fontSize: 11 }}>{c.url}</span>
            </div>
          ))}
          {batchResults.errors?.map((e, i) => (
            <div key={i} style={{ fontSize: 12, marginBottom: 4, color: "#c84a3a" }}>
              ✗ {e.url} — {e.error}
            </div>
          ))}
          <div style={{ fontSize: 12, marginTop: 8, color: "var(--signal-text-dim)" }}>
            Cards saved to library. Open Library to load them.
          </div>
        </div>
      )}

      {error && mainJob?.status !== "failed" ? (
        <div
          style={{
            border: "1px solid #7f1d1d",
            background: "var(--signal-bg-panel)",
            color: "#7f1d1d",
            padding: 10,
            marginBottom: 12,
          }}
        >
          {error}
        </div>
      ) : null}

      <MainJobStatus job={mainJob} />

      <div
        className="signal-main-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(220px, 0.9fr) minmax(0, 1.8fr)",
          flexWrap: "wrap",
          gap: 16,
          alignItems: "start",
        }}
      >
        <div className="signal-sticky-panel" style={{ position: "sticky", top: 16, alignSelf: "start" }}>
          <PreviewPanel
            imageFile={imageFile}
            imageUrl={imageUrl}
            onImageChange={handleImageChange}
            card={card}
            viewMode={characterViewMode}
            t={t}
          />
        </div>

        {sourceOpen && (
          <div
            onClick={() => setSourceOpen(false)}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.35)",
              display: "grid",
              placeItems: "center",
              zIndex: 1000,
              backdropFilter: "blur(2px)",
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                width: "min(900px, 92vw)",
                maxHeight: "82vh",
                overflow: "auto",
                background: "rgba(239, 232, 216, 0.97)",
                border: "1px solid var(--signal-border)",
                borderRadius: 18,
                padding: 18,
                boxShadow: "0 20px 60px rgba(0,0,0,0.18)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 12,
                }}
              >
                <h2 style={{ margin: 0 }}>Source</h2>
                <button
                  style={buttonStyle}
                  onClick={() => setSourceOpen(false)}
                >
                  Close
                </button>
              </div>

              <SourcePanel source={source} />
            </div>
          </div>
        )}

        <section
          className="signal-panel signal-panel-delay-1"
          style={{
            border: "1px solid var(--signal-border)",
            background: "var(--signal-bg-panel)",
            padding: 14,

          }}
        >
          <h2 className="signal-heading" style={{ marginTop: 0 }}>{t.characterSystem || "Character System"}</h2>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <button
              className={characterViewMode === "natural" ? "signal-btn signal-btn-active" : "signal-btn"}
              style={{ ...buttonStyle }}
              onClick={() => setCharacterViewMode("natural")}
            >
              {t.natural || "Natural"}
            </button>

            <button
              className={characterViewMode === "structured" ? "signal-btn signal-btn-active" : "signal-btn"}
              style={{ ...buttonStyle }}
              onClick={() => setCharacterViewMode("structured")}
            >
              {t.structured || "Structured"}
            </button>
          </div>
          {!card ? (
            <div style={{ color: "var(--signal-text-dim)" }}>Generate a card to begin.</div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(160px, 0.9fr) minmax(0, 1.7fr)",
              // signal-character-grid applied below
                gap: 12,
                alignItems: "start",
              }}
            >
              <div
                style={{
                  border: "1px solid var(--signal-border)",
                  background: "var(--signal-bg-field)",
                  padding: 10,
                }}
              >
                <button
                  style={{ ...buttonStyle, width: "100%", marginBottom: 10 }}
                  onClick={() => openRegenModal("", "full")}
                >
                  {t.regenerateFullCard || "Regenerate Full Card"}
                </button>

                {/* Progress badge — shows fields for current tab only, excludes optional fields */}
                {(() => {
                  const sp = card?.structured_profile || {};

                  const naturalFields = ["description", "personality", "scenario", "first_mes", "mes_example", "tags"];
                  const structuredFields = [
                    "age", "gender", "pronouns", "ethnicity", "race", "sexual_attraction",
                    "job_occupation", "relationship_to_user", "relationship_status",
                    "appearance", "height", "weight", "clothing", "accessories",
                    "non_human_appearance", "personal_parts",
                    "personality_traits", "speech", "backstory",
                    "likes", "dislikes", "loves", "hates", "kinks", "tags",
                  ];

                  const allFields = characterViewMode === "natural" ? naturalFields : structuredFields;

                  const blank = allFields.filter(f => {
                    const v = NATURAL_FIELDS.has(f) ? card?.[f] : sp[f];
                    if (f === "tags") return !v || !Array.isArray(v) || v.length < 10;
                    return !v || (Array.isArray(v) ? v.length === 0 : String(v).trim() === "");
                  });

                  const total = allFields.length;
                  const filled = total - blank.length;
                  const pct = Math.round((filled / total) * 100);
                  const color = pct === 100 ? "var(--signal-ok, #4caf50)"
                    : pct >= 60 ? "var(--signal-warn, #ff9800)"
                    : "var(--signal-err, #f44336)";

                  return (
                    <div style={{ marginBottom: 10 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                        <span style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--signal-text-dim)" }}>
                          {characterViewMode === "natural" ? "NATURAL FIELDS" : "STRUCTURED FIELDS"}
                        </span>
                        <span style={{ fontSize: 11, fontWeight: 700, color }}>
                          {filled}/{total}
                        </span>
                      </div>
                      <div style={{ height: 3, background: "var(--signal-bg-field)", borderRadius: 2 }}>
                        <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 2, transition: "width 0.4s ease" }} />
                      </div>
                      {blank.length > 0 && (
                        <div style={{ marginTop: 5, fontSize: 10, color: "var(--signal-text-dim)", lineHeight: 1.6 }}>
                          {blank.map(f => (t.fields?.[f] || f.replaceAll("_", " "))).join(" · ")}
                        </div>
                      )}
                    </div>
                  );
                })()}

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      characterViewMode === "structured" ? "1fr 1fr" : "1fr",
                    gap: 6,
                  }}
                >
                  {(characterViewMode === "natural"
                    ? [
                        "description",
                        "personality",
                        "scenario",
                        "first_mes",
                        "mes_example",
                        "tags",
                      ]
                    : [
                        // ── Identity ──
                        "age",
                        "gender",
                        "pronouns",
                        "ethnicity",
                        "race",
                        // ── Role & Relationship ──
                        "job_occupation",
                        "relationship_to_user",
                        "relationship_status",
                        "sexual_attraction",
                        // ── Physical ──
                        "appearance",
                        "height",
                        "weight",
                        "clothing",
                        "accessories",
                        "non_human_appearance",
                        "personal_parts",
                        // ── Character ──
                        "personality_traits",
                        "speech",
                        "backstory",
                        "likes",
                        "dislikes",
                        "loves",
                        "hates",
                        "kinks",
                        // ── Card fields ──
                        "scenario",
                        "first_mes",
                        "mes_example",
                        "tags",
                      ]
                  ).map((field, idx) => (
                    <React.Fragment key={field}>
                      {/* Divider before natural fields in structured view */}

                      {characterViewMode === "structured" && field === "scenario" && (
                        <div style={{ gridColumn: "1 / -1", margin: "6px 0 2px" }} className="signal-divider">
                          <div className="signal-divider-mark signal-divider-mark-left" />
                          <div className="signal-divider-bar" />
                          <span className="signal-divider-label">{t.cardFields || "Card fields"}</span>
                          <div className="signal-divider-bar" />
                          <div className="signal-divider-mark signal-divider-mark-right" />
                        </div>
                      )}
                      <button
                        type="button"
                        className={selectedField === field ? "signal-btn signal-btn-active signal-field-active signal-list-item" : "signal-btn signal-list-item"}
                        style={{
                          animationDelay: `${idx * 35}ms`,
                          padding: "10px 8px",
                          cursor: "pointer",
                          textAlign: "left",
                          fontSize: 14,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 6,
                        }}
                        onClick={() => setSelectedField(field)}
                      >
                        <span>▸ {(t.fields && t.fields[field]) || field.replaceAll("_", " ")}</span>
                        {(() => {
                          const v = NATURAL_FIELDS.has(field) ? card?.[field] : card?.structured_profile?.[field];
                          const isEmpty = !v || (Array.isArray(v) ? v.length === 0 : String(v).trim() === "");
                          return isEmpty ? (
                            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--signal-text-dim)", opacity: 0.4, flexShrink: 0 }} />
                          ) : null;
                        })()}
                      </button>
                    </React.Fragment>
                  ))}
                </div>
              </div>

              <div
                className={`signal-screen-panel signal-corners-all${flashSave ? " signal-field-flash" : ""}`}
                style={{
                  border: "1px solid var(--signal-border)",
                  background: "var(--signal-bg-field)",
                  padding: 12,
                  position: "sticky",
                  top: 16,
                  alignSelf: "start",
                }}
              >
                <input
                  value={card.name || ""}
                  onChange={(e) => updateCardField("name", e.target.value)}
                  onBlur={async (e) => {
                    const newName = e.target.value.trim();
                    if (newName && cardId) {
                      try { await renameCard(cardId, newName); } catch {}
                    }
                  }}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "center",
                    fontWeight: 700,
                    fontSize: 18,
                    marginBottom: 10,
                    border: "none",
                    borderBottom: "1px solid var(--signal-border)",
                    background: "transparent",
                    color: "var(--signal-text)",
                    fontFamily: "inherit",
                    outline: "none",
                    padding: "2px 0 6px",
                    boxSizing: "border-box",
                  }}
                />

                <div
                  style={{
                    borderBottom: "1px solid var(--signal-border)",
                    paddingBottom: 6,
                    marginBottom: 12,
                    textAlign: "center",
                  }}
                >
                  {(() => {
                    const label = ((t.fields && t.fields[selectedField]) || selectedField.replaceAll("_", " ")).toUpperCase();
                    return (
                      <span
                        className="signal-field-label-active signal-glitch-label"
                        data-text={label}
                      >
                        {label}
                      </span>
                    );
                  })()}
                </div>

                {/* Loading bar shown while this field is regenerating */}
                {fieldBusy === selectedField && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 12, color: "var(--signal-text-dim)", marginBottom: 5, textAlign: "center", letterSpacing: "0.08em", display: "flex", justifyContent: "center", alignItems: "center", gap: 8 }}>
                      <span>Regenerating…</span>
                      <span style={{ opacity: 0.4 }}>·</span>
                      <span style={{ fontVariantNumeric: "tabular-nums" }}>{fieldElapsed}s</span>
                    </div>
                    <div style={{ width: "100%", height: 6, background: "var(--signal-bg-field)", overflow: "hidden", position: "relative" }}>
                      <FieldLoadingBar />
                    </div>
                  </div>
                )}

                {characterViewMode === "natural" ? (
                  <>
                    <CheatsheetBar
                      textareaRef={textareaRef}
                      t={t}
                      totalTokens={totalCardTokens}
                      value={card[selectedField] ?? ""}
                      onChange={(val) => updateCardField(selectedField, val)}
                    />
                    <textarea
                      ref={textareaRef}
                      value={typingField === selectedField ? typingText : (card[selectedField] ?? "")}
                      onChange={(e) => updateCardField(selectedField, e.target.value)}
                      rows={16}
                      disabled={fieldBusy === selectedField || typingField === selectedField}
                      style={{
                        width: "100%",
                        padding: 10,
                        border: "1px solid var(--signal-border)",
                        background: fieldBusy === selectedField ? "var(--signal-bg-mid)" : "var(--signal-bg-field)",
                        color: fieldBusy === selectedField ? "var(--signal-text-dim)" : "var(--signal-text)",
                        resize: "vertical",
                        fontFamily: "inherit",
                        boxSizing: "border-box",
                        transition: "background 0.2s, color 0.2s",
                      }}
                    />
                  </>
                ) : (
                  <>
                    <CheatsheetBar
                      textareaRef={textareaRef}
                      t={t}
                      totalTokens={totalCardTokens}
                      value={
                        NATURAL_FIELDS.has(selectedField)
                          ? (card?.[selectedField] ?? "")
                          : Array.isArray(card?.structured_profile?.[selectedField])
                            ? card.structured_profile[selectedField].join("\n")
                            : (card?.structured_profile?.[selectedField] ?? "")
                      }
                      onChange={(val) => {
                        if (NATURAL_FIELDS.has(selectedField)) updateCardField(selectedField, val);
                        else updateStructuredField(selectedField, val);
                      }}
                    />
                    <textarea
                      ref={textareaRef}
                      value={
                        NATURAL_FIELDS.has(selectedField)
                          ? (selectedField === "tags"
                              ? (Array.isArray(card?.tags) ? card.tags.join(", ") : (card?.tags ?? ""))
                              : (card?.[selectedField] ?? ""))
                          : Array.isArray(card?.structured_profile?.[selectedField])
                            ? card.structured_profile[selectedField].join("\n")
                            : (card?.structured_profile?.[selectedField] ?? "")
                      }
                      onChange={(e) => {
                        if (NATURAL_FIELDS.has(selectedField)) {
                          if (selectedField === "tags") {
                            updateCardField("tags", e.target.value.split(",").map(t => t.trim()).filter(Boolean));
                          } else {
                            updateCardField(selectedField, e.target.value);
                          }
                        } else {
                          updateStructuredField(selectedField, e.target.value);
                        }
                      }}
                      rows={16}
                      disabled={fieldBusy === selectedField}
                      style={{
                        width: "100%",
                        padding: 10,
                        border: "1px solid var(--signal-border)",
                        background: fieldBusy === selectedField ? "var(--signal-bg-mid)" : "var(--signal-bg-field)",
                        color: fieldBusy === selectedField ? "var(--signal-text-dim)" : "var(--signal-text)",
                        resize: "vertical",
                        fontFamily: "inherit",
                        boxSizing: "border-box",
                        transition: "background 0.2s, color 0.2s",
                      }}
                    />
                  </>
                )}

                <div
                  style={{
                    marginTop: 10,
                    display: "flex",
                    justifyContent: "center",
                    gap: 8,
                  }}
                >
                  <button
                    className="signal-btn"
                    style={{
                      ...buttonStyle,
                      opacity: fieldBusy === selectedField ? 0.5 : 1,
                      cursor: fieldBusy === selectedField ? "not-allowed" : "pointer",
                    }}
                    onClick={() => openRegenModal(selectedField, "field")}
                    disabled={fieldBusy === selectedField}
                  >
                    {t.regenerateField || "Regenerate Field"}
                  </button>
                  <button
                    className="signal-btn"
                    style={{
                      ...buttonStyle,
                      opacity: !card ? 0.4 : 1,
                      cursor: !card ? "not-allowed" : "pointer",
                      fontWeight: 700,
                    }}
                    onClick={handleSaveCard}
                    disabled={!card}
                  >
                    {t.save || "Save"}
                  </button>
                </div>

                {selectedField === "first_mes" && (
                  <AlternateGreetings
                    greetings={card.alternate_greetings || []}
                    onChange={updateAlternateGreetings}
                    t={t}
                    cardId={cardId}
                  />
                )}
              </div>
            </div>
          )}
          {source && (
            <div
              style={{
                border: "1px solid var(--signal-border)",
                background: "var(--signal-bg-panel)",
                color: "var(--signal-text)",
                padding: 12,
                marginBottom: 12,
                textAlign: "center",
                letterSpacing: "0.04em",
              }}
            >
              Source loaded: <strong>{source.title || "Untitled page"}</strong>
              {sourceId ? ` (ID: ${sourceId})` : ""}
            </div>
          )}
          {regenModal.open && (
            <RegenModal
              t={t}
              value={regenModal}
              onChange={setRegenModal}
              onClose={closeRegenModal}
              onSubmit={submitRegenModal}
            />
          )}
        </section>
      </div>
    </>
  );
}

const buttonStyle = {
  padding: "10px 14px",
  border: "1px solid var(--signal-border)",
  background: "var(--signal-bg-btn)",
  color: "var(--signal-text)",
  cursor: "pointer",
  fontWeight: 700,
};

function FieldLoadingBar() {
  return <div className="signal-bar-running" />;
}

const inputStyle = {
  padding: 12,
  border: "1px solid var(--signal-border)",
  background: "var(--signal-bg-field)",
  color: "var(--signal-text)",
  minWidth: 220,
};
