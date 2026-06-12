import React, { useEffect, useState, useRef } from "react";
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
  startScrape,
  fetchModels,
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
  const [sourceOpen, setSourceOpen] = useState(false);
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
        setSource(jobData.result.source);
        setSourceId(jobData.result.source_id);
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

  async function handleSaveCard() {
    if (!card || !cardId) return;
    try {
      setError("");
      await saveCard(cardId, card);
      if (showToast) showToast(t.savedOk || "Card saved");
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

        setCard((prev) => ({
          ...prev,
          [fieldName]: nextValue,
        }));
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

    const blob = new Blob([JSON.stringify(card, null, 2)], {
      type: "application/json",
    });

    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = `${card.name || "card"}.json`;
    a.click();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <>
      <h1 className="nier-title nier-heading" style={{ marginTop: 0, marginBottom: 4, display: 'block', textAlign: 'center' }}>Character Card Studio</h1>
      <p style={{ color: "var(--nier-text-dim)" }}>
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
            border: "1px solid var(--nier-border)",
            background: "var(--nier-bg-field)",
            color: "var(--nier-text)",
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
        </select>

        {/* Model picker — NieR style */}
        <div ref={modelRef} style={{ position: "relative", minWidth: 260 }}>
          {/* Trigger input */}
          <div style={{
            display: "flex",
            border: "1px solid var(--nier-border)",
            background: "var(--nier-bg-field)",
          }}>
            <input
              value={modelDropdownOpen ? modelSearch : (model || "")}
              onChange={(e) => { setModelSearch(e.target.value); setModel(e.target.value); }}
              onFocus={() => { setModelDropdownOpen(true); setModelSearch(model || ""); }}
              placeholder={t.modelOptional || "Model (optional)"}
              style={{
                flex: 1, padding: "12px 10px", border: "none",
                background: "transparent", color: "var(--nier-text)",
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
                borderLeft: "1px solid var(--nier-border)",
                background: "var(--nier-bg-panel)", cursor: "pointer",
                color: "var(--nier-text)", fontSize: 12,
              }}
            >
              {modelDropdownOpen ? "▴" : "▾"}
            </button>
          </div>

          {modelDropdownOpen && (
            <div style={{
              position: "absolute", top: "100%", left: 0, right: 0,
              background: "var(--nier-bg-panel)", border: "1px solid var(--nier-border)",
              borderTop: "none", zIndex: 500,
              display: "flex", flexDirection: "column",
              maxHeight: 340,
            }}>
              {/* Search bar */}
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "8px 12px", borderBottom: "1px solid var(--nier-border)",
                background: "var(--nier-bg-mid)",
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
                    color: "var(--nier-text)", fontFamily: "inherit", fontSize: 13,
                    outline: "none",
                  }}
                />
              </div>

              {/* Fetch button */}
              <button
                onClick={() => loadModels(provider)}
                disabled={modelsLoading}
                className={modelsLoading ? "nier-fetch-btn nier-fetch-btn-loading" : "nier-fetch-btn"}
                style={{
                  margin: "8px 10px 4px",
                  padding: "8px 12px",
                  border: "1px solid var(--nier-border)",
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
                  fontSize: 11, color: "var(--nier-text-dim)",
                  letterSpacing: "0.06em",
                }}>
                  {modelList.length} models available
                </div>
              )}

              {/* Model list */}
              <div style={{ overflowY: "auto", flex: 1 }}>
                {!modelsLoading && modelList.length === 0 && (
                  <div style={{ padding: "12px", color: "var(--nier-text-dim)", fontSize: 13, textAlign: "center" }}>
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
                        borderBottom: "1px solid var(--nier-border)",
                        background: model === m.id ? "var(--nier-btn-active-bg)" : "transparent",
                        color: model === m.id ? "var(--nier-text-inv)" : "var(--nier-text)",
                      }}
                      onMouseEnter={(e) => { if (model !== m.id) e.currentTarget.style.background = "var(--nier-bg-mid)"; }}
                      onMouseLeave={(e) => { if (model !== m.id) e.currentTarget.style.background = "transparent"; }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600 }}>
                        {m.name}
                      </div>
                      <div style={{ fontSize: 11, opacity: 0.55, marginTop: 2 }}>
                        {m.id}
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
        <button onClick={handleScrape} disabled={loading} className="nier-btn" style={buttonStyle}>
          {loading ? (t.working || "Working...") : (t.scrape || "Scrape")}
        </button>

        <button
          onClick={() => setSourceOpen(true)}
          disabled={!source}
          className="nier-btn"
          style={buttonStyle}
        >
          {t.viewSource || "View Source"}
        </button>

        <button
          onClick={handleGenerate}
          disabled={loading || !sourceId}
          className="nier-btn"
          style={buttonStyle}
        >
          {t.generateCard || "Generate Card"}
        </button>

        <button onClick={handleSaveCard} disabled={!card} className="nier-btn" style={buttonStyle}>
          {t.save || "Save"}
        </button>

        <button onClick={handleExportCard} disabled={!card} className="nier-btn" style={buttonStyle}>
          {t.exportCardJson || "Export Card JSON"}
        </button>

        <button
          onClick={handleExportStructured}
          disabled={!card?.structured_profile}
          className="nier-btn"
          style={buttonStyle}
        >
          {t.exportStructuredJson || "Export Structured JSON"}
        </button>
      </div>

      {error && mainJob?.status !== "failed" ? (
        <div
          style={{
            border: "1px solid #7f1d1d",
            background: "var(--nier-bg-panel)",
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
        className="nier-main-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(220px, 0.9fr) minmax(0, 1.8fr)",
          flexWrap: "wrap",
          gap: 16,
          alignItems: "start",
        }}
      >
        <div className="nier-sticky-panel" style={{ position: "sticky", top: 16, alignSelf: "start" }}>
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
                border: "1px solid var(--nier-border)",
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
          className="nier-panel nier-panel-delay-1"
          style={{
            border: "1px solid var(--nier-border)",
            background: "var(--nier-bg-panel)",
            padding: 14,

          }}
        >
          <h2 className="nier-heading" style={{ marginTop: 0 }}>{t.characterSystem || "Character System"}</h2>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <button
              className={characterViewMode === "natural" ? "nier-btn nier-btn-active" : "nier-btn"}
              style={{ ...buttonStyle }}
              onClick={() => setCharacterViewMode("natural")}
            >
              {t.natural || "Natural"}
            </button>

            <button
              className={characterViewMode === "structured" ? "nier-btn nier-btn-active" : "nier-btn"}
              style={{ ...buttonStyle }}
              onClick={() => setCharacterViewMode("structured")}
            >
              {t.structured || "Structured"}
            </button>
          </div>
          {!card ? (
            <div style={{ color: "var(--nier-text-dim)" }}>Generate a card to begin.</div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(160px, 0.9fr) minmax(0, 1.7fr)",
              // nier-character-grid applied below
                gap: 12,
                alignItems: "start",
              }}
            >
              <div
                style={{
                  border: "1px solid var(--nier-border)",
                  background: "var(--nier-bg-field)",
                  padding: 10,
                }}
              >
                <button
                  style={{ ...buttonStyle, width: "100%", marginBottom: 10 }}
                  onClick={() => openRegenModal("", "full")}
                >
                  {t.regenerateFullCard || "Regenerate Full Card"}
                </button>



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
                        "species",
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
                        <div style={{ gridColumn: "1 / -1", margin: "6px 0 2px" }} className="nier-divider">
                          <div className="nier-divider-mark nier-divider-mark-left" />
                          <div className="nier-divider-bar" />
                          <span className="nier-divider-label">{t.cardFields || "Card fields"}</span>
                          <div className="nier-divider-bar" />
                          <div className="nier-divider-mark nier-divider-mark-right" />
                        </div>
                      )}
                      <button
                        type="button"
                        className={selectedField === field ? "nier-btn nier-btn-active nier-field-active nier-list-item" : "nier-btn nier-list-item"}
                        style={{
                          animationDelay: `${idx * 35}ms`,
                          padding: "10px 8px",
                          cursor: "pointer",
                          textAlign: "left",
                          fontSize: 14,
                        }}
                        onClick={() => setSelectedField(field)}
                      >
                        ▸ {(t.fields && t.fields[field]) || field.replaceAll("_", " ")}
                      </button>
                    </React.Fragment>
                  ))}
                </div>
              </div>

              <div
                className="nier-screen-panel nier-corners-all"
              style={{
                  border: "1px solid var(--nier-border)",
                  background: "var(--nier-bg-field)",
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
                    borderBottom: "1px solid var(--nier-border)",
                    background: "transparent",
                    color: "var(--nier-text)",
                    fontFamily: "inherit",
                    outline: "none",
                    padding: "2px 0 6px",
                    boxSizing: "border-box",
                  }}
                />

                <div
                  style={{
                    borderBottom: "1px solid var(--nier-border)",
                    paddingBottom: 6,
                    marginBottom: 12,
                    textAlign: "center",
                  }}
                >
                  <div className="nier-field-label-active">
                    {((t.fields && t.fields[selectedField]) || selectedField.replaceAll("_", " ")).toUpperCase()}
                  </div>
                </div>

                {/* Loading bar shown while this field is regenerating */}
                {fieldBusy === selectedField && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 12, color: "var(--nier-text-dim)", marginBottom: 5, textAlign: "center", letterSpacing: "0.08em" }}>
                      Regenerating…
                    </div>
                    <div style={{ width: "100%", height: 6, background: "var(--nier-bg-field)", overflow: "hidden", position: "relative" }}>
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
                      value={card[selectedField] ?? ""}
                      onChange={(e) => updateCardField(selectedField, e.target.value)}
                      rows={16}
                      disabled={fieldBusy === selectedField}
                      style={{
                        width: "100%",
                        padding: 10,
                        border: "1px solid var(--nier-border)",
                        background: fieldBusy === selectedField ? "var(--nier-bg-mid)" : "var(--nier-bg-field)",
                        color: fieldBusy === selectedField ? "var(--nier-text-dim)" : "var(--nier-text)",
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
                        border: "1px solid var(--nier-border)",
                        background: fieldBusy === selectedField ? "var(--nier-bg-mid)" : "var(--nier-bg-field)",
                        color: fieldBusy === selectedField ? "var(--nier-text-dim)" : "var(--nier-text)",
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
                  }}
                >
                  <button
                    className="nier-btn"
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
                border: "1px solid var(--nier-border)",
                background: "var(--nier-bg-panel)",
                color: "var(--nier-text)",
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
  border: "1px solid var(--nier-border)",
  background: "var(--nier-bg-btn)",
  color: "var(--nier-text)",
  cursor: "pointer",
  fontWeight: 700,
};

function FieldLoadingBar() {
  return <div className="nier-bar-running" />;
}

const inputStyle = {
  padding: 12,
  border: "1px solid var(--nier-border)",
  background: "var(--nier-bg-field)",
  color: "var(--nier-text)",
  minWidth: 220,
};
