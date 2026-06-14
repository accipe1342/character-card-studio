/**
 * LoreStudio.jsx — Lorebook editor
 * ==================================
 * The lore entry creation and management interface.
 * Supports single-URL generation, multi-URL crawling, manual entry
 * creation, and AI generation from custom text.
 *
 * LAYOUT
 * ------
 * Left panel:   Project list + new project input
 * Middle panel: Entry list for the active project + action buttons
 * Right panel:  Entry editor (title, keywords, content, ST settings)
 *
 * STATE
 * -----
 * projects        Array of lore project objects
 * activeProject   ID of the currently selected project (or null = all)
 * entries         Array of lore entries for the active project
 * selectedId      ID of the entry being edited
 * entry           The current entry object being edited
 * crawlMode       "single" | "multi" — URL input mode
 * urls            Array of URLs for multi-mode
 * loading         True while a crawl/generate job is running
 * saving          True while saving an entry
 * deleteConfirm   ID of entry waiting for delete confirmation
 * flashEntry      ID of entry to flash green on save
 * deletingEntry   ID of entry flashing red before deletion
 * movingEntryId   ID of entry showing the move-to-project dropdown
 * showGenPanel    Whether the "Generate from Prompt" panel is visible
 *
 * KEY HANDLERS
 * ------------
 * handleStartCrawl()     Starts single or multi URL lore generation
 * handleSelectEntry(id)  Loads an entry into the editor
 * handleSaveEntry()      Saves the current entry, triggers flash
 * handleDeleteEntry()    Two-click delete with red flash animation
 * handleNewEntry()       Creates a blank entry in the active project
 * handleExport()         Downloads lorebook as SillyTavern JSON
 * handleMoveEntry()      Moves entry to a different project
 *
 * SILLYAVERN FIELDS
 * -----------------
 * Each entry has three ST-specific sliders in the editor:
 *   scan_depth      (1–20)    How many messages to scan for keywords
 *   insertion_order (0–1000)  Priority; lower = inserted first
 *   entry_depth     (0–20)    Where in context to insert the entry
 * These are saved to the DB and exported in the lorebook JSON.
 *
 * PROPS
 * -----
 * t              Translation strings from i18n.js
 * showToast(msg) App-level toast notification
 *
 * HOW TO EXTEND
 * -------------
 * - Add a new entry field: add to the entry editor section and update
 *   the PATCH /api/lore/entry/:id endpoint in app.py.
 * - Add a new ST field: add a slider following the scan_depth pattern
 *   and add the column to database.py with a migration.
 * - Change crawl settings: edit the maxPages/maxDepth inputs and
 *   pass them to startLoreCrawl() / startMultiLore() in api.js.
 */

import React, { useState, useEffect } from "react";
import MainJobStatus from "../shared/MainJobStatus";
import {
  startLoreCrawl, startLoreSingle, startLoreMulti, listLoreEntries, getLoreEntry,
  updateLoreEntry, deleteLoreEntry, exportLorebook, getJob, fetchModels,
  listLoreProjects, createLoreProject, renameLoreProject, deleteLoreProject,
  newLoreEntry, generateLoreEntry, moveEntryToProject,
} from "../../lib/api";

const ENTRY_TYPES = ["character", "place", "faction", "event", "item", "ability", "concept", "other"];

