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
import { markBusy } from "../../lib/leaveGuard";
import { InterviewPanel, TrimButton } from "./AssistPanels";
import { onHelperChange, registerHelperFlush, setHelperContext } from "../../lib/helperBus";
import { getGreetingStyle, setGreetingStyle } from "../../lib/greetingStyle";
import NierMenu, { MenuItem, MenuLabel, MenuSep } from "../shared/NierMenu";
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
  exportCardV2,
  listLoreProjects,
  getPresets,
  renameCard,
  scanCardProse, setCardImage, uploadImage, loadCard, importCard } from "../../lib/api";

// ── static card audit (no model call): what would make this card weaker in SillyTavern ──
function auditCard(card) {
  const issues = [];
  let score = 100;
  const tok = (x) => Math.round(String(x || "").length / 4);
  const add = (sev, msg, cost) => { issues.push([sev, msg]); score -= cost; };
  for (const f of ["description", "personality", "scenario", "first_mes", "mes_example"]) {
    if (!String(card[f] || "").trim()) add("high", `${f.replace("_", " ")} is empty`, 12);
  }
  const perm = tok(card.description) + tok(card.personality) + tok(card.scenario);
  if (perm > 1500) add("med", `About ${perm} permanent tokens: trim the description or move world detail into a lorebook`, 8);
  if (card.description && tok(card.description) < 60) add("med", "Description is very short", 5);
  const mes = String(card.mes_example || "").trim();
  if (mes && !mes.startsWith("<START>")) add("med", "Example messages don't start with <START>", 6);
  if (/<START>[^\n]/.test(mes)) add("low", "A <START> marker is not on its own line", 3);
  if (/(^|\n)\{\{user\}\}:/.test(mes)) add("low", "Example messages include {{user}} lines", 3);
  const fm = String(card.first_mes || "");
  if (/(^|\n)\s*\{\{user\}\}\s*:/.test(fm) || /\*\{\{user\}\}\s+\w+s\b/.test(fm)) add("high", "First message speaks or acts for {{user}}", 10);
  if (tok(fm) > 400) add("low", "First message is long; replies tend to copy its length", 3);
  const tags = Array.isArray(card.tags) ? card.tags : [];
  if (tags.length < 10) add("low", `${tags.length} tags (aim for 10-20)`, 4);
  if (!(card.alternate_greetings || []).length) add("low", "No alternate greetings", 2);
  if (!String(card.depth_prompt || "").trim()) add("low", "No Character's Note (helps long chats stay in character)", 2);
  const sent = (x) => new Set(String(x || "").toLowerCase().split(/[.!?]\s+/).map((y) => y.trim()).filter((y) => y.length > 25));
  const a = sent(card.description), b = sent(card.personality);
  let dup = 0; a.forEach((x) => { if (b.has(x)) dup += 1; });
  if (dup >= 2) add("med", "Description and personality repeat the same sentences", 5);
  const sp = card.structured_profile || {};
  const ageNum = String(sp.age || "").match(/\d+/);
  if (ageNum) {
    const descAges = [...String(card.description || "").matchAll(/\b(\d{1,3})[- ]years?[- ]old\b/gi)].map((m) => m[1]);
    if (descAges.length && !descAges.includes(ageNum[0])) add("high", `Age ${ageNum[0]} in the profile but ${descAges[0]} in the description`, 8);
    if (parseInt(ageNum[0]) < 18 && ((sp.kinks || []).length || (sp.personal_parts || []).length || String(sp.sexual_attraction || "").trim()))
      add("high", "Under-18 character has sexual profile fields filled", 20);
  }
  const first = String(card.name || "").split(" ")[0];
  if (first && card.description && !card.description.includes(first) && !/\{\{char\}\}/.test(card.description))
    add("low", "Description never names the character", 2);
  // lessons from r/SillyTavernAI: what makes cards misbehave in long chats
  const desc = String(card.description || "") + " " + String(card.personality || "");
  const trauma = (desc.match(/\b(trauma\w*|abus\w*|tortur\w*|PTSD|nightmares?|scar(red|s)? by|haunted by|grief|griev\w*|orphan\w*|massacre\w*)\b/gi) || []).length;
  if (trauma >= 3) add("med", "The description dwells on a painful past: models tend to bring it up constantly. Keep one line here and move the backstory into a lorebook entry", 5);
  const absolutes = (desc.match(/\b(always|never|every time|constantly|at all times)\b/gi) || []).length;
  if (absolutes >= 5) add("low", `${absolutes} "always/never" rules: very specific cards get parroted back. Show it in example messages instead`, 3);
  if (perm > 900) add("low", "Big for group chats: in a group every card is in context at once. Consider a 'lean' version for groups", 2);
  if (!String(sp.with_strangers || "").trim() && !String(sp.with_close || "").trim())
    add("low", "No 'with strangers / with people close to them' layers: they make a character feel less one-note", 2);
  else if (String(sp.with_strangers || "").trim() && String(sp.with_strangers).trim() === String(sp.with_close || "").trim())
    add("low", "'With strangers' and 'with people close to them' say the same thing", 2);
  return { score: Math.max(0, score), issues, perm };
}

