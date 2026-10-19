/**
 * App.jsx — Root application component
 * ======================================
 * The top-level component. Owns global state and renders the main
 * layout: TopNav, the active studio (Character or Lore), and the
 * library drawer.
 *
 * GLOBAL STATE MANAGED HERE
 * -------------------------
 * activeTab        "character" | "lore" — which studio is shown
 * theme            "light" | "dark" — applied as data-theme on <html>
 * language         "en" | "ja" | "zh" — passed down as `t` prop
 * card             The currently loaded character card object
 * cardId           DB id of the current card (null if unsaved)
 * imageFile        File object for the card image (if uploaded)
 * imageUrl         Object URL or proxy URL for the card image preview
 * libraryOpen      Whether the library drawer is visible
 * libraryCards     Array of card summaries from GET /api/cards
 * librarySearch    Current search string for filtering library cards
 *
 * LIBRARY DRAWER
 * --------------
 * Slides in from the right. Shows all saved cards with search,
 * load, duplicate, rename, and delete actions.
 * Rename is done inline with a double-click on the card name.
 *
 * HOW TO EXTEND
 * -------------
 * - Add a new global state: useState here, pass as prop or use context.
 * - Add a new tab: add to the activeTab switch and the TopNav tabs list.
 * - Add a new library action: add a button in the filteredLibraryCards
 *   map and a handler function above it.
 */

import { useState, useEffect } from "react";
import { LANGUAGES, useStrings } from "./lib/i18n";
import ConfigPage from "./components/ConfigPage";
import TopNav from "./components/TopNav";
import CharacterStudio from "./components/studio/CharacterStudio";
import LoreStudio from "./components/studio/LoreStudio";
import TextStudio from "./components/studio/TextStudio";
import SearchModal from "./components/SearchModal";
import { anyBusy } from "./lib/leaveGuard";
import { listCards, loadCard, deleteCard, renameCard, duplicateCard } from "./lib/api";