export default function LoreStudio({ url, setUrl, t = {}, showToast }) {
  const [provider, setProvider] = useState("nanogpt");
  const [model, setModel] = useState("");
  const [maxPages, setMaxPages] = useState(10);
  const [maxDepth, setMaxDepth] = useState(1);
  const [purpose, setPurpose] = useState("Create a general lorebook");
  const [criteria, setCriteria] = useState("Must be a meaningful lore page");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [crawlMode, setCrawlMode] = useState("single"); // "single" | "multi" | "crawl"
  const [multiUrls, setMultiUrls] = useState(["", ""]); // for multi mode


  const [job, setJob] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [entries, setEntries] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [entry, setEntry] = useState(null);
  const [saving, setSaving] = useState(false);
  const [newKeyword, setNewKeyword] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [modelList, setModelList] = useState([]);
  const [modelSearch, setModelSearch] = useState("");
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(false);
  const modelRef = React.useRef(null);
  const [filterType, setFilterType] = useState("all");
  const [search, setSearch] = useState("");
  const [projects, setProjects] = useState([]);
  const [activeProject, setActiveProject] = useState(null);
  const [newProjectName, setNewProjectName] = useState("");
  const [renamingId, setRenamingId] = useState(null);
  const [renameVal, setRenameVal] = useState("");
  const [deletingProjectId, setDeletingProjectId] = useState(null);
  const [showGenPanel, setShowGenPanel] = useState(false);
  const [genPrompt, setGenPrompt] = useState("");
  const [genType, setGenType] = useState("concept");
  const [genTitle, setGenTitle] = useState("");
  const [generating, setGenerating] = useState(false);
  const [flashEntry, setFlashEntry] = useState(null);   // id of entry to flash green
  const [deletingEntry, setDeletingEntry] = useState(null); // id flashing red
  const [movingEntryId, setMovingEntryId] = useState(null); // entry being moved

  // Poll job
  useEffect(() => {
    if (!jobId) return;
    const interval = setInterval(async () => {
      try {
        const j = await getJob(jobId);
        setJob(j);
        if (j.status === "done" || j.status === "failed") {
          clearInterval(interval);
          setLoading(false);
          if (j.status === "done") { loadEntries(activeProjectRef.current); loadProjects(); }
        }
      } catch {}
    }, 1000);
    return () => clearInterval(interval);
  }, [jobId]);

  React.useEffect(() => {
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
    } catch (e) { console.error(e); }
    finally { setModelsLoading(false); }
  }

  function addMultiUrl() { setMultiUrls(prev => [...prev, ""]); }
  function removeMultiUrl(i) { setMultiUrls(prev => prev.filter((_, idx) => idx !== i)); }
  function updateMultiUrl(i, val) { setMultiUrls(prev => { const n = [...prev]; n[i] = val; return n; }); }

  async function handleNewEntry() {
    try {
      const data = await newLoreEntry(activeProject?.id);
      const blank = { id: data.id, title: data.title, entry_type: "concept", crawl_id: activeProject?.id };
      setEntries(prev => [blank, ...prev]);
      await handleSelectEntry(data.id);
    } catch(e) { setError(e.message); }
  }

  async function handleGenerateEntry() {
    if (!genPrompt.trim()) return;
    setGenerating(true); setError("");
    try {
      const result = await generateLoreEntry({
        prompt: genPrompt, title: genTitle, entry_type: genType,
        provider, model, project_id: activeProject?.id, save: true,
      });
      await loadEntries(activeProjectRef.current);
      await loadProjects();
      if (result.id) await handleSelectEntry(result.id);
      setShowGenPanel(false);
      setGenPrompt(""); setGenTitle("");
    } catch(e) { setError(e.message); }
    finally { setGenerating(false); }
  }

  async function loadProjects() {
    try {
      const data = await listLoreProjects();
      setProjects(data);
    } catch(e) { setError(e.message); }
  }

  const activeProjectRef = React.useRef(null);

  async function loadEntries(projectOverride) {
    try {
      const proj = projectOverride !== undefined ? projectOverride : activeProjectRef.current;
      const url = proj ? `/api/lore/entries?project_id=${proj.id}` : "/api/lore/entries";
      const res = await fetch(url);
      const data = await res.json();
      setEntries(data);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { loadProjects(); loadEntries(); }, []);
  useEffect(() => {
    activeProjectRef.current = activeProject;
    loadEntries(activeProject);
  }, [activeProject]);

  async function handleSelectEntry(id) {
    setSelectedId(id);
    try {
      const data = await getLoreEntry(id);
      // Normalize keywords — DB may return a JSON string instead of array
      if (typeof data.keywords === "string") {
        try { data.keywords = JSON.parse(data.keywords); } catch { data.keywords = []; }
      }
      if (!Array.isArray(data.keywords)) data.keywords = [];
      setEntry(data);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleSaveEntry() {
    if (!entry || !selectedId) return;
    setSaving(true);
    try {
      await updateLoreEntry(selectedId, entry);
      setEntries(prev => prev.map(e => e.id === selectedId ? { ...e, title: entry.title } : e));
      if (showToast) showToast(t.entrySaved || "Entry saved");
      setFlashEntry(selectedId);
      setTimeout(() => setFlashEntry(null), 900);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteEntry(id, e) {
    e.stopPropagation();
    if (deleteConfirm === id) {
      try {
        setDeletingEntry(id);
        await deleteLoreEntry(id);
        setTimeout(() => {
          setEntries(prev => prev.filter(e => e.id !== id));
          if (selectedId === id) { setSelectedId(null); setEntry(null); }
          setDeleteConfirm(null);
          setDeletingEntry(null);
        }, 400);
      } catch (err) {
        setError(err.message);
        setDeletingEntry(null);
      }
    } else {
      setDeleteConfirm(id);
    }
  }

  async function handleMoveEntry(loreId, projectId) {
    try {
      await moveEntryToProject(loreId, projectId === "none" ? null : parseInt(projectId));
      setMovingEntryId(null);
      await loadEntries(activeProjectRef.current);
      await loadProjects();
      if (showToast) showToast(t.entrySaved || "Moved");
    } catch(e) { setError(e.message); }
  }

  async function handleStartCrawl() {
    if (crawlMode !== "multi" && !url.trim()) { setError("Enter a URL first"); return; }
    setError("");
    setLoading(true);
    try {
      let data;
      if (crawlMode === "single") {
        data = await startLoreSingle({ url, provider, model, project_id: activeProject?.id });
      } else {
        const validUrls = multiUrls.filter(u => u.trim());
        if (!validUrls.length) { setError("Add at least one URL"); setLoading(false); return; }
        data = await startLoreMulti({ urls: validUrls, provider, model, project_id: activeProject?.id });
      }
      setJobId(data.job_id);
      setJob({ status: "running", progress: 0, stage: "queued", message: "Starting..." });
    } catch (e) {
      setError(e.message);
      setLoading(false);
    }
  }

  async function handleExport() {
    try {
      const data = await exportLorebook();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "lorebook.json";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setError(e.message);
    }
  }

  function addKeyword() {
    const kw = newKeyword.trim();
    if (!kw || !entry) return;
    if (!entry.keywords.includes(kw)) {
      setEntry(prev => ({ ...prev, keywords: [...prev.keywords, kw] }));
    }
    setNewKeyword("");
  }

  function removeKeyword(kw) {
    setEntry(prev => ({ ...prev, keywords: prev.keywords.filter(k => k !== kw) }));
  }

  const filteredEntries = entries.filter(e => {
    const matchType = filterType === "all" || e.entry_type === filterType;
    const matchSearch = !search || e.title?.toLowerCase().includes(search.toLowerCase());
    return matchType && matchSearch;
  });

  const inputStyle = {
    padding: "10px 12px",
    border: "1px solid var(--signal-border)",
    background: "var(--signal-bg-input)",
    color: "var(--signal-text)",
    fontFamily: "inherit",
    fontSize: 14,
    boxSizing: "border-box",
    width: "100%",
  };

  const btnStyle = {
    padding: "10px 14px",
    border: "1px solid var(--signal-border)",
    background: "var(--signal-bg-btn)",
    color: "var(--signal-text)",
    cursor: "pointer",
    fontWeight: 700,
    fontFamily: "inherit",
    letterSpacing: "0.06em",
  };

  return (
    <div>
      <h1 className="signal-title signal-heading" style={{ marginTop: 0, marginBottom: 4, display: "block", textAlign: "center" }}>
        {t.loreStudio || "Lore Studio"}
      </h1>
      <p style={{ color: "var(--signal-text-dim)", textAlign: "center", marginBottom: 20, letterSpacing: "0.04em" }}>
        {t.loreSubtitle || "World entries • factions • places • events"}
      </p>

      {/* Toolbar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        {crawlMode === "single" && (
          <input
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder={t.urlPlaceholder || "Paste a wiki URL"}
            style={{ ...inputStyle, flex: "1 1 300px" }}
          />
        )}
        <select value={provider} onChange={e => setProvider(e.target.value)} style={{ ...inputStyle, width: "auto" }}>
          <option value="nanogpt">NanoGPT</option>
          <option value="openrouter">OpenRouter</option>
          <option value="local">Local (OpenAI-compatible)</option>
        </select>
        {/* Model picker */}
        <div ref={modelRef} style={{ position: "relative", width: 220 }}>
          <div style={{ display: "flex", border: "1px solid var(--signal-border)", background: "var(--signal-bg-input)" }}>
            <input
              value={modelDropdownOpen ? modelSearch : (model || "")}
              onChange={e => { setModelSearch(e.target.value); setModel(e.target.value); }}
              onFocus={() => { setModelDropdownOpen(true); setModelSearch(model || ""); }}
              placeholder="Model (optional)"
              style={{ flex: 1, padding: "10px 10px", border: "none", background: "transparent", color: "var(--signal-text)", fontFamily: "inherit", fontSize: "inherit", outline: "none", minWidth: 0 }}
            />
            <button
              onClick={() => { if (modelDropdownOpen) { setModelDropdownOpen(false); } else { setModelDropdownOpen(true); } }}
              style={{ padding: "0 12px", border: "none", borderLeft: "1px solid var(--signal-border)", background: "var(--signal-bg-mid)", cursor: "pointer", color: "var(--signal-text)", fontSize: 12 }}
            >
              {modelDropdownOpen ? "▴" : "▾"}
            </button>
          </div>
          {modelDropdownOpen && (
            <div style={{ position: "absolute", top: "100%", left: 0, right: 0, background: "var(--signal-bg-panel)", border: "1px solid var(--signal-border)", borderTop: "none", zIndex: 500, display: "flex", flexDirection: "column", maxHeight: 320 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderBottom: "1px solid var(--signal-border)", background: "var(--signal-bg-mid)" }}>
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><circle cx="5.5" cy="5.5" r="4.5" stroke="#888" strokeWidth="1.2"/><line x1="9" y1="9" x2="12" y2="12" stroke="#888" strokeWidth="1.2" strokeLinecap="round"/></svg>
                <input autoFocus value={modelSearch} onChange={e => setModelSearch(e.target.value)} placeholder="Search models..." style={{ flex: 1, border: "none", background: "transparent", color: "var(--signal-text)", fontFamily: "inherit", fontSize: 13, outline: "none" }} />
              </div>
              <button
                onClick={() => loadModels(provider)}
                disabled={modelsLoading}
                className={modelsLoading ? "signal-fetch-btn signal-fetch-btn-loading" : "signal-fetch-btn"}
                style={{ margin: "8px 10px 4px", padding: "8px 12px", border: "1px solid var(--signal-border)", cursor: modelsLoading ? "not-allowed" : "pointer", fontFamily: "inherit", fontSize: 12, fontWeight: 700, letterSpacing: "0.08em", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
              >
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><circle cx="6.5" cy="6.5" r="5.5" stroke="currentColor" strokeWidth="1"/><circle cx="6.5" cy="6.5" r="2.5" stroke="currentColor" strokeWidth="1"/><circle cx="6.5" cy="6.5" r="0.8" fill="currentColor"/><line x1="1" y1="6.5" x2="4" y2="6.5" stroke="currentColor" strokeWidth="1"/><line x1="9" y1="6.5" x2="12" y2="6.5" stroke="currentColor" strokeWidth="1"/></svg>
                {modelsLoading ? "SCANNING…" : "FETCH MODELS FROM API"}
              </button>
              {modelList.length > 0 && <div style={{ padding: "3px 12px 6px", fontSize: 11, color: "var(--signal-text-dim)" }}>{modelList.length} models available</div>}
              <div style={{ overflowY: "auto", flex: 1 }}>
                {!modelsLoading && modelList.length === 0 && <div style={{ padding: "12px", color: "var(--signal-text-dim)", fontSize: 13, textAlign: "center" }}>Press FETCH MODELS to load</div>}
                {modelList.filter(m => !modelSearch || m.id.toLowerCase().includes(modelSearch.toLowerCase()) || m.name.toLowerCase().includes(modelSearch.toLowerCase())).map(m => (
                  <div key={m.id} onClick={() => { setModel(m.id); setModelSearch(""); setModelDropdownOpen(false); }}
                    style={{ padding: "9px 12px", cursor: "pointer", borderBottom: "1px solid var(--signal-border)", background: model === m.id ? "var(--signal-btn-active-bg)" : "transparent", color: model === m.id ? "var(--signal-btn-active-text)" : "var(--signal-text)" }}
                    onMouseEnter={e => { if (model !== m.id) e.currentTarget.style.background = "var(--signal-bg-mid)"; }}
                    onMouseLeave={e => { if (model !== m.id) e.currentTarget.style.background = "transparent"; }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{m.name}</div>
                    <div style={{ fontSize: 11, opacity: 0.55, marginTop: 2 }}>{m.id}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button className="signal-btn" onClick={handleStartCrawl} disabled={loading || crawlMode === "multi"} style={btnStyle}>
          {loading && crawlMode === "single" ? (t.working || "Working...") : "⟳ " + (t.generateEntry || "Generate Entry")}
        </button>

        <button
          className="signal-btn"
          onClick={() => { setCrawlMode(m => m === "multi" ? "single" : "multi"); }}
          style={btnStyle}
        >
          {crawlMode === "multi" ? (t.cancelBatch || "Cancel") : (t.multiplePages || "Multiple Pages")}
        </button>



        {entries.length > 0 && (
          <button className="signal-btn" onClick={handleExport} style={btnStyle}>
            ↓ {t.exportLorebook || "Export Lorebook"}
          </button>
        )}
        <button className="signal-btn" onClick={handleNewEntry} style={btnStyle}>
          + {t.newEntry || "New Entry"}
        </button>
        <button className="signal-btn" onClick={() => setShowGenPanel(v => !v)} style={btnStyle}>
          ✦ {t.generateFromPrompt || "Generate from Prompt"}
        </button>
        {activeProject && entries.length > 0 && (
          <button className="signal-btn" onClick={async () => {
            if (!window.confirm(`Delete all ${entries.length} entries in "${activeProject.project_name}"?`)) return;
            await deleteLoreProject(activeProject.id);
            const recreated = await createLoreProject(activeProject.project_name);
            setProjects(prev => prev.map(p => p.id === activeProject.id ? { ...p, id: recreated.id, entry_count: 0 } : p));
            setActiveProject(prev => ({ ...prev, id: recreated.id }));
            setEntries([]);
          }} style={{ padding: "8px 12px", border: "1px solid #c84a3a", background: "transparent", color: "#c84a3a", cursor: "pointer", fontFamily: "inherit", fontSize: 12, fontWeight: 700 }}>
            ✕ Clear entries
          </button>
        )}
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--signal-text-dim)", alignSelf: "center" }}>
          {activeProject && <span style={{ fontWeight: 700, marginRight: 6 }}>📁 {activeProject.project_name}</span>}
          {entries.length} {entries.length === 1 ? "entry" : "entries"}
        </span>
      </div>

      {/* Multi-URL dropdown panel — mirrors batch generate style */}
      {crawlMode === "multi" && (
        <div style={{ border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)", padding: 14, marginBottom: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 10, letterSpacing: "0.08em" }}>
            {t.batchTitle ? t.batchTitle.replace("CHARACTER GENERATION", "LORE GENERATION") : ":: BATCH LORE GENERATION"}
          </div>
          <div style={{ fontSize: 12, color: "var(--signal-text-dim)", marginBottom: 10 }}>
            {t.loreBatchHint || "Paste up to 20 wiki URLs — each will be scraped and generated as a lore entry."}
          </div>
          {multiUrls.map((u, i) => (
            <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
              <input
                value={u}
                onChange={e => updateMultiUrl(i, e.target.value)}
                placeholder={`https://...fandom.com/wiki/Page${i + 1}`}
                style={{ ...inputStyle, flex: 1 }}
              />
              {multiUrls.length > 2 && (
                <button className="signal-btn" onClick={() => removeMultiUrl(i)}
                  style={{ padding: "0 12px", border: "1px solid #c84a3a", color: "#c84a3a", background: "transparent", cursor: "pointer", fontFamily: "inherit", fontSize: 13 }}>
                  ✕
                </button>
              )}
            </div>
          ))}
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            {multiUrls.length < 20 && (
              <button className="signal-btn" onClick={addMultiUrl}
                style={{ ...btnStyle, fontSize: 12 }}>
                + {t.addUrl || "Add URL"}
              </button>
            )}
            <button
              className="signal-btn"
              onClick={handleStartCrawl}
              disabled={loading || multiUrls.filter(u => u.trim()).length === 0}
              style={{ ...btnStyle, fontWeight: 700 }}
            >
              {loading ? (t.working || "Working...") : `⟳ ${t.generateAll || "Generate All"} (${multiUrls.filter(u => u.trim()).length})`}
            </button>
          </div>
        </div>
      )}



      {/* Job status */}
      {job && <MainJobStatus job={job} mode="lore" />}

      {error && (
        <div style={{ color: "#c84a3a", fontSize: 13, marginBottom: 10, padding: "8px 12px", border: "1px solid #c84a3a" }}>
          ⊗ {error}
        </div>
      )}

      {/* Generate from prompt panel */}
      {showGenPanel && (
        <div style={{ border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)", padding: 14, marginBottom: 10 }}>
          <div style={{ fontSize: 11, letterSpacing: "0.1em", color: "var(--signal-text-dim)", marginBottom: 8 }}>GENERATE SINGLE ENTRY FROM PROMPT</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
            <input value={genTitle} onChange={e => setGenTitle(e.target.value)}
              placeholder="Title (optional — model will suggest)"
              style={{ ...inputStyle, fontSize: 13 }} />
            <select value={genType} onChange={e => setGenType(e.target.value)} style={{ ...inputStyle }}>
              {["character","place","faction","event","item","ability","concept","other"].map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <textarea
            value={genPrompt}
            onChange={e => setGenPrompt(e.target.value)}
            rows={4}
            placeholder="Paste any text, description, or notes about this entry... The model will generate keywords and content from it."
            style={{ ...inputStyle, resize: "vertical", marginBottom: 8 }}
          />
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button className="signal-btn" onClick={() => setShowGenPanel(false)} style={{ ...btnStyle, fontSize: 12 }}>Cancel</button>
            <button className="signal-btn" onClick={handleGenerateEntry} disabled={generating || !genPrompt.trim()}
              style={{ ...btnStyle, opacity: generating || !genPrompt.trim() ? 0.5 : 1, background: "var(--signal-btn-active-bg)", color: "var(--signal-btn-active-text)" }}>
              {generating ? (t.working || "Generating...") : "⟳ " + (t.generateAndSave || "Generate & Save")}
            </button>
          </div>
        </div>
      )}

      {/* Project panel */}
      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 12, marginBottom: 12 }}>
        <div className="signal-panel" style={{ border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)", padding: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--signal-text-dim)", marginBottom: 8 }}>
            PROJECTS
          </div>

          {/* New project input */}
          <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
            <input
              value={newProjectName}
              onChange={e => setNewProjectName(e.target.value)}
              onKeyDown={async e => {
                if (e.key === "Enter" && newProjectName.trim()) {
                  const p = await createLoreProject(newProjectName.trim());
                  setProjects(prev => [p, ...prev]);
                  setActiveProject(p);
                  setNewProjectName("");
                }
              }}
              placeholder={t.newProject || "New project..."}
              style={{ ...inputStyle, flex: 1, padding: "5px 8px", fontSize: 12 }}
            />
            <button className="signal-btn" onClick={async () => {
              if (!newProjectName.trim()) return;
              const p = await createLoreProject(newProjectName.trim());
              setProjects(prev => [p, ...prev]);
              setActiveProject(p);
              setNewProjectName("");
            }} style={{ padding: "0 8px", border: "1px solid var(--signal-border)", cursor: "pointer", fontFamily: "inherit", fontWeight: 700 }}>+</button>
          </div>

          {/* All entries option */}
          <div
            onClick={() => setActiveProject(null)}
            style={{
              padding: "6px 8px", marginBottom: 4, cursor: "pointer", fontSize: 12,
              border: "1px solid var(--signal-border)",
              background: activeProject === null ? "var(--signal-btn-active-bg)" : "transparent",
              color: activeProject === null ? "var(--signal-btn-active-text)" : "var(--signal-text-dim)",
              fontStyle: "italic",
            }}
          >
            All entries
          </div>

          {/* Project list */}
          {projects.map(p => (
            <div key={p.id} style={{ marginBottom: 3 }}>
              {renamingId === p.id ? (
                <input
                  autoFocus
                  value={renameVal}
                  onChange={e => setRenameVal(e.target.value)}
                  onBlur={async () => {
                    if (renameVal.trim()) {
                      await renameLoreProject(p.id, renameVal.trim());
                      setProjects(prev => prev.map(x => x.id === p.id ? { ...x, project_name: renameVal.trim() } : x));
                      if (activeProject?.id === p.id) setActiveProject(prev => ({ ...prev, project_name: renameVal.trim() }));
                    }
                    setRenamingId(null);
                  }}
                  onKeyDown={e => e.key === "Enter" && e.target.blur()}
                  style={{ ...inputStyle, padding: "4px 6px", fontSize: 12, width: "100%" }}
                />
              ) : (
                <div
                  onClick={() => setActiveProject(p)}
                  style={{
                    padding: "6px 8px", cursor: "pointer", fontSize: 12,
                    border: "1px solid var(--signal-border)",
                    background: activeProject?.id === p.id ? "var(--signal-btn-active-bg)" : "var(--signal-bg-btn)",
                    color: activeProject?.id === p.id ? "var(--signal-btn-active-text)" : "var(--signal-text)",
                    display: "flex", justifyContent: "space-between", alignItems: "center", gap: 4,
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.project_name}</div>
                    <div style={{ fontSize: 10, opacity: 0.6 }}>{p.entry_count} entries</div>
                  </div>
                  <div style={{ display: "flex", gap: 3, flexShrink: 0 }}>
                    <button onClick={e => { e.stopPropagation(); setRenamingId(p.id); setRenameVal(p.project_name); }}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", fontSize: 11, opacity: 0.6, padding: "0 2px" }}>✎</button>
                    <button onClick={async e => {
                      e.stopPropagation();
                      if (deletingProjectId === p.id) {
                        await deleteLoreProject(p.id);
                        setProjects(prev => prev.filter(x => x.id !== p.id));
                        if (activeProject?.id === p.id) { setActiveProject(null); }
                        setDeletingProjectId(null);
                        loadEntries();
                      } else {
                        setDeletingProjectId(p.id);
                      }
                    }} style={{
                      background: deletingProjectId === p.id ? "#c84a3a" : "none",
                      border: "none", cursor: "pointer",
                      color: deletingProjectId === p.id ? "#fff" : "#c84a3a",
                      fontSize: 11, padding: "0 2px",
                    }}>
                      {deletingProjectId === p.id ? "?" : "✕"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {projects.length === 0 && (
            <div style={{ fontSize: 11, color: "var(--signal-text-dim)", textAlign: "center", padding: "8px 0" }}>
              No projects yet
            </div>
          )}
        </div>

        {/* Right side placeholder when no entries */}
        <div style={{ minWidth: 0 }}>

      {/* Main editor area */}
      {entries.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 12, alignItems: "start" }}>

          {/* Entry list */}
          <div className="signal-panel" style={{ border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)", padding: 10 }}>
            {/* Filter + search */}
            <div style={{ marginBottom: 8, display: "flex", flexDirection: "column", gap: 6 }}>
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder={t.searchEntries || "Search entries..."}
                style={{ ...inputStyle, fontSize: 12, padding: "6px 10px" }}
              />
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {["all", ...ENTRY_TYPES].map(type => (
                  <button
                    key={type}
                    className={filterType === type ? "signal-btn signal-btn-active" : "signal-btn"}
                    onClick={() => setFilterType(type)}
                    style={{ padding: "3px 8px", fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", border: "1px solid var(--signal-border)", cursor: "pointer", fontFamily: "inherit" }}
                  >
                    {(t.entryTypes && t.entryTypes[type]) || type.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 600, overflowY: "auto" }}>
              {filteredEntries.map(e => (
                <div
                  key={e.id}
                  onClick={() => { if (movingEntryId !== e.id) handleSelectEntry(e.id); }}
                  className={flashEntry === e.id ? "signal-field-flash" : deletingEntry === e.id ? "signal-entry-delete-flash" : ""}
                  style={{
                    padding: "8px 10px",
                    border: `1px solid ${deletingEntry === e.id ? "#c84a3a" : "var(--signal-border)"}`,
                    background: deletingEntry === e.id ? "rgba(200,74,58,0.15)" : selectedId === e.id ? "var(--signal-btn-active-bg)" : "var(--signal-bg-btn)",
                    color: selectedId === e.id ? "var(--signal-btn-active-text)" : "var(--signal-text)",
                    cursor: "pointer",
                    transition: "background 0.2s, border-color 0.2s",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {e.title || "Untitled"}
                      </div>
                      <div style={{ fontSize: 10, opacity: 0.6, letterSpacing: "0.06em" }}>
                        {(t.entryTypes && t.entryTypes[e.entry_type]) || e.entry_type?.toUpperCase()}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 3, flexShrink: 0 }}>
                      <button
                        onClick={ev => { ev.stopPropagation(); setMovingEntryId(movingEntryId === e.id ? null : e.id); }}
                        title={t.moveToProject || "Move to project"}
                        style={{ padding: "2px 5px", fontSize: 10, fontWeight: 700, border: "1px solid var(--signal-border)", background: movingEntryId === e.id ? "var(--signal-btn-active-bg)" : "transparent", color: movingEntryId === e.id ? "var(--signal-btn-active-text)" : "var(--signal-text-dim)", cursor: "pointer", fontFamily: "inherit" }}
                      >↪</button>
                      <button
                        onClick={(ev) => handleDeleteEntry(e.id, ev)}
                        style={{ padding: "2px 6px", fontSize: 10, fontWeight: 700, border: `1px solid ${deleteConfirm === e.id ? "#c84a3a" : "var(--signal-border)"}`, background: deleteConfirm === e.id ? "#c84a3a" : "transparent", color: deleteConfirm === e.id ? "#fff" : "#c84a3a", cursor: "pointer", fontFamily: "inherit" }}
                      >
                        {deleteConfirm === e.id ? "?" : "✕"}
                      </button>
                    </div>
                  </div>
                  {movingEntryId === e.id && (
                    <div style={{ marginTop: 6 }} onClick={ev => ev.stopPropagation()}>
                      <select
                        defaultValue={e.crawl_id ?? "none"}
                        onChange={ev => handleMoveEntry(e.id, ev.target.value)}
                        style={{ width: "100%", padding: "4px 6px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-input)", color: "var(--signal-text)", fontFamily: "inherit", fontSize: 12 }}
                      >
                        <option value="none">{t.noProject || "No Project"}</option>
                        {projects.map(p => (
                          <option key={p.id} value={p.id}>{p.project_name}</option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              ))}
              {filteredEntries.length === 0 && (
                <div style={{ color: "var(--signal-text-dim)", fontSize: 12, textAlign: "center", padding: 12 }}>
                  No entries found
                </div>
              )}
            </div>
          </div>

          {/* Entry editor */}
          {entry ? (
            <section
              className={`signal-panel signal-screen-panel${flashEntry === selectedId ? " signal-field-flash" : ""}`}
              style={{
                border: "1px solid var(--signal-border)", background: "var(--signal-bg-field)",
                padding: 16, position: "sticky", top: 16, alignSelf: "start",
              }}>
              {/* Title */}
              <input
                value={entry.title || ""}
                onChange={e => setEntry(prev => ({ ...prev, title: e.target.value }))}
                style={{
                  ...inputStyle, fontWeight: 700, fontSize: 18,
                  borderLeft: "none", borderRight: "none", borderTop: "none",
                  textAlign: "center", marginBottom: 8,
                }}
              />

              {/* Type selector */}
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 12 }}>
                {ENTRY_TYPES.map(type => (
                  <button
                    key={type}
                    className={entry.entry_type === type ? "signal-btn signal-btn-active" : "signal-btn"}
                    onClick={() => setEntry(prev => ({ ...prev, entry_type: type }))}
                    style={{ padding: "4px 8px", fontSize: 11, border: "1px solid var(--signal-border)", cursor: "pointer", fontFamily: "inherit", fontWeight: 700 }}
                  >
                    {(t.entryTypes && t.entryTypes[type]) || type}
                  </button>
                ))}
              </div>

              {/* Keywords */}
              <div className="signal-divider" style={{ marginBottom: 8 }}>
                <div className="signal-divider-mark signal-divider-mark-left" />
                <div className="signal-divider-bar" />
                <span className="signal-divider-label">Keys / Triggers</span>
                <div className="signal-divider-bar" />
                <div className="signal-divider-mark signal-divider-mark-right" />
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 8 }}>
                {(entry.keywords || []).map(kw => (
                  <span key={kw} style={{
                    padding: "3px 8px", border: "1px solid var(--signal-border)",
                    background: "var(--signal-bg-mid)", fontSize: 12, fontFamily: "monospace",
                    display: "flex", alignItems: "center", gap: 4,
                  }}>
                    {kw}
                    <button onClick={() => removeKeyword(kw)} style={{
                      background: "none", border: "none", cursor: "pointer", color: "#c84a3a",
                      padding: 0, fontSize: 12, lineHeight: 1,
                    }}>✕</button>
                  </span>
                ))}
              </div>

              <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
                <input
                  value={newKeyword}
                  onChange={e => setNewKeyword(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && addKeyword()}
                  placeholder="Add keyword... (Enter)"
                  style={{ ...inputStyle, flex: 1, fontSize: 13, padding: "6px 10px" }}
                />
                <button className="signal-btn" onClick={addKeyword}
                  style={{ ...btnStyle, padding: "6px 12px" }}>+</button>
              </div>

              {/* Content */}
              <div className="signal-divider" style={{ marginBottom: 8 }}>
                <div className="signal-divider-mark signal-divider-mark-left" />
                <div className="signal-divider-bar" />
                <span className="signal-divider-label">Content</span>
                <div className="signal-divider-bar" />
                <div className="signal-divider-mark signal-divider-mark-right" />
              </div>

              <textarea
                value={entry.content || ""}
                onChange={e => setEntry(prev => ({ ...prev, content: e.target.value }))}
                rows={12}
                style={{ ...inputStyle, resize: "vertical" }}
              />

              {/* SillyTavern lorebook settings */}
              <div className="signal-divider" style={{ margin: "12px 0 10px" }}>
                <div className="signal-divider-mark signal-divider-mark-left" />
                <div className="signal-divider-bar" />
                <span className="signal-divider-label">{t.stDepthHint || "SillyTavern settings"}</span>
                <div className="signal-divider-bar" />
                <div className="signal-divider-mark signal-divider-mark-right" />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 14 }}>
                {[
                  { key: "scan_depth", label: t.scanDepth || "Scan Depth", min: 1, max: 20, def: 2, hint: "How many recent messages to scan for trigger keywords" },
                  { key: "insertion_order", label: t.insertionOrder || "Insertion Order", min: 0, max: 1000, def: 100, hint: "Priority order — lower number = inserted first" },
                  { key: "entry_depth", label: t.entryDepth || "Entry Depth", min: 0, max: 20, def: 4, hint: "Where in context to insert (0 = top)" },
                ].map(({ key, label, min, max, def, hint }) => (
                  <div key={key} title={hint}>
                    <div style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--signal-text-dim)", marginBottom: 4 }}>{label}</div>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <input
                        type="range"
                        min={min} max={max}
                        value={entry[key] ?? def}
                        onChange={e => setEntry(prev => ({ ...prev, [key]: parseInt(e.target.value) }))}
                        style={{ flex: 1, accentColor: "var(--signal-text)" }}
                      />
                      <span style={{ fontSize: 12, fontWeight: 700, minWidth: 28, textAlign: "right" }}>
                        {entry[key] ?? def}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Save */}
              <div style={{ display: "flex", gap: 8, marginTop: 10, justifyContent: "flex-end" }}>
                <button className="signal-btn" onClick={handleSaveEntry} disabled={saving}
                  style={{ ...btnStyle, opacity: saving ? 0.5 : 1 }}>
                  {saving ? (t.saving || "Saving...") : (t.saveEntry || "Save Entry")}
                </button>
              </div>
            </section>
          ) : (
            <div style={{ color: "var(--signal-text-dim)", textAlign: "center", padding: 40, fontSize: 14 }}>
              Select an entry to edit
            </div>
          )}
        </div>
      )}

      {!entries.length && !job && (
        <div style={{
          border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)",
          padding: 40, textAlign: "center", color: "var(--signal-text-dim)",
        }}>
          <div style={{ fontSize: 14, marginBottom: 8 }}>No lore entries yet.</div>
          <div style={{ fontSize: 12 }}>
            {activeProject ? `Create a project and generate entries.` : "Select a project or generate entries."}
          </div>
        </div>
      )}
        </div>{/* end right side */}
      </div>{/* end project grid */}
    </div>
  );
}
