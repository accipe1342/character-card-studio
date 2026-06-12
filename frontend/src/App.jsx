import { useState, useEffect } from "react";
import { LANGUAGES, useStrings } from "./lib/i18n";
import ConfigPage from "./components/ConfigPage";
import TopNav from "./components/TopNav";
import CharacterStudio from "./components/studio/CharacterStudio";
import LoreStudio from "./components/studio/LoreStudio";
import { listCards, loadCard, deleteCard, renameCard, duplicateCard } from "./lib/api";

export default function App() {
  const [mode, setMode] = useState("character"); // "character" | "lore" | "config"
  const [modeDir, setModeDir] = useState("right");
  const [lang, setLang] = useState(() => localStorage.getItem("nier-lang") || "en");
  const t = useStrings(lang);

  useEffect(() => { localStorage.setItem("nier-lang", lang); }, [lang]); // which direction to slide
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [libraryCards, setLibraryCards] = useState([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(null); // card id pending delete
  const [toast, setToast] = useState(""); // save confirmation message

  const [url, setUrl] = useState("https://soulcalibur.fandom.com/wiki/Ivy");
  const [source, setSource] = useState(null);
  const [sourceId, setSourceId] = useState(null);

  const [card, setCard] = useState(null);
  const [cardId, setCardId] = useState(null);

  const [imageFile, setImageFile] = useState(null);
  const [imageUrl, setImageUrl] = useState("");

  // Clean up object URLs when they're replaced
  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl);
    };
  }, [imageUrl]);

  const [characterViewMode, setCharacterViewMode] = useState("natural");
  const [selectedField, setSelectedField] = useState("description");
  const [customPrompt, setCustomPrompt] = useState("");
  const [regenPreview, setRegenPreview] = useState(null);

  function showToast(msg) {
    setToast(msg);
    setTimeout(() => setToast(""), 2500);
  }

  async function handleDeleteCard(id, e) {
    e.stopPropagation();
    if (deleteConfirm === id) {
      try {
        await deleteCard(id);
        setLibraryCards(prev => prev.filter(c => c.id !== id));
        if (cardId === id) { setCard(null); setCardId(null); }
        setDeleteConfirm(null);
      } catch (err) {
        setLibraryError(err.message);
      }
    } else {
      setDeleteConfirm(id);
    }
  }

  async function handleDuplicateCard(id, e) {
    e.stopPropagation();
    try {
      const data = await duplicateCard(id);
      setLibraryCards(prev => [{ id: data.id, name: data.card.name, url: data.card.url || "", updated_at: new Date().toISOString() }, ...prev]);
      showToast("Card duplicated");
    } catch (err) {
      setLibraryError(err.message);
    }
  }

  async function openLibrary() {
    setLibraryOpen(true);
    setLibraryError("");
    setLibraryLoading(true);
    try {
      const cards = await listCards();
      setLibraryCards(cards);
    } catch (e) {
      setLibraryError(e.message);
    } finally {
      setLibraryLoading(false);
    }
  }

  async function handleLoadCard(id) {
    try {
      const { card: loaded, source: loadedSource } = await loadCard(id);
      // Merge sex -> gender if gender is missing
      if (loaded.structured_profile && !loaded.structured_profile.gender && loaded.structured_profile.sex) {
        loaded.structured_profile.gender = loaded.structured_profile.sex;
      }
      setCard(loaded);
      setCardId(loaded.id);
      setSourceId(loaded.source_id);
      setSource(loadedSource);
      setUrl(loaded.url || loadedSource?.url || "");
      setLibraryOpen(false);
    } catch (e) {
      setLibraryError(e.message);
    }
  }

  return (
    <main
      className="nier-screen"
      style={{
        minHeight: "100vh",
        background: "var(--nier-bg, #e8e3d3)",
        color: "var(--nier-text, #2b2b2b)",
        padding: 24,
        backgroundImage: `
          linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px)
        `,
        backgroundSize: "40px 40px",
      }}
    >
      {/* Save toast */}
      {toast && (
        <div style={{
          position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
          background: "var(--nier-btn-active-bg)", color: "var(--nier-text-inv)",
          padding: "10px 24px", border: "1px solid var(--nier-border)",
          fontSize: 13, fontWeight: 700, letterSpacing: "0.08em",
          zIndex: 9999, pointerEvents: "none",
          boxShadow: "0 4px 16px rgba(0,0,0,0.2)",
        }}>
          ✓ {toast}
        </div>
      )}

      {/* Library drawer backdrop */}
      {libraryOpen && (
        <div
          onClick={() => setLibraryOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.4)",
            zIndex: 200,
          }}
        />
      )}

      {/* Library drawer */}
      <div
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          width: "min(400px, 92vw)",
          height: "100vh",
          background: "var(--nier-bg-panel, #efe8d8)",
          borderLeft: "1px solid #3a3a3a",
          zIndex: 201,
          display: "flex",
          flexDirection: "column",
          transform: libraryOpen ? "translateX(0)" : "translateX(100%)",
          transition: "transform 0.22s ease",
          boxShadow: libraryOpen ? "-4px 0 20px rgba(0,0,0,0.18)" : "none",
        }}
      >
        {/* Drawer header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "14px 16px",
            borderBottom: "1px solid #3a3a3a",
            background: "var(--nier-bg-mid, #e5deca)",
          }}
        >
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>{t.savedCards}</div>
            <div style={{ fontSize: 12, color: "var(--nier-text-dim, #888)", marginTop: 2 }}>
              {t.clickToResume}
            </div>
          </div>
          <button
            onClick={() => setLibraryOpen(false)}
            style={{
              background: "none",
              border: "1px solid var(--nier-border, #3a3a3a)",
              padding: "6px 10px",
              cursor: "pointer",
              fontWeight: 700,
              fontSize: 14,
            }}
          >
            ✕
          </button>
        </div>

        {/* Drawer body */}
        <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
          {libraryLoading && (
            <div style={{ color: "var(--nier-text-dim, #888)", textAlign: "center", padding: 24 }}>
              {t.loading}
            </div>
          )}
          {libraryError && (
            <div style={{ color: "#b00", padding: 12 }}>{libraryError}</div>
          )}
          {!libraryLoading && !libraryError && libraryCards.length === 0 && (
            <div style={{ color: "var(--nier-text-dim, #888)", textAlign: "center", padding: 24 }}>
              {t.noSavedCards}
            </div>
          )}
          {libraryCards.map((c, i) => (
            <div
              key={c.id}
              className="nier-library-item"
              onClick={() => handleLoadCard(c.id)}
              style={{
                animationDelay: `${i * 40}ms`,
                padding: "10px 12px",
                marginBottom: 8,
                border: "1px solid var(--nier-border)",
                background: cardId === c.id ? "var(--nier-btn-active-bg)" : "var(--nier-bg-field)",
                color: cardId === c.id ? "var(--nier-text-inv)" : "var(--nier-text)",
                cursor: "pointer",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.name || "Unnamed"}
                  </div>
                  <div style={{ fontSize: 12, opacity: 0.7, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.url || c.title || "—"}
                  </div>
                  <div style={{ fontSize: 11, opacity: 0.6, marginTop: 3, display: "flex", gap: 6, alignItems: "center" }}>
                    {c.model && (
                      <span style={{
                        fontFamily: "monospace",
                        background: cardId === c.id ? "rgba(255,255,255,0.15)" : "var(--nier-bg-mid)",
                        padding: "1px 5px",
                        fontSize: 10,
                        letterSpacing: "0.02em",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        maxWidth: 180,
                        display: "inline-block",
                      }}>
                        {c.model}
                      </span>
                    )}
                    <span style={{ opacity: 0.5 }}>
                      {c.updated_at ? new Date(c.updated_at).toLocaleString() : ""}
                    </span>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                  <button
                    onClick={(e) => handleDuplicateCard(c.id, e)}
                    style={{
                      padding: "3px 8px",
                      border: "1px solid var(--nier-border)",
                      background: "transparent",
                      color: "var(--nier-text-dim)",
                      cursor: "pointer",
                      fontSize: 11,
                      fontWeight: 700,
                      fontFamily: "inherit",
                    }}
                    title="Duplicate card"
                  >
                    ⎘
                  </button>
                  <button
                    onClick={(e) => handleDeleteCard(c.id, e)}
                    style={{
                      padding: "3px 8px",
                      border: `1px solid ${deleteConfirm === c.id ? "#c84a3a" : "var(--nier-border)"}`,
                      background: deleteConfirm === c.id ? "#c84a3a" : "transparent",
                      color: deleteConfirm === c.id ? "#fff" : "#c84a3a",
                      cursor: "pointer",
                      fontSize: 11,
                      fontWeight: 700,
                      fontFamily: "inherit",
                    }}
                    title={deleteConfirm === c.id ? "Click again to confirm" : "Delete card"}
                  >
                    {deleteConfirm === c.id ? "Sure?" : "✕"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ maxWidth: 1600, margin: "0 auto" }}>
        <TopNav
          mode={mode}
          setMode={(next) => {
            const modes = ["character", "lore"];
            setModeDir(modes.indexOf(next) > modes.indexOf(mode) ? "right" : "left");
            setMode(next);
          }}
          onLibrary={openLibrary}
          lang={lang}
          setLang={setLang}
          t={t}
        />

        <div key={mode} className={modeDir === "right" ? "nier-mode-enter" : "nier-mode-enter-left"} style={{ display: "contents" }}>
        {mode === "config" ? (
          <ConfigPage t={t} showToast={showToast} />
        ) : mode === "character" ? (
          <CharacterStudio
            t={t}
            showToast={showToast}
            imageFile={imageFile}
            setImageFile={setImageFile}
            imageUrl={imageUrl}
            setImageUrl={setImageUrl}
            url={url}
            setUrl={setUrl}
            source={source}
            setSource={setSource}
            sourceId={sourceId}
            setSourceId={setSourceId}
            card={card}
            setCard={setCard}
            cardId={cardId}
            setCardId={setCardId}
            characterViewMode={characterViewMode}
            setCharacterViewMode={setCharacterViewMode}
            selectedField={selectedField}
            setSelectedField={setSelectedField}
            customPrompt={customPrompt}
            setCustomPrompt={setCustomPrompt}
            regenPreview={regenPreview}
            setRegenPreview={setRegenPreview}
          />
        ) : (
          <LoreStudio
            t={t}
            showToast={showToast}
            url={url}
            setUrl={setUrl}
            source={source}
            setSource={setSource}
            sourceId={sourceId}
            setSourceId={setSourceId}
            card={card}
            setCard={setCard}
            cardId={cardId}
            setCardId={setCardId}
            characterViewMode={characterViewMode}
            setCharacterViewMode={setCharacterViewMode}
            selectedField={selectedField}
            setSelectedField={setSelectedField}
            customPrompt={customPrompt}
            setCustomPrompt={setCustomPrompt}
            regenPreview={regenPreview}
            setRegenPreview={setRegenPreview}
          />
        )}
        </div>
      </div>
    </main>
  );
}