export default function App() {
  const [mode, setMode] = useState("character"); // "character" | "lore" | "text" | "config"
  const [modeDir, setModeDir] = useState("right");
  const [lang, setLang] = useState(() => localStorage.getItem("signal-lang") || "en");
  const t = useStrings(lang);

  useEffect(() => { localStorage.setItem("signal-lang", lang); }, [lang]); // which direction to slide
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [libraryCards, setLibraryCards] = useState([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(null); // card id pending delete
  const [toast, setToast] = useState(""); // save confirmation message
  const [librarySearch, setLibrarySearch] = useState("");

  const [url, setUrl] = useState("");
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
  const [handoff, setHandoff] = useState(null);   // TEXT "Make card" -> CHARACTER: {lore_project_id, story_point}
  const [searchOpen, setSearchOpen] = useState(false);
  const [focus, setFocus] = useState(null);       // search hit to open: {kind: "lore"|"text", project_id, id}

  // Ctrl+K / Cmd+K opens the search everywhere
  useEffect(() => {
    function onKey(e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen(true); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  // closing the tab while a job runs or an edit isn't saved yet: ask first
  useEffect(() => {
    function onLeave(e) {
      if (!anyBusy()) return;
      e.preventDefault();
      e.returnValue = t.unsavedLeave || "A job is running or changes are not saved yet. Leave anyway?";
      return e.returnValue;
    }
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [t]);

  function goTo(next) {
    const modes = ["character", "lore", "text", "config"];
    setModeDir(modes.indexOf(next) > modes.indexOf(mode) ? "right" : "left");
    setMode(next);
  }
  async function openSearchHit(it) {
    if (it.group === "cards") { await handleLoadCard(it.id); goTo("character"); }
    else if (it.group === "lore") { setFocus({ kind: "lore", project_id: it.project_id, id: it.id }); goTo("lore"); }
    else if (it.group === "entities") { setFocus({ kind: "text", project_id: it.project_id, id: it.id }); goTo("text"); }
    else if (it.group === "texts") { setFocus({ kind: "text", project_id: it.id, id: null }); goTo("text"); }
  }

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
    setLibrarySearch("");
    try {
      const cards = await listCards();
      setLibraryCards(cards);
    } catch (e) {
      setLibraryError(e.message);
    } finally {
      setLibraryLoading(false);
    }
  }

  const filteredLibraryCards = librarySearch.trim()
    ? libraryCards.filter(c =>
        (c.name || "").toLowerCase().includes(librarySearch.toLowerCase()) ||
        (c.url || "").toLowerCase().includes(librarySearch.toLowerCase())
      )
    : libraryCards;

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
    <div
      style={{
        minHeight: "100vh",
        width: "100%",
        background: "var(--signal-bg, #e8e3d3)",
        backgroundImage: `
          linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px)
        `,
        backgroundSize: "40px 40px",
      }}
    >
    <main
      className="signal-screen"
      style={{
        minHeight: "100vh",
        color: "var(--signal-text, #2b2b2b)",
        padding: 24,
      }}
    >
      {/* Save toast */}
      {toast && (
        <div style={{
          position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
          background: "var(--signal-btn-active-bg)", color: "var(--signal-btn-active-text)",
          padding: "10px 24px", border: "1px solid var(--signal-border)",
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
          background: "var(--signal-bg-panel, #efe8d8)",
          color: "var(--signal-text)",
          borderLeft: "1px solid var(--signal-border, #3a3a3a)",
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
            borderBottom: "1px solid var(--signal-border, #3a3a3a)",
            background: "var(--signal-bg-mid, #e5deca)",
          }}
        >
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>{t.savedCards}</div>
            <div style={{ fontSize: 12, color: "var(--signal-text-dim, #888)", marginTop: 2 }}>
              {t.clickToResume}
            </div>
          </div>
          <button
            onClick={() => setLibraryOpen(false)}
            aria-label="Close library"
            style={{
              background: "none",
              border: "1px solid var(--signal-border, #3a3a3a)",
              color: "var(--signal-text)",
              padding: "6px 10px",
              cursor: "pointer",
              fontWeight: 700,
              fontSize: 14,
            }}
          >
            ✕
          </button>
        </div>

        {/* Search */}
        <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--signal-border, #3a3a3a)" }}>
          <input
            value={librarySearch}
            onChange={e => setLibrarySearch(e.target.value)}
            placeholder="Search cards..."
            style={{
              width: "100%",
              padding: "7px 10px",
              border: "1px solid var(--signal-border)",
              background: "var(--signal-bg-field)",
              color: "var(--signal-text)",
              fontFamily: "inherit",
              fontSize: 13,
              boxSizing: "border-box",
              outline: "none",
            }}
          />
        </div>

        {/* Drawer body */}
        <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
          {libraryLoading && (
            <div style={{ color: "var(--signal-text-dim, #888)", textAlign: "center", padding: 24 }}>
              {t.loading}
            </div>
          )}
          {libraryError && (
            <div style={{ color: "#b00", padding: 12 }}>{libraryError}</div>
          )}
          {!libraryLoading && !libraryError && libraryCards.length === 0 && (
            <div style={{ color: "var(--signal-text-dim, #888)", textAlign: "center", padding: 24 }}>
              {t.noSavedCards}
            </div>
          )}
          {!libraryLoading && !libraryError && filteredLibraryCards.length === 0 && libraryCards.length > 0 && (
            <div style={{ color: "var(--signal-text-dim, #888)", textAlign: "center", padding: 24 }}>
              No cards match "{librarySearch}"
            </div>
          )}
          {filteredLibraryCards.map((c, i) => (
            <div
              key={c.id}
              className="signal-library-item"
              onClick={() => handleLoadCard(c.id)}
              style={{
                animationDelay: `${i * 40}ms`,
                padding: "10px 12px",
                marginBottom: 8,
                border: "1px solid var(--signal-border)",
                background: cardId === c.id ? "var(--signal-btn-active-bg)" : "var(--signal-bg-field)",
                color: cardId === c.id ? "var(--signal-btn-active-text)" : "var(--signal-text)",
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
                        background: cardId === c.id ? "rgba(255,255,255,0.15)" : "var(--signal-bg-mid)",
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
                      border: "1px solid var(--signal-border)",
                      background: "transparent",
                      color: "var(--signal-text-dim)",
                      cursor: "pointer",
                      fontSize: 11,
                      fontWeight: 700,
                      fontFamily: "inherit",
                    }}
                    title="Duplicate card"
                    aria-label={`Duplicate ${c.name || "card"}`}
                  >
                    ⎘
                  </button>
                  <button
                    onClick={(e) => handleDeleteCard(c.id, e)}
                    style={{
                      padding: "3px 8px",
                      border: `1px solid ${deleteConfirm === c.id ? "#c84a3a" : "var(--signal-border)"}`,
                      background: deleteConfirm === c.id ? "#c84a3a" : "transparent",
                      color: deleteConfirm === c.id ? "#fff" : "#c84a3a",
                      cursor: "pointer",
                      fontSize: 11,
                      fontWeight: 700,
                      fontFamily: "inherit",
                    }}
                    title={deleteConfirm === c.id ? "Click again to confirm" : "Delete card"}
                    aria-label={deleteConfirm === c.id ? `Confirm: delete ${c.name || "card"}` : `Delete ${c.name || "card"}`}
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
        <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} onPick={openSearchHit} t={t} />
        <TopNav
          mode={mode}
          setMode={goTo}
          onLibrary={openLibrary}
          onSearch={() => setSearchOpen(true)}
          lang={lang}
          setLang={setLang}
          t={t}
        />

        <div key={mode} className={modeDir === "right" ? "signal-mode-enter" : "signal-mode-enter-left"} style={{ display: "contents" }}>
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
            pendingHandoff={handoff}
            clearPendingHandoff={() => setHandoff(null)}
          />
        ) : mode === "text" ? (
          <TextStudio
            t={t}
            showToast={showToast}
            focus={focus?.kind === "text" ? focus : null}
            clearFocus={() => setFocus(null)}
            onOpenLore={() => { setModeDir("left"); setMode("lore"); }}
            onMakeCard={({ source: src, source_id, lore_project_id, story_point }) => {
              // a reviewed fic character becomes the CHARACTER studio's source, ready for Generate Card
              setSource(src); setSourceId(source_id); setCard(null); setCardId(null); setUrl("");
              setHandoff({ lore_project_id: lore_project_id || null, story_point: story_point || "" });
              setModeDir("left"); setMode("character");
              showToast(`${src?.title || "Character"} is ready: press Generate Card` +
                (lore_project_id ? " (the story's lorebook will be attached)" : ""));
            }}
          />
        ) : (
          <LoreStudio
            t={t}
            showToast={showToast}
            focus={focus?.kind === "lore" ? focus : null}
            clearFocus={() => setFocus(null)}
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
    </div>
  );
}