/** closes a dialog on Escape while it is mounted */
function EscapeCloses({ onClose }) {
  useEffect(() => {
    const k = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return null;
}

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
  pendingHandoff = null,        // from TEXT "Make card": {lore_project_id, story_point}
  clearPendingHandoff,
  onLoadCard,                   // App's loader: puts a saved card (and its source and portrait) in the studio
}) {
  const [loading, setLoading] = useState(false);
  const importRef = useRef(null);
  const [error, setError] = useState("");
  // lorebook embedded in exported cards (data.character_book); remembered per card
  const [loreProjects, setLoreProjects] = useState([]);
  const [attachLore, setAttachLore] = useState("");
  useEffect(() => {
    listLoreProjects().then((p) => setLoreProjects(p || [])).catch(() => {});
    getPresets().then((p) => { if (p?.card?.model) { setProvider(p.card.provider || "nanogpt"); setModel(p.card.model); } }).catch(() => {});
  }, []);
  useEffect(() => {
    let v = "";
    try { v = (cardId && localStorage.getItem(`ccs-card-lore-${cardId}`)) || ""; } catch {}
    setAttachLore(v);
  }, [cardId]);
  useEffect(() => {
    if (!pendingHandoff) return;
    if (pendingHandoff.story_point) { setStoryPoint(pendingHandoff.story_point); setGenOpen(true); }
  }, [pendingHandoff]);
  useEffect(() => {   // once the card from a TEXT hand-off exists, attach that story's lorebook to it
    if (pendingHandoff?.lore_project_id && cardId && card) {
      chooseLore(String(pendingHandoff.lore_project_id));
      clearPendingHandoff && clearPendingHandoff();
    }
  }, [cardId]);

  // a lorebook attached from elsewhere (an import, TEXT) must be in the list, or the menu shows "No lorebook attached"
  const loreFetchedFor = useRef("");
  useEffect(() => {
    if (attachLore && loreFetchedFor.current !== String(attachLore) && !loreProjects.some((p) => String(p.id) === String(attachLore))) {
      loreFetchedFor.current = String(attachLore);      // once per lorebook, so a deleted one can't loop
      listLoreProjects().then((p) => setLoreProjects(p || [])).catch(() => {});
    }
  }, [attachLore, loreProjects]);
  function chooseLore(v) {
    setAttachLore(v);
    try { if (cardId) localStorage.setItem(`ccs-card-lore-${cardId}`, v); } catch {}
  }
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
  const NATURAL_FIELDS = new Set(["description","personality","scenario","first_mes","mes_example","tags","depth_prompt","system_prompt"]);
  const FIELD_LABELS = { depth_prompt: "Character's Note", system_prompt: "System Prompt", story_point: "story point",
    with_strangers: "With strangers", with_close: "With people close to them" };
  const fieldLabel = (f) => (t.fields && t.fields[f]) || FIELD_LABELS[f] || f.replaceAll("_", " ");

  // generation options (sent with Generate Card)
  const [genOpen, setGenOpen] = useState(false);
  const [storyPoint, setStoryPoint] = useState("");
  const [userRole, setUserRole] = useState("");
  const [tokenTarget, setTokenTarget] = useState("standard");
  const [cardStyle, setCardStyle] = useState("prose");
  const [deepGen, setDeepGen] = useState(false);
  const [greetStyle, setGreetStyleState] = useState(getGreetingStyle);
  const setGreetStyle = (k, v) => setGreetStyleState((s) => { const n = { ...s, [k]: v }; setGreetingStyle(n); return n; });
  const [genWarnings, setGenWarnings] = useState([]);
  const [audit, setAudit] = useState(null);
  const [interviewOpen, setInterviewOpen] = useState(false);
  // portraits: whatever image is showing is saved to data/images and attached once the card has an id
  const imageNames = useRef({});        // shown URL -> stored file name (uploads, wiki pictures)
  const attached = useRef("");          // "cardId:name" last attached, so card edits don't re-send it
  useEffect(() => {
    if (!cardId || !card || !imageUrl) return;
    let alive = true;
    (async () => {
      let name = imageUrl.startsWith("/api/images/") ? imageUrl.slice(12) : imageNames.current[imageUrl];
      if (!name) {
        try {
          const blob = await (await fetch(imageUrl)).blob();
          name = await uploadImage(blob);
          imageNames.current[imageUrl] = name;
        } catch { return; }       // a wiki picture that can't be fetched just stays unsaved
      }
      const key = `${cardId}:${name}`;
      if (!alive || attached.current === key || card.image === name) { attached.current = key; return; }
      try { await setCardImage(cardId, name); attached.current = key; if (alive) setCard((c) => (c && (c.id == null || c.id === cardId) ? { ...c, image: name } : c)); }
      catch { /* shown again next time the card changes */ }
    })();
    return () => { alive = false; };
  }, [cardId, card, imageUrl, setCard]);
  // AUDIT: instant checks here, plus the stock-phrase scan from the backend (also no model call)
  async function runAudit() {
    const a = auditCard(card || {});
    setAudit(a);
    try {
      const r = await scanCardProse(card || {});
      if (r.warnings?.length) {
        setAudit({ ...a, score: Math.max(0, a.score - Math.min(10, r.warnings.length * 2)),
          issues: [...a.issues, ...r.warnings.map((w) => ["low", `Stock phrase: ${w}`])] });
      }
    } catch { /* the instant checks are still shown */ }
  }
  // per-field history of regenerations: undo / redo
  const [fieldHistory, setFieldHistory] = useState({});   // field -> {undo: [], redo: []}

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

      // never overwrite a card already made from this source: generate a new one, the old one stays in the library
      const keepOld = !!(card && cardId && card.source_id === sourceId);
      const opts = { token_target: tokenTarget, style: cardStyle, deep: deepGen };
      if (storyPoint.trim()) opts.story_point = storyPoint.trim();
      if (userRole.trim()) opts.user_role = userRole.trim();
      const loreForGen = attachLore || pendingHandoff?.lore_project_id;
      if (loreForGen) opts.lore_project_id = loreForGen;
      setGenWarnings([]); setAudit(null);
      const data = await startCharacterGenerate(sourceId, provider, model, keepOld, opts);

      pollJob(data.job_id, (jobData) => {
        if (keepOld && showToast) showToast("Saved as a new card; the previous version is still in the Library");
        setGenWarnings(jobData.result?.warnings || []);
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

  // autosave: 1.5 s after the last edit, compared against the last saved copy of this card
  const cardBaseline = useRef("");
  const [cardDirty, setCardDirty] = useState(false);
  // closing the tab mid-generation or before the autosave ran asks first
  useEffect(() => { markBusy("character", loading || cardDirty); return () => markBusy("character", false); }, [loading, cardDirty]);
  useEffect(() => {
    cardBaseline.current = card ? JSON.stringify(card) : "";
    setCardDirty(false);
  }, [cardId]);
  useEffect(() => {
    if (!card || !cardId) return;
    const json = JSON.stringify(card);
    const changed = json !== cardBaseline.current;
    setCardDirty(changed);
    if (!changed || typingField) return;
    const tm = setTimeout(async () => {
      try { await saveCard(cardId, card); cardBaseline.current = json; setCardDirty(false); }
      catch (e) { setError(`Autosave failed: ${e.message}`); }
    }, 1500);
    return () => clearTimeout(tm);
  }, [card, cardId, typingField]);

  // the helper side panel: what is open, save before it reads, reload what it changed
  const cardRef = useRef(card);
  cardRef.current = card;
  useEffect(() => {
    setHelperContext("character", { card_id: cardId || null, label: card?.name || "", provider, model });
  }, [cardId, card?.name, provider, model]);
  useEffect(() => registerHelperFlush("character", async () => {
    const c = cardRef.current;
    if (c && cardId && JSON.stringify(c) !== cardBaseline.current) {
      await saveCard(cardId, c);
      cardBaseline.current = JSON.stringify(c);
      setCardDirty(false);
    }
  }), [cardId]);
  useEffect(() => onHelperChange(async (touched) => {
    if (!cardId || !touched.some((x) => x.kind === "card" && x.id === cardId)) return;
    if (cardRef.current && JSON.stringify(cardRef.current) !== cardBaseline.current) {
      showToast && showToast("You edited this card while the helper worked: your version was kept");
      return;
    }
    try {
      const { card: fresh } = await loadCard(cardId);
      cardBaseline.current = JSON.stringify(fresh);       // what the server has: nothing to autosave
      setCard(fresh);
    } catch {                                             // undo removed a card the helper had created
      setCard(null); setCardId(null);
    }
  }), [cardId]);    // re-subscribed per card; the latest card is read through cardRef

  // Field regen timer
  useEffect(() => {
    if (!fieldBusy) { setFieldElapsed(0); return; }
    setFieldElapsed(0);
    const id = setInterval(() => setFieldElapsed(s => s + 1), 1000);
    return () => clearInterval(id);
  }, [fieldBusy]);

  // NEW ▾ > Import card: a card PNG / JSON / CHARX becomes a new card; its embedded lorebook becomes a LORE project
  async function handleImportCard(file) {
    try {
      setError("");
      const r = await importCard(file);
      if (r.lore_project_id) {
        try { localStorage.setItem(`ccs-card-lore-${r.card_id}`, String(r.lore_project_id)); } catch { /* attach it by hand */ }
      }
      if (onLoadCard) await onLoadCard(r.card_id);
      showToast?.(`Imported ${r.name}` + (r.entries ? ` with a ${r.entries}-entry lorebook (now in LORE)` : ""));
      (r.warnings || []).forEach((w) => showToast?.(w));
    } catch (e) {
      setError(e.message);
    }
  }

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
      cardBaseline.current = JSON.stringify(card); setCardDirty(false);
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

  function pushHistory(fieldName, oldValue) {
    setFieldHistory((h) => {
      const cur = h[fieldName] || { undo: [], redo: [] };
      return { ...h, [fieldName]: { undo: [...cur.undo, oldValue].slice(-20), redo: [] } };
    });
  }
  function readField(f) { return NATURAL_FIELDS.has(f) ? card?.[f] : card?.structured_profile?.[f]; }
  function writeField(f, v) {
    if (NATURAL_FIELDS.has(f)) setCard((prev) => ({ ...prev, [f]: v }));
    else setCard((prev) => ({ ...prev, structured_profile: { ...(prev?.structured_profile || {}), [f]: v } }));
  }
  function stepHistory(f, dir) {   // dir -1 = undo, +1 = redo
    const h = fieldHistory[f];
    if (!h) return;
    const from = dir < 0 ? h.undo : h.redo;
    if (!from.length) return;
    const value = from[from.length - 1];
    const current = readField(f);
    setFieldHistory((all) => {
      const c = all[f];
      return dir < 0
        ? { ...all, [f]: { undo: c.undo.slice(0, -1), redo: [...c.redo, current] } }
        : { ...all, [f]: { undo: [...c.undo, current], redo: c.redo.slice(0, -1) } };
    });
    writeField(f, value);
  }

  async function handleRegenerateField(fieldName, options = {}) {
    if (!cardId) return;

    try {
      setError("");
      setFieldBusy(fieldName);
      pushHistory(fieldName, readField(fieldName));

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
      "motivations",
      "flaws",
      "mannerisms",
      "relationships",
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

  async function handleExportCard(spec = "v2") {
    if (!card) return;

    // Always export a real Character Card V2 (spec/data wrapper). In structured
    // view the description is the formatted structured profile.
    const isStructured = characterViewMode === "structured";
    try {
      const data = await exportCardV2(card, isStructured ? "structured" : "natural", attachLore || null, spec);
      const v3 = spec === "v3" ? "_v3" : "";
      const filename = isStructured
        ? `${card.name || "card"}_structured${v3}.json`
        : `${card.name || "card"}${v3}.json`;
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(objectUrl);
    } catch (e) {
      showToast && showToast(`Export failed: ${e.message}`);
    }
  }

  // .charx: Character Card V3 zip with the portrait inside (SillyTavern, RisuAI and other V3 apps import it)
  async function handleExportCharx() {
    if (!card) return;
    try {
      let image;
      if (!card.image && imageUrl) {          // a picture not saved yet: send it along
        const blob = await (await fetch(imageUrl)).blob();
        image = await new Promise((res) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(blob); });
      }
      const r = await fetch("/api/export/charx", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ card, mode: characterViewMode, lore_project_id: attachLore || null, image }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${(card.name || "card").replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "_") || "card"}.charx`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      showToast && showToast(`Export failed: ${e.message}`);
    }
  }

  return (
    <>
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

      {/* Row 2: actions. Making a card on the left, then New / Tools / Export menus (NieR-style, as in LORE) */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={handleScrape} disabled={loading} className="signal-btn" style={{ ...buttonStyle, whiteSpace: "nowrap" }}>
          {loading ? (t.working || "Working...") : (t.scrape || "Scrape")}
        </button>
        <button onClick={handleGenerate} disabled={loading || !sourceId} className="signal-btn signal-btn-active" style={{ ...buttonStyle, whiteSpace: "nowrap" }}>
          {t.generateCard || "Generate Card"}
        </button>
        <button className={genOpen ? "signal-btn signal-btn-active" : "signal-btn"} style={{ ...buttonStyle, whiteSpace: "nowrap" }}
          onClick={() => setGenOpen((v) => !v)} aria-expanded={genOpen}
          title="Story point, your role, size, style, first message point of view and In-depth mode for Generate Card">
          ⚙ {t.genOptions || "Options"}
        </button>
        <button className={batchMode ? "signal-btn signal-btn-active" : "signal-btn"} onClick={() => { setBatchMode(b => !b); setBatchResults(null); }}
          style={{ ...buttonStyle, whiteSpace: "nowrap" }}>
          {batchMode ? (t.cancelBatch || "Cancel Batch") : (t.batchGenerate || "Batch Generate")}
        </button>

        <div aria-hidden="true" style={{ width: 1, alignSelf: "stretch", background: "var(--signal-border)", opacity: 0.5, margin: "0 4px" }} />

        <NierMenu label={t.newMenu || "NEW"}>
          <MenuItem onClick={handleNewCard}>{t.newCard || "New Card"} (blank)</MenuItem>
          <MenuItem onClick={() => importRef.current?.click()} title="A card PNG, a card .json (V1, V2 or V3) or a .charx">
            {t.importCard || "Import card (PNG, JSON, CHARX)"}…
          </MenuItem>
        </NierMenu>
        <input ref={importRef} type="file" accept=".png,.json,.charx,image/png,application/json" aria-label="Import a card file"
          style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) handleImportCard(f); }} />
        <NierMenu label={t.toolsMenu || "TOOLS"}>
          <MenuItem disabled={!card} why="open a card first" onClick={runAudit} title="Check the card for problems (no model call)">⚖ {t.auditCard || "Audit"}</MenuItem>
          <MenuItem disabled={!card} why="open a card first" onClick={() => setInterviewOpen(true)} title="Ask the character questions to test its voice (one model call per answer, not saved)">◇ {t.interview || "Interview"}</MenuItem>
          <MenuItem disabled={!source} why="scrape a page first" onClick={() => setSourceOpen(true)}>{t.viewSource || "View Source"}</MenuItem>
        </NierMenu>

        <div style={{ flex: 1 }} />
        {card && cardId && (
          <span style={{ fontSize: 12, color: "var(--signal-text-dim)", letterSpacing: "0.14em" }}
            title="Edits are saved automatically 1.5 s after you stop typing">
            {cardDirty ? "● EDITING (AUTOSAVES)" : "✓ SAVED"}
          </span>
        )}
        <NierMenu label={t.exportMenu || "EXPORT"} align="right" disabled={!card} width={300} title={card ? "" : "Open or make a card first"}>
          <MenuItem onClick={() => handleExportCard("v2")} title="Character Card V2 JSON: what SillyTavern and most sites import">
            {characterViewMode === "structured" ? (t.exportStructuredJson || "Export Structured JSON") : (t.exportCardJson || "Export Card JSON")}
          </MenuItem>
          <MenuItem onClick={() => handleExportCard("v3")} title="Character Card V3 JSON (chara_card_v3) for V3-aware sites. PNG exports already carry both V2 and V3">
            {t.exportV3Json || "V3 JSON"}
          </MenuItem>
          <MenuItem onClick={handleExportCharx} title="Character Card V3 .charx: a zip with the card and its portrait (and the attached lorebook). SillyTavern imports it like a PNG">
            {t.exportCharx || "CHARX"}
          </MenuItem>
          <MenuSep />
          <MenuLabel>EMBEDDED LOREBOOK</MenuLabel>
          <div style={{ padding: "4px 14px 10px" }}>
            <select value={attachLore} onChange={(e) => chooseLore(e.target.value)} aria-label="Embedded lorebook"
              title="Embed a LORE project in exported cards (JSON and PNG) as the card's own lorebook"
              style={{ width: "100%", padding: "8px 10px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-field)", color: "var(--signal-text)", fontFamily: "inherit" }}
              onFocus={() => listLoreProjects().then((p) => setLoreProjects(p || [])).catch(() => {})}>
              <option value="">{t.noLorebook || "No lorebook attached"}</option>
              {loreProjects.map((p) => (
                <option key={p.id} value={p.id}>{p.project_name || p.name}</option>
              ))}
            </select>
          </div>
        </NierMenu>
      </div>

      {genOpen && (
        <div style={{ border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)", padding: 14, marginBottom: 12,
          display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10, textAlign: "left" }}>
          <label style={{ fontSize: 11, letterSpacing: "0.08em" }}>STORY POINT
            <input value={storyPoint} onChange={(e) => setStoryPoint(e.target.value)} placeholder="e.g. after the season finale"
              style={{ width: "100%", padding: "8px 10px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-field)", color: "var(--signal-text)", fontFamily: "inherit", boxSizing: "border-box", marginTop: 4 }} />
          </label>
          <label style={{ fontSize: 11, letterSpacing: "0.08em" }}>{"{{USER}}"} IS
            <input value={userRole} onChange={(e) => setUserRole(e.target.value)} placeholder="e.g. a new recruit on the team"
              style={{ width: "100%", padding: "8px 10px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-field)", color: "var(--signal-text)", fontFamily: "inherit", boxSizing: "border-box", marginTop: 4 }} />
          </label>
          <label style={{ fontSize: 11, letterSpacing: "0.08em" }}>SIZE
            <select value={tokenTarget} onChange={(e) => setTokenTarget(e.target.value)}
              style={{ width: "100%", padding: "8px 10px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-field)", color: "var(--signal-text)", fontFamily: "inherit", marginTop: 4 }}>
              <option value="small">Small model (400-600 tokens)</option>
              <option value="lean">Lean (~800)</option>
              <option value="standard">Standard (~1200)</option>
              <option value="rich">Rich (~1800)</option>
            </select>
          </label>
          <label style={{ fontSize: 11, letterSpacing: "0.08em" }}>STYLE
            <select value={cardStyle} onChange={(e) => setCardStyle(e.target.value)}
              style={{ width: "100%", padding: "8px 10px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-field)", color: "var(--signal-text)", fontFamily: "inherit", marginTop: 4 }}>
              <option value="prose">Prose</option>
              <option value="plist">PList + Ali:Chat</option>
            </select>
          </label>
          {[["pov", "FIRST MESSAGE POV", [["", "Model's choice"], ["third", "Third person (she / he / they)"], ["second", "Second person (you)"], ["first", "First person (I)"]]],
            ["tense", "TENSE", [["", "Model's choice"], ["present", "Present"], ["past", "Past"]]],
            ["length", "GREETING LENGTH", [["", "Model's choice"], ["short", "Short (50-100 words)"], ["medium", "Medium (150-250)"], ["long", "Long (300-450)"]]]].map(([k, label, opts]) => (
            <label key={k} style={{ fontSize: 11, letterSpacing: "0.08em" }} title="Used for the first message, alternate greetings and example messages, here and when you regenerate them">{label}
              <select value={greetStyle[k]} onChange={(e) => setGreetStyle(k, e.target.value)}
                style={{ width: "100%", padding: "8px 10px", border: "1px solid var(--signal-border)", background: "var(--signal-bg-field)", color: "var(--signal-text)", fontFamily: "inherit", marginTop: 4 }}>
                {opts.map(([v, t2]) => <option key={v} value={v}>{t2}</option>)}
              </select>
            </label>
          ))}
          <label style={{ fontSize: 12, display: "flex", gap: 8, alignItems: "center", cursor: "pointer" }}>
            <input type="checkbox" checked={deepGen} onChange={(e) => setDeepGen(e.target.checked)} />
            <span><b>In-depth</b>: bible → card → check (3 model calls, fewer invented facts)</span>
          </label>
          <div style={{ fontSize: 11, color: "var(--signal-text-dim)", alignSelf: "center" }}>
            {attachLore || pendingHandoff?.lore_project_id
              ? "A lorebook is attached: the card keeps world facts out of the description."
              : "Attach a lorebook (dropdown above) to keep the card lean."}
          </div>
        </div>
      )}

      {genWarnings.length > 0 && (
        <div style={{ border: "1px solid var(--signal-warn)", padding: "8px 12px", marginBottom: 12, fontSize: 12, textAlign: "left", display: "flex", gap: 8 }}>
          <div style={{ flex: 1 }}>
            <b>Check these:</b>
            <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>{genWarnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
          </div>
          <span style={{ cursor: "pointer" }} onClick={() => setGenWarnings([])} aria-label="Dismiss" role="button">✕</span>
        </div>
      )}

      {audit && (
        <div style={{ border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)", padding: 12, marginBottom: 12, textAlign: "left" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <b style={{ letterSpacing: "0.08em" }}>CARD AUDIT</b>
            <span style={{ fontSize: 20, fontWeight: 700, color: audit.score >= 85 ? "var(--signal-text)" : audit.score >= 60 ? "var(--signal-warn)" : "var(--signal-accent)" }}>{audit.score}/100</span>
            <span style={{ fontSize: 11, color: "var(--signal-text-dim)" }}>~{audit.perm} permanent tokens</span>
            <span style={{ marginLeft: "auto", cursor: "pointer" }} onClick={() => setAudit(null)} role="button" aria-label="Close audit">✕</span>
          </div>
          {card && Math.round(String(card.description || "").length / 4) > 500 && (
            <div style={{ fontSize: 12, marginBottom: 6 }}>
              Description is ~{Math.round(String(card.description).length / 4)} tokens.{" "}
              <TrimButton text={card.description} target={400} kind="card_field" field="description" name={card.name} provider={provider} model={model}
                label="TRIM DESCRIPTION" onAccept={(text) => { pushHistory("description", card.description); writeField("description", text); setAudit(null); }} />
            </div>
          )}
          {audit.issues.length === 0 ? <div style={{ fontSize: 12 }}>No problems found.</div> : (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
              {audit.issues.map(([sev, msg], i) => (
                <li key={i}><b style={{ color: sev === "high" ? "var(--signal-accent)" : sev === "med" ? "var(--signal-warn)" : "var(--signal-text-dim)" }}>{sev.toUpperCase()}</b> {msg}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {interviewOpen && card && <EscapeCloses onClose={() => setInterviewOpen(false)} />}
      {interviewOpen && card && (
        <div onClick={() => setInterviewOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 300,
          display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto" }}>
          <div onClick={(e) => e.stopPropagation()} className="signal-panel" role="dialog" aria-label="Interview"
            style={{ border: "1px solid var(--signal-border)", background: "var(--signal-bg-panel)", width: "min(720px, 100%)", padding: 20, textAlign: "left" }}>
            <div style={{ display: "flex", alignItems: "center", marginBottom: 4 }}>
              <b style={{ letterSpacing: "0.08em" }}>INTERVIEW · {card.name}</b>
              <span style={{ marginLeft: "auto", cursor: "pointer" }} onClick={() => setInterviewOpen(false)} role="button" aria-label="Close interview">✕</span>
            </div>
            <InterviewPanel card={card} provider={provider} model={model} name={card.name} />
          </div>
        </div>
      )}

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
                  style={{ ...buttonStyle, color: "var(--signal-accent)", borderColor: "var(--signal-accent)", padding: "7px 10px" }}
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
            <div key={i} style={{ fontSize: 12, marginBottom: 4, color: "var(--signal-accent)" }}>
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
            loreProjectId={attachLore || null}
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
                    "age", "gender", "pronouns", "species", "ethnicity", "race", "sexual_attraction",
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
                        "depth_prompt",
                        "system_prompt",
                      ]
                    : [
                        // ── Identity ──
                        "age",
                        "gender",
                        "pronouns",
                        "species",
                        "ethnicity",
                        "race",
                        "story_point",
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
                        "motivations",
                        "flaws",
                        "mannerisms",
                        "relationships",
                        "with_strangers",
                        "with_close",
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
                        <span>▸ {fieldLabel(field)}</span>
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
                    border: "1px solid var(--signal-border)",
                    background: "var(--signal-btn-active-bg)",
                    color: "var(--signal-btn-active-text)",
                    fontFamily: "inherit",
                    outline: "none",
                    padding: "8px 10px",
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
                    const label = fieldLabel(selectedField).toUpperCase();
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
                  {(fieldHistory[selectedField]?.undo?.length > 0 || fieldHistory[selectedField]?.redo?.length > 0) && (<>
                    <button className="signal-btn" style={{ ...buttonStyle, opacity: fieldHistory[selectedField]?.undo?.length ? 1 : 0.4 }}
                      disabled={!fieldHistory[selectedField]?.undo?.length} onClick={() => stepHistory(selectedField, -1)}
                      title="Go back to the version before the last regeneration" aria-label="Previous version">↶ {fieldHistory[selectedField]?.undo?.length || 0}</button>
                    <button className="signal-btn" style={{ ...buttonStyle, opacity: fieldHistory[selectedField]?.redo?.length ? 1 : 0.4 }}
                      disabled={!fieldHistory[selectedField]?.redo?.length} onClick={() => stepHistory(selectedField, 1)}
                      title="Forward to the newer version" aria-label="Next version">↷ {fieldHistory[selectedField]?.redo?.length || 0}</button>
                  </>)}
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
