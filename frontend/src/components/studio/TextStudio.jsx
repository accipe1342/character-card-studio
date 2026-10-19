/**
 * TextStudio.jsx — Text -> lorebook (fanfiction / long-form text)
 * =================================================================
 * Third studio beside CHARACTER and LORE.
 *
 * FLOW
 * ----
 * 1. SOURCE   paste text, upload .txt/.md/.html/.epub, or fetch URLs
 *             (AO3 work URLs pull the whole work; "follow next" walks chapters)
 * 2. EXTRACT  one model call per chunk; resumable if some chunks fail
 * 3. REVIEW   edit / merge / delete / keep entities; age flags highlight
 *             characters who are (or may be) under 18
 * 4. COMMIT   kept entities become a NEW project in the LORE studio
 *
 * LAYOUT  (same look as CHARACTER / LORE: title, boxed signal-panels, ornamented headings)
 * ------
 * Left:   saved text projects + new source panel
 * Middle: project pipeline (model, deep/quick, chunks at once, chunks). "Rebuild list" = merge only (no extraction
 *         calls); "Resplit text" (under Chunk size, left) = rechunk, which clears extraction.
 * Right:  entity list + entity editor
 *
 * PROPS
 * -----
 * t, showToast, onOpenLore()   (switches App to the LORE studio)
 *
 * HOW TO EXTEND
 * -------------
 * - New source type: add a tab in SOURCE_TABS and a handler that calls an
 *   ingest function in lib/api.js (backend: backend/text_module.py).
 * - New entity field: add it to text_entities, the PATCH handler and the
 *   editor below.
 */

import React, { useState, useEffect, useRef, useMemo } from "react";
import MainJobStatus from "../shared/MainJobStatus";
import CriticPanel from "./CriticPanel";
import { markBusy } from "../../lib/leaveGuard";
import { DEFAULT_MODELS, Divider, btn, btnPrimary, btnSm, btnTool, headingStyle, hint, input, label, panelStyle, toolbarGrid } from "./textUi";
import {
  getJob, fetchModels,
  textIngest, textIngestFile, textIngestUrls, appendText,
  listTextProjects, getTextProject, deleteTextProject, rechunkTextProject,
  startTextExtract, patchTextEntity, deleteTextEntity, mergeTextEntities, commitTextProject,
  restoreTextEntity, emptyTextTrash, getTextRecap, saveTextRecap, saveRecapPosition, textEntityToSource, makeNarratorCard, startCastCards, writeRecapAI,
  getPresets,
} from "../../lib/api";

const ENTITY_TYPES = ["character", "place", "faction", "event", "item", "ability", "concept"];
const SOURCE_TABS = ["paste", "file", "url"];
const FLAG_STYLE = {
  minor: { bg: "#c84a3a", fg: "#fff", label: "UNDER 18" },
  check: { bg: "#b8860b", fg: "#fff", label: "CHECK AGE" },
  unknown: { bg: "transparent", fg: "var(--signal-text-dim)", label: "AGE ?" },
};

// ---- problem detection for the review list --------------------------------------------------------
const BODY_RE = /^(?:(?:the|his|her|their|its|[\w-]+['\u2019]s)\s+)?(?:[\w-]+\s+)?(?:cock|dick|penis|pussy|vagina|clit|erection|boner|precum|cum|semen|balls|breasts?|tits?|boobs?|nipples?|ass|butt|mouth|lips?|tongue|hands?|fists?|fingers?|arms?|legs?|feet|foot|face|eyes?|hair|ponytail|skin|tears?|tail|claws?|teeth|neck|chest|back|body|cheeks?|thighs?|waist|hips?)$/i;
const JUNK_WORDS = new Set(["sex", "rape", "blowjob", "handjob", "orgasm", "naked", "boredom", "fear", "anger", "joy", "sadness",
  "arousal", "lust", "pain", "pleasure", "floor", "wall", "walls", "room", "corner", "ceiling", "door", "window", "pockets",
  "items", "weapon", "weapons", "transformation", "ground", "air", "light", "darkness", "silence"]);
const normName = (t) => (t || "").toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();

// groups of entries that are really the same thing (same name, or one's alias is the other's name)
function dupGroups(entities) {
  const parent = new Map(entities.map((e) => [e.id, e.id]));
  const find = (x) => { while (parent.get(x) !== x) { parent.set(x, parent.get(parent.get(x))); x = parent.get(x); } return x; };
  const union = (a, b) => { const ra = find(a), rb = find(b); if (ra !== rb) parent.set(ra, rb); };
  const byName = new Map();
  for (const e of entities) {
    const k = normName(e.name);
    if (!k) continue;
    if (byName.has(k)) union(e.id, byName.get(k)); else byName.set(k, e.id);
  }
  for (const e of entities) {
    if (e.entity_type === "event") continue;
    for (const a of e.aliases || []) {
      const o = byName.get(normName(a));
      if (o !== undefined && o !== e.id) {
        const other = entities.find((x) => x.id === o);
        if (other && other.entity_type !== "event") union(e.id, o);
      }
    }
  }
  const groups = new Map();
  for (const e of entities) { const r = find(e.id); groups.set(r, [...(groups.get(r) || []), e]); }
  return [...groups.values()].filter((g) => g.length > 1);
}

// id -> { dup, dupExtra, empty, junk, nokeys }. dupExtra marks every copy except the best one.
function findIssues(entities) {
  const out = new Map();
  for (const e of entities) {
    const nm = (e.name || "").trim();
    out.set(e.id, {
      empty: (e.content || "").trim().length < 15,
      junk: e.entity_type !== "event" && (BODY_RE.test(nm) || JUNK_WORDS.has(normName(nm)) || normName(nm).length < 2),
      nokeys: e.entity_type !== "event" && !(e.keywords || []).length,
    });
  }
  for (const g of dupGroups(entities)) {
    const best = [...g].sort((a, b) => (b.mentions - a.mentions) || ((b.content || "").length - (a.content || "").length))[0];
    for (const e of g) Object.assign(out.get(e.id), { dup: true, dupExtra: e.id !== best.id });
  }
  return out;
}
const issueMatch = (i, kind) => !!i && (kind === "any" ? (i.dup || i.empty || i.junk || i.nokeys) : i[kind]);

function IssueBadges({ i }) {
  if (!i) return null;
  const chip = (txt, bg, title) => (
    <span title={title} style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px", background: bg, color: "#fff", letterSpacing: "0.04em" }}>{txt}</span>
  );
  return (<>
    {i.dup && chip("DUP", "#b8860b", "Another entry has the same name or alias")}
    {i.empty && chip("EMPTY", "#c84a3a", "Almost no content")}
    {i.junk && chip("JUNK?", "#c84a3a", "Looks like a body part, act, feeling or scenery rather than lore")}
    {i.nokeys && chip("NO KEYS", "#6b6b6b", "No trigger keywords, so it will never load")}
  </>);
}

const TIER_STYLE = {
  main: { label: "MAIN", title: "Mentioned across many chunks", bg: "var(--signal-btn-active-bg)", fg: "var(--signal-btn-active-text)" },
  supporting: { label: "SUP", title: "Mentioned in 2+ chunks", bg: "transparent", fg: "var(--signal-text)" },
  "one-off": { label: "1×", title: "Mentioned in one chunk only", bg: "transparent", fg: "var(--signal-text-dim)" },
};
function TierBadge({ tier }) {
  const s = TIER_STYLE[tier];
  if (!s) return null;
  return <span title={s.title} style={{ fontSize: 10, fontWeight: 700, padding: "1px 5px", background: s.bg, color: s.fg,
    border: "1px solid var(--signal-border)", letterSpacing: "0.04em" }}>{s.label}</span>;
}
function OriginBadge({ origin }) {
  if (origin !== "altered" && origin !== "original") return null;
  return <span title={origin === "original" ? "Invented by this story" : "From canon, but changed by this story"}
    style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px", background: "#4a6a8a", color: "#fff", letterSpacing: "0.04em" }}>
    {origin === "original" ? "FIC" : "ALT"}</span>;
}
const relToText = (rels) => (rels || []).map((r) => `${r.with} — ${r.relation}`).join("\n");
const textToRel = (txt) => (txt || "").split("\n").map((ln) => {
  const m = ln.split(/\s+[—–-]\s+|:\s+/);
  const w = (m[0] || "").trim(), rel = m.slice(1).join(" ").trim();
  return w && rel ? { with: w, relation: rel } : null;
}).filter(Boolean);

function Flag({ flag }) {
  const f = FLAG_STYLE[flag];
  if (!f) return null;
  return (
    <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px", background: f.bg, color: f.fg,
      border: flag === "unknown" ? "1px solid var(--signal-border)" : "none", letterSpacing: "0.05em" }}>
      {f.label}
    </span>
  );
}

const csv = (arr) => (arr || []).join(", ");
const fromCsv = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function TextStudio({ t = {}, showToast, onOpenLore, onMakeCard, focus, clearFocus }) {
  // source panel
  const [tab, setTab] = useState("paste");
  const [name, setName] = useState("");
  const [pasted, setPasted] = useState("");
  const [file, setFile] = useState(null);
  const [urlsText, setUrlsText] = useState("");
  const [followNext, setFollowNext] = useState(false);
  const [maxPages, setMaxPages] = useState(30);
  const [chunkChars, setChunkChars] = useState(4000);
  const fileRef = useRef(null);

  // projects
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null); // full project payload
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  // model
  const [provider, setProvider] = useState("nanogpt");
  const [model, setModel] = useState(DEFAULT_MODELS.nanogpt);
  const [modelList, setModelList] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [condense, setCondense] = useState(true);
  const [mode, setMode] = useState("deep"); // "deep" | "quick"
  const [force, setForce] = useState(false);
  const [parallel, setParallel] = useState(3); // chunks sent to the model at once

  // job
  const [job, setJob] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [jobKind, setJobKind] = useState(""); // "fetch" | "extract"
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // review
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [checked, setChecked] = useState(new Set());
  const [filterType, setFilterType] = useState("all");
  const [filterFlag, setFilterFlag] = useState("all");
  const [search, setSearch] = useState("");
  const [entDelConfirm, setEntDelConfirm] = useState(null);
  const [dirty, setDirty] = useState(false);     // editor has changes not yet saved
  const [saving, setSaving] = useState(false);
  const [filterIssue, setFilterIssue] = useState("all");
  const [filterTier, setFilterTier] = useState("all");
  const [showOneOffs, setShowOneOffs] = useState(false);   // one-off entries are collapsed by default
  const [showTrash, setShowTrash] = useState(false);
  const [lastDeleted, setLastDeleted] = useState([]);      // ids of the last delete, for UNDO
  const [recap, setRecap] = useState(null);                // {text, edited, upto, chunks, limit}
  const [recapDirty, setRecapDirty] = useState(false);     // starting point or text changed, not saved yet
  const [recapTyped, setRecapTyped] = useState(false);     // the text itself was edited by hand
  const [timelineTyped, setTimelineTyped] = useState(false);
  const [timelineStale, setTimelineStale] = useState(false); // starting point moved since the chapter log was written
  const [recapAiBusy, setRecapAiBusy] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);  // events live in their own collapsed section
  const [cardBusy, setCardBusy] = useState("");            // "narrator" | entity id while a card is being made
  const draftRef = useRef(null);
  draftRef.current = draft;

  useEffect(() => {
    loadProjects();
    getPresets().then((p) => {          // Config → Model presets
      if (p?.extract?.model) { setProvider(p.extract.provider || "nanogpt"); setModel(p.extract.model); }
    }).catch(() => {});
  }, []);

  async function loadProjects() {
    try { setProjects(await listTextProjects()); } catch (e) { setError(e.message); }
  }

  async function openProject(id) {
    try {
      const p = await getTextProject(id);
      setProject(p);
      setSelectedId(null); setDraft(null); setChecked(new Set()); setError(""); setShowTrash(false); setLastDeleted([]);
      loadRecap(id);
    } catch (e) { setError(e.message); }
  }

  async function loadRecap(id, upto) {
    try {
      const r = await getTextRecap(id, upto);
      setRecap(r); setRecapDirty(upto !== undefined); setRecapTyped(false); setTimelineTyped(false);
      setTimelineStale(upto !== undefined && !!r.timeline);
    }
    catch { setRecap(null); }
  }

  // poll job
  useEffect(() => {
    if (!jobId) return;
    let tick = 0;
    const iv = setInterval(async () => {
      try {
        const j = await getJob(jobId);
        setJob(j);
        // live per-chunk progress: refresh the chunk list every few seconds while extracting
        tick += 1;
        if (jobKind === "extract" && j.status === "running" && tick % 3 === 0 && project) {
          getTextProject(project.id).then((p) => setProject((cur) => (cur && cur.id === p.id ? { ...cur, chunks: p.chunks } : cur))).catch(() => {});
        }
        if (j.status === "done" || j.status === "failed") {
          clearInterval(iv);
          setBusy(false);
          if (j.status === "failed") setError(j.error || j.message || "Job failed");
          if (j.status === "done") {
            await loadProjects();
            if (jobKind === "fetch" && j.result?.project_id) await openProject(j.result.project_id);
            else if (project) await openProject(project.id);
            showToast && showToast(j.message || "Done");
          }
        }
      } catch {}
    }, 1000);
    return () => clearInterval(iv);
  }, [jobId]);

  async function handleFetchModels() {
    setModelsLoading(true);
    try { setModelList(await fetchModels(provider)); } catch (e) { setError(e.message); }
    finally { setModelsLoading(false); }
  }

  async function handleIngest() {
    setError(""); setBusy(true);
    try {
      if (tab === "url") {
        const urls = urlsText.split("\n").map((u) => u.trim()).filter(Boolean);
        const { job_id } = await textIngestUrls({ name, urls, follow_next: followNext, max_pages: maxPages, chunk_chars: chunkChars });
        setJob(null); setJobKind("fetch"); setJobId(job_id);
        return; // busy cleared by poller
      }
      const res = tab === "file"
        ? await textIngestFile(file, name, chunkChars)
        : await textIngest({ name, text: pasted, chunk_chars: chunkChars });
      await loadProjects();
      await openProject(res.id);
      setPasted(""); setFile(null); setName("");
      if (fileRef.current) fileRef.current.value = "";
      showToast && showToast(`${res.chunks} chunks ready`);
      setBusy(false);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  // review work (hand edits, trash, keep/skip choices, manual merges) survives re-extracting and Rebuild list (mergeOnly)
  async function handleExtract(mergeOnly = false, only = null) {
    if (!project) return;
    if (force && !mergeOnly && !only && !window.confirm(`Redo all ${project.chunks.length} chunks from scratch? This makes new model calls for every chunk.`)) return;
    setError(""); setBusy(true);
    try {
      const res = await startTextExtract(project.id, { provider, model, condense, mode, parallel, force: force && !mergeOnly && !only, merge_only: mergeOnly, only });
      if (res.already_running) showToast && showToast("Extraction is already running for this text; following it.");
      setJob(null); setJobKind("extract"); setJobId(res.job_id);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  // add new chapters or a SillyTavern chat log to the end; only the new chunks need extracting
  const appendRef = useRef(null);
  const [appendOpen, setAppendOpen] = useState(false);
  const [appendTextVal, setAppendTextVal] = useState("");
  async function handleAppend(fileOrText) {
    if (!project) return;
    try {
      const r = await appendText(project.id, fileOrText);
      setAppendOpen(false); setAppendTextVal("");
      if (appendRef.current) appendRef.current.value = "";
      await openProject(project.id); await loadProjects();
      showToast && showToast(`Added ${r.added_chars.toLocaleString()} chars as ${r.new_chunks} new chunk(s). Press EXTRACT REMAINING.`);
    } catch (e) { setError(e.message); }
  }

  async function handleRechunk() {
    if (!project) return;
    const done = project.chunks.filter((c) => c.done).length;
    const calls = done * (mode === "deep" ? 7 : 1);
    if (!window.confirm(`Resplit "${project.name}" into ~${chunkChars.toLocaleString()}-character chunks?\n\n` +
      (done ? `This DELETES the extraction for ${done} chunk(s) (about ${calls} model calls to redo). Your review list stays until you extract again.`
            : "No chunks have been extracted yet, so nothing is lost.") +
      "\n\nMenus and broken characters in the saved text are cleaned again.")) return;
    try {
      const r = await rechunkTextProject(project.id, chunkChars);
      await openProject(project.id); await loadProjects();
      showToast && showToast(`Resplit into ${r.chunks} chunks. Press EXTRACT.`);
    }
    catch (e) { setError(e.message); }
  }

  async function handleDeleteProject(id, e) {
    e.stopPropagation();
    if (deleteConfirm !== id) { setDeleteConfirm(id); return; }
    await deleteTextProject(id);
    setDeleteConfirm(null);
    if (project?.id === id) setProject(null);
    loadProjects();
  }

  // review ------------------------------------------------------------------
  const draftFrom = (e) => ({ ...e, aliasesCsv: csv(e.aliases), keywordsCsv: csv(e.keywords), voiceText: (e.voice || []).join("\n"),
    relText: relToText(e.relations), origin: e.origin || "" });

  // reload the entry list WITHOUT closing the editor or losing the selection / scroll position
  async function refreshEntities() {
    try { setProject(await getTextProject(project.id)); } catch (e) { setError(e.message); }
  }

  function editDraft(patch) { setDraft((d) => ({ ...d, ...patch })); setDirty(true); }

  async function selectEntity(e) {
    if (draft && dirty) await saveDraft(true);      // never lose edits when clicking another entry
    setSelectedId(e.id); setDraft(draftFrom(e)); setDirty(false); setEntDelConfirm(null);
  }

  function stepEntity(dir) {
    const list = shownRef.current;
    const i = list.findIndex((x) => x.id === selectedId);
    const t = list[i + dir];
    if (t) selectEntity(t);
  }

  async function saveDraft(silent) {
    const snap = draftRef.current;
    if (!snap) return;
    setSaving(true);
    try {
      await patchTextEntity(snap.id, {
        name: snap.name, type: snap.entity_type, age: snap.age, content: snap.content,
        aliases: fromCsv(snap.aliasesCsv), keywords: fromCsv(snap.keywordsCsv),
        voice: snap.voiceText.split("\n").map((v) => v.trim()).filter(Boolean), keep: snap.keep,
        origin: snap.origin || "", relations: textToRel(snap.relText),
      });
      if (draftRef.current === snap) setDirty(false);   // stay dirty if more typing happened meanwhile
      await refreshEntities();
      if (silent !== true) showToast && showToast("Entity saved");
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  // autosave 1 s after the last keystroke
  useEffect(() => {
    if (!dirty || !draft) return;
    const t = setTimeout(() => saveDraft(true), 1000);
    return () => clearTimeout(t);
  }, [draft, dirty]);

  // keyboard review: J/K or arrows move, X keep/skip, Delete -> trash, U undo, Ctrl+S save
  useEffect(() => {
    function onKey(ev) {
      const tag = (ev.target?.tagName || "").toLowerCase();
      const typing = tag === "input" || tag === "textarea" || tag === "select" || ev.target?.isContentEditable;
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") {
        if (draftRef.current) { ev.preventDefault(); saveDraft(false); }
        return;
      }
      if (typing || ev.ctrlKey || ev.metaKey || ev.altKey || !project || showTrash) return;
      const k = ev.key;
      if (k === "j" || k === "ArrowDown" || k === "k" || k === "ArrowUp") {
        const list = shownRef.current;
        if (!list.length) return;
        ev.preventDefault();
        const i = list.findIndex((x) => x.id === selectedId);
        const dir = (k === "j" || k === "ArrowDown") ? 1 : -1;
        const t2 = i < 0 ? list[0] : list[i + dir];
        if (t2) selectEntity(t2);
      } else if ((k === "x" || k === "X") && draftRef.current) {
        ev.preventDefault(); toggleKeep(draftRef.current);
      } else if (k === "Delete" && draftRef.current) {
        ev.preventDefault(); removeEntity();
      } else if ((k === "u" || k === "U") && lastDeleted.length) {
        ev.preventDefault(); undoDelete();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function toggleKeep(e, ev) {
    if (ev) ev.stopPropagation();
    try {
      await patchTextEntity(e.id, { keep: !e.keep });
      if (draftRef.current && draftRef.current.id === e.id) setDraft((d) => ({ ...d, keep: !e.keep }));
      await refreshEntities();
    } catch (er) { setError(er.message); }
  }

  // deleting moves to the trash (restorable), so no confirmation step
  async function removeEntity() {
    if (!draft) return;
    const list = shownRef.current;
    const i = list.findIndex((x) => x.id === draft.id);
    const next = list[i + 1] || list[i - 1];
    try {
      await deleteTextEntity(draft.id);
      setLastDeleted([draft.id]);
      setEntDelConfirm(null); setDirty(false);
      const p = await getTextProject(project.id);
      setProject(p);
      const nx = next && p.entities.find((x) => x.id === next.id);
      if (nx) { setSelectedId(nx.id); setDraft(draftFrom(nx)); } else { setSelectedId(null); setDraft(null); }
    } catch (e) { setError(e.message); }
  }

  // bulk actions on the ticked rows
  function toggleAllShown() {
    setChecked((c) => (shown.length > 0 && shown.every((e) => c.has(e.id))) ? new Set() : new Set(shown.map((e) => e.id)));
  }
  function selectProblems(kind) {   // "issues" = every flagged entry that is safe to remove, "dups" = duplicate extras only
    const ids = entities.filter((e) => {
      const i = issues.get(e.id) || {};
      return kind === "dups" ? i.dupExtra : (i.dupExtra || i.empty || i.junk);
    }).map((e) => e.id);
    setChecked(new Set(ids));
    if (!ids.length) showToast && showToast("Nothing flagged");
  }
  async function bulkKeep(val) {
    try { for (const id of checked) await patchTextEntity(id, { keep: val }); await refreshEntities(); }
    catch (e) { setError(e.message); }
  }
  async function bulkDelete() {
    try {
      for (const id of checked) await deleteTextEntity(id);
      setLastDeleted([...checked]);
      if (draft && checked.has(draft.id)) { setDraft(null); setSelectedId(null); setDirty(false); }
      setChecked(new Set());
      await refreshEntities();
    } catch (e) { setError(e.message); }
  }
  async function undoDelete() {
    try {
      for (const id of lastDeleted) await restoreTextEntity(id);
      showToast && showToast(`${lastDeleted.length} restored`);
      setLastDeleted([]);
      await refreshEntities();
    } catch (e) { setError(e.message); }
  }
  async function restoreOne(id) {
    try { await restoreTextEntity(id); await refreshEntities(); } catch (e) { setError(e.message); }
  }
  async function emptyTrash() {
    if (!window.confirm(`Permanently delete the ${project.trash.length} entries in the trash?`)) return;
    try { await emptyTextTrash(project.id); setLastDeleted([]); await refreshEntities(); } catch (e) { setError(e.message); }
  }

  // recap / starting point
  // only hand-typed text is frozen; otherwise just the starting point is saved and the recap stays automatic
  async function saveRecap(reset = false, quiet = false) {
    try {
      const timeline = reset ? "" : timelineTyped ? recap.timeline : timelineStale ? "" : undefined;
      await saveTextRecap(project.id, reset || !recapTyped ? (reset ? "" : (recap.edited && !timelineStale ? recap.text : "")) : recap.text,
        recap.upto, timeline);
      if (quiet) return;
      await loadRecap(project.id);
      showToast && showToast(reset ? "Recap reset to automatic" : "Story So Far saved");
    } catch (e) { setError(e.message); }
  }

  async function aiRecap() {
    if (recap?.edited && !window.confirm("Replace the current Story So Far with an AI-written archive summary?")) return;
    setRecapAiBusy(true); setError("");
    try {
      const r = await writeRecapAI(project.id, { provider, model, upto: recap?.upto ?? -1 });
      await loadRecap(project.id);
      showToast && showToast(`Recap written (${r.text.length.toLocaleString()} chars) and saved`);
    } catch (e) { setError(e.message); }
    finally { setRecapAiBusy(false); }
  }

  // cards
  async function makeCard(e) {
    if (!onMakeCard) return;
    try {
      if (dirty) await saveDraft(true);
      setCardBusy(e.id);
      const res = await textEntityToSource(e.id);
      onMakeCard(res);
    } catch (er) { setError(er.message); }
    finally { setCardBusy(""); }
  }
  // cards for every kept main character, then (optionally) one group card; runs as a job
  const [castJob, setCastJob] = useState(null);            // {id, status, message}
  const [castGroup, setCastGroup] = useState(true);
  async function makeCastCards() {
    const n = entities.filter((e) => e.keep && e.entity_type === "character" && e.tier === "main").length;
    if (!n) { setError("No kept main characters. Keep some main-tier characters first."); return; }
    if (!window.confirm(`Write ${Math.min(n, 8)} character card(s)${castGroup && n >= 2 ? " and a group card" : ""} with ${provider}/${model || "default"}? This makes one model call per card (more with in-depth mode). Cards made earlier are kept.`)) return;
    setError("");
    try {
      const r = await startCastCards(project.id, { provider, model, group: castGroup });
      setCastJob({ id: r.job_id, status: "running", message: `Starting ${r.count} card(s)...` });
    } catch (e) { setError(e.message); }
  }
  useEffect(() => {
    if (!castJob?.id || castJob.status !== "running") return;
    const iv = setInterval(async () => {
      try {
        const j = await getJob(castJob.id);
        if (j.status === "done") {
          clearInterval(iv);
          const res = j.result || {};
          setCastJob({ id: null, status: "done", message: j.message });
          if (res.failed?.length) setError(`Some cards failed: ${res.failed.map((f) => `${f.name || f.id}: ${f.error}`).join("; ")}`);
          showToast && showToast(`${j.message}. Open them from the Library.`);
        } else if (j.status === "failed") {
          clearInterval(iv);
          setCastJob({ id: null, status: "failed", message: j.error || j.message });
          setError(j.error || j.message || "Cast cards failed");
        } else {
          setCastJob((c) => ({ ...c, message: j.message || c.message }));
        }
      } catch { /* keep polling */ }
    }, 1500);
    return () => clearInterval(iv);
  }, [castJob?.id, castJob?.status]);

  // closing the tab mid-job or with an unsaved review edit asks first
  useEffect(() => { markBusy("text", busy || dirty || castJob?.status === "running"); return () => markBusy("text", false); },
    [busy, dirty, castJob?.status]);
  // a search hit: open the project, then the entity
  const [pendingSelect, setPendingSelect] = useState(null);
  useEffect(() => {
    if (!focus) return;
    (async () => {
      await openProject(focus.project_id);
      if (focus.id) setPendingSelect(focus.id);
      clearFocus && clearFocus();
    })();
  }, [focus]);
  useEffect(() => {
    if (!pendingSelect || !project) return;
    const e = (project.entities || []).find((x) => x.id === pendingSelect);
    setPendingSelect(null);
    if (!e) return;
    if (e.entity_type === "event") setShowTimeline(true);
    selectEntity(e);
  }, [pendingSelect, project]);

  async function makeNarrator() {
    setCardBusy("narrator"); setError("");
    try {
      const res = await makeNarratorCard(project.id, { provider, model });
      const blob = new Blob([JSON.stringify(res.card, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${(res.card?.data?.name || "narrator").replace(/[^\w\- ]+/g, "")}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      showToast && showToast(`Narrator card downloaded (${res.entries} lore entries embedded) and saved to the library`);
    } catch (e) { setError(e.message); }
    finally { setCardBusy(""); }
  }

  // merge every group of same-named entries into one (combines their notes instead of throwing them away)
  async function mergeDuplicates() {
    const groups = dupGroups(entities).filter((g) => g.every((e) => e.entity_type !== "event"));
    if (!groups.length) { showToast && showToast("No duplicate groups to merge"); return; }
    if (!window.confirm(`Merge ${groups.length} group(s) of duplicate entries into one entry each?`)) return;
    try {
      for (const g of groups) await mergeTextEntities(project.id, g.map((e) => e.id));
      setChecked(new Set()); setDraft(null); setSelectedId(null); setDirty(false);
      await openProject(project.id);
      showToast && showToast("Duplicates merged");
    } catch (e) { setError(e.message); }
  }

  async function mergeChecked() {
    try {
      await mergeTextEntities(project.id, [...checked]);
      setChecked(new Set()); setDraft(null); setSelectedId(null);
      await openProject(project.id);
      showToast && showToast("Entities merged");
    } catch (e) { setError(e.message); }
  }

  // events roll up into 2 entries (recap + timeline); everything else is one entry each
  // plus one always-on Cast Roster when two or more main/supporting characters are kept, and one Relationships entry
  const relationPairs = (kept) => {
    const chars = kept.filter((e) => e.entity_type === "character");
    const names = new Map();
    chars.forEach((e) => [e.name, ...(e.aliases || [])].forEach((n) => names.set(String(n).toLowerCase().trim(), e.name)));
    const pairs = new Set();
    chars.forEach((e) => (e.relations || []).forEach((x) => {
      const o = names.get(String(x.with || "").toLowerCase().trim());
      if (o && o !== e.name && x.relation) pairs.add([e.name, o].sort().join("|"));
    }));
    return pairs.size;
  };
  const countToSend = (kept) => kept.filter((e) => e.entity_type !== "event").length +
    ((kept.some((e) => e.entity_type === "event") || recap?.timeline) ? 2 : 0) +
    (kept.filter((e) => e.entity_type === "character" && e.tier !== "one-off").length >= 2 ? 1 : 0) +
    (relationPairs(kept) >= 2 ? 1 : 0);

  async function commit(asNew = false) {
    const kept = project.entities.filter((e) => e.keep);
    const flagged = kept.filter((e) => e.age_flag === "minor" || e.age_flag === "check").length;
    const sendCount = countToSend(kept);
    const resend = !!project.lore_project_id && !asNew;
    const msg = (resend
      ? `Update the LORE project made last time with ${sendCount} entries?\n\nEntries you edited by hand in LORE are kept as they are; the rest are refreshed, new ones added, and ones you no longer keep go to the LORE trash. (Cancel, then hold Shift while clicking, to make a separate new project instead.)`
      : `Send ${sendCount} entries to a new LORE project?`) +
      (kept.some((e) => e.entity_type === "event") ? "\n\nKept events are combined into a 'Story So Far' recap and a timeline, not sent one by one." : "") +
      (flagged ? `\n\n${flagged} character(s) are flagged under 18 / check age. Review them first if you haven't.` : "");
    if (!window.confirm(msg + (recap && recap.upto >= 0 ? `\n\nRoleplay starts after chunk ${recap.upto + 1}: the recap and timeline stop there.` : ""))) return;
    try {
      if (recapDirty) await saveRecap(false, true);   // send what is on screen
      const r = await commitTextProject(project.id, asNew ? "new" : undefined);
      showToast && showToast(r.mode === "update"
        ? `LORE updated: ${r.updated} refreshed, ${r.added} added, ${r.kept_edited} hand-edited kept, ${r.trashed} to trash`
        : `${r.entries} entries sent to a new LORE project`);
      await loadProjects(); await openProject(project.id);
    } catch (e) { setError(e.message); }
  }

  const entities = project?.entities || [];
  const issues = useMemo(() => findIssues(project?.entities || []), [project]);
  const issueCount = entities.filter((e) => issueMatch(issues.get(e.id), "any")).length;
  const dupCount = entities.filter((e) => issues.get(e.id)?.dupExtra).length;
  const tierRank = { main: 0, supporting: 1, "one-off": 2, "": 3 };
  const oneOffHidden = !showOneOffs && filterTier === "all" && !search
    ? entities.filter((e) => e.tier === "one-off").length : 0;
  const timelineEvents = entities.filter((e) => e.entity_type === "event" &&
    (!search || e.name.toLowerCase().includes(search.toLowerCase()))).sort((a, b) => a.id - b.id);   // story order
  const shown = entities.filter((e) => e.entity_type !== "event" &&
    (filterTier === "all" ? (showOneOffs || !!search || e.tier !== "one-off") : e.tier === filterTier) &&
    (filterIssue === "all" || (filterIssue === "fic" ? ["altered", "original"].includes(e.origin) : issueMatch(issues.get(e.id), filterIssue))) &&
    (filterType === "all" || e.entity_type === filterType) &&
    (filterFlag === "all" || (filterFlag === "flagged" ? ["minor", "check"].includes(e.age_flag) : e.age_flag === filterFlag)) &&
    (!search || e.name.toLowerCase().includes(search.toLowerCase()) || e.aliases.some((a) => a.toLowerCase().includes(search.toLowerCase())))
  ).sort((a, b) => (a.entity_type === "event") - (b.entity_type === "event") || (tierRank[a.tier || ""] - tierRank[b.tier || ""]));
  const shownRef = useRef(shown);
  shownRef.current = showTimeline ? [...shown, ...timelineEvents] : shown;
  const flaggedCount = entities.filter((e) => ["minor", "check"].includes(e.age_flag)).length;
  const doneChunks = project ? project.chunks.filter((c) => c.done).length : 0;
  const canIngest = !busy && (tab === "paste" ? pasted.trim().length > 0 : tab === "file" ? !!file : urlsText.trim().length > 0);

  const remaining = project ? project.chunks.length - doneChunks : 0;
  const tabBtn = (active) => ({
    ...btn, flex: 1, padding: "8px 10px",
    background: active ? "var(--signal-btn-active-bg)" : "var(--signal-bg-btn)",
    color: active ? "var(--signal-btn-active-text)" : "var(--signal-text)",
  });
  const checkRow = { display: "flex", gap: 6, alignItems: "center", fontSize: 12, marginTop: 8, cursor: "pointer" };

  return (
    <div>
      <h1 className="signal-title signal-heading" style={{ marginTop: 0, marginBottom: 4, display: "block", textAlign: "center" }}>
        {t.textStudio || "Text Studio"}
      </h1>
      <p style={{ color: "var(--signal-text-dim)", textAlign: "center", marginBottom: 20, letterSpacing: "0.04em" }}>
        {t.textSubtitle || "Fanfiction & long text • chapters • characters • events"}
      </p>

      {error && (
        <div style={{ color: "#c84a3a", fontSize: 13, marginBottom: 10, padding: "8px 12px", border: "1px solid #c84a3a",
          display: "flex", justifyContent: "space-between", gap: 8, textAlign: "left" }}>
          <span>⊗ {error}</span>
          <span style={{ cursor: "pointer" }} onClick={() => setError("")}>✕</span>
        </div>
      )}

      {job && (busy || job.status === "failed") && <MainJobStatus job={job} mode="lore" />}

      <div className="signal-main-grid text-grid" style={{
        display: "grid", gridTemplateColumns: "minmax(250px, 0.8fr) minmax(300px, 1fr) minmax(360px, 1.3fr)",
        gap: 12, alignItems: "start",
      }}>
        {/* ───────── LEFT: projects + source, and the critic under it ───────── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
        <section className="signal-panel signal-panel-delay-1" style={panelStyle}>
          <h2 className="signal-heading" style={headingStyle}>TEXT SOURCES</h2>

          <div style={{ maxHeight: 220, overflowY: "auto", marginBottom: 4 }}>
            {projects.length === 0 && (
              <div style={{ fontSize: 11, color: "var(--signal-text-dim)", textAlign: "center", padding: "8px 0" }}>No texts yet</div>
            )}
            {projects.map((p) => {
              const active = project?.id === p.id;
              return (
                <div key={p.id} onClick={() => openProject(p.id)} style={{
                  padding: "6px 8px", marginBottom: 3, cursor: "pointer", fontSize: 12,
                  border: "1px solid var(--signal-border)",
                  background: active ? "var(--signal-btn-active-bg)" : "var(--signal-bg-btn)",
                  color: active ? "var(--signal-btn-active-text)" : "var(--signal-text)",
                  display: "flex", justifyContent: "space-between", alignItems: "center", gap: 4,
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</div>
                    <div style={{ fontSize: 10, opacity: 0.6 }}>
                      {(p.chars / 1000).toFixed(0)}k chars · {p.done_chunks}/{p.chunk_count} chunks · {p.entity_count} entities
                      {p.lore_project_id ? " · in LORE" : ""}
                    </div>
                  </div>
                  <button onClick={(e) => handleDeleteProject(p.id, e)} aria-label={deleteConfirm === p.id ? `Confirm: delete ${p.name}` : `Delete ${p.name}`}
                    title={deleteConfirm === p.id ? "Click again to delete" : "Delete text project"} style={{
                    background: deleteConfirm === p.id ? "#c84a3a" : "none", border: "none", cursor: "pointer",
                    color: deleteConfirm === p.id ? "#fff" : "#c84a3a", fontSize: 11, padding: "0 4px", flexShrink: 0,
                  }}>{deleteConfirm === p.id ? "?" : "✕"}</button>
                </div>
              );
            })}
          </div>

          <Divider label="NEW SOURCE" />

          <div style={{ display: "flex", gap: 8, marginBottom: 4 }}>
            {SOURCE_TABS.map((k) => (
              <button key={k} className={tab === k ? "signal-btn signal-btn-active" : "signal-btn"} onClick={() => setTab(k)} style={tabBtn(tab === k)}>
                {k.toUpperCase()}
              </button>
            ))}
          </div>

          <div style={label}>NAME (optional)</div>
          <input style={input} value={name} onChange={(e) => setName(e.target.value)} placeholder="Fic title" />

          {tab === "paste" && (<>
            <div style={label}>TEXT</div>
            <textarea style={{ ...input, height: 160, resize: "vertical" }} value={pasted} onChange={(e) => setPasted(e.target.value)}
              placeholder="Paste the whole fic or any amount of chapters. Lines like 'Chapter 3' split it up." />
            <div style={hint}>{pasted.length.toLocaleString()} chars</div>
          </>)}

          {tab === "file" && (<>
            <div style={label}>FILE (.txt .md .html .epub, or a SillyTavern chat .jsonl)</div>
            <input ref={fileRef} type="file" accept=".txt,.md,.html,.htm,.xhtml,.epub,.jsonl" onChange={(e) => setFile(e.target.files?.[0] || null)}
              style={{ ...input, padding: 8 }} />
            <div style={hint}>On AO3: Download → HTML or EPUB gives the cleanest result. A SillyTavern chat export (.jsonl) turns a roleplay into lore the same way.</div>
          </>)}

          {tab === "url" && (<>
            <div style={label}>URLS (one per line)</div>
            <textarea style={{ ...input, height: 100, resize: "vertical" }} value={urlsText} onChange={(e) => setUrlsText(e.target.value)}
              placeholder={"https://archiveofourown.org/works/12345\nor one URL per chapter\nor wiki pages: https://….fandom.com/wiki/Name"} />
            <label style={checkRow}>
              <input type="checkbox" checked={followNext} onChange={(e) => setFollowNext(e.target.checked)} />
              Follow "next chapter" links
            </label>
            {followNext && (<>
              <div style={label}>MAX PAGES</div>
              <input type="number" min={1} max={200} style={input} value={maxPages} onChange={(e) => setMaxPages(+e.target.value)} />
            </>)}
            <div style={hint}>
              AO3 work links load the full work in one request. Wiki pages (Fandom, Wikipedia and other /wiki/ links) are read
              through the wiki's API: infobox, sections and lists, without navboxes or references. Pages are fetched 2s apart. Menus, nav links and
              repeated pages are stripped. Sites with bot protection (e.g. FanFiction.net) will refuse; paste or upload instead.
            </div>
          </>)}

          <div style={label}>CHUNK SIZE (chars)</div>
          <input type="number" min={1500} max={20000} step={500} style={input} value={chunkChars} onChange={(e) => setChunkChars(+e.target.value)} />
          {project && (
            <button className="signal-btn" style={{ ...btn, width: "100%", marginTop: 8, borderColor: "#c84a3a", color: "#c84a3a", fontSize: 12 }}
              disabled={busy} onClick={handleRechunk}
              title="Cut the open text into chunks of this size again. Deletes its extraction results: extraction starts over.">
              ✂ {(t.resplitText || "Resplit text").toUpperCase()} AT THIS SIZE
            </button>
          )}

          <button className="signal-btn" style={{ ...btnPrimary, width: "100%", marginTop: 14, opacity: canIngest ? 1 : 0.5, cursor: canIngest ? "pointer" : "not-allowed" }}
            disabled={!canIngest} onClick={handleIngest}>
            {busy && jobKind === "fetch" ? "FETCHING…" : "⇣ LOAD TEXT"}
          </button>
        </section>

        <CriticPanel project={project} parallel={parallel} showToast={showToast} setError={setError} t={t} />
        </div>

        {/* ───────── MIDDLE: pipeline ───────── */}
        <section className="signal-panel signal-panel-delay-2" style={panelStyle}>
          <h2 className="signal-heading" style={headingStyle}>{project ? project.name : (t.noTextSelected || "NO TEXT SELECTED")}</h2>

          {!project && (
            <div style={{ color: "var(--signal-text-dim)", fontSize: 13, padding: "12px 0", textAlign: "center", lineHeight: 1.6 }}>
              Load a text on the left, or pick a saved one.<br />
              Then: <b>extract → review → send to LORE</b>.
            </div>
          )}

          {project && (<>
            <div style={{ ...hint, marginTop: 0, textAlign: "center" }}>
              {(project.chars / 1000).toFixed(0)}k chars · {project.chunks.length} chunks · {doneChunks} extracted · {entities.length} entities
            </div>

            <div style={label}>PROVIDER / MODEL</div>
            <div style={{ display: "flex", gap: 8 }}>
              <select style={{ ...input, width: "auto" }} value={provider} onChange={(e) => { setProvider(e.target.value); setModel(DEFAULT_MODELS[e.target.value] || ""); setModelList([]); }}>
                <option value="nanogpt">NanoGPT</option>
                <option value="openrouter">OpenRouter</option>
                <option value="local">Local</option>
              </select>
              <input style={{ ...input, flex: 1, minWidth: 0 }} list="text-models" value={model} onChange={(e) => setModel(e.target.value)} placeholder="Model (optional)" />
              <datalist id="text-models">{modelList.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</datalist>
            </div>
            <button className="signal-btn signal-fetch-btn" onClick={handleFetchModels} disabled={modelsLoading} style={{
              width: "100%", marginTop: 6, padding: "8px 12px", border: "1px solid var(--signal-border)", fontFamily: "inherit",
              fontSize: 12, fontWeight: 700, letterSpacing: "0.08em", cursor: modelsLoading ? "not-allowed" : "pointer" }}>
              {modelsLoading ? "SCANNING…" : "FETCH MODELS FROM API"}
            </button>

            <Divider label="EXTRACTION" style={{ marginTop: 16 }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className={mode === "deep" ? "signal-btn signal-btn-active" : "signal-btn"} onClick={() => setMode("deep")} style={tabBtn(mode === "deep")}>DEEP</button>
              <button className={mode === "quick" ? "signal-btn signal-btn-active" : "signal-btn"} onClick={() => setMode("quick")} style={tabBtn(mode === "quick")}>QUICK</button>
            </div>
            <div style={hint}>
              {mode === "deep"
                ? "Inventory → gleaning → per-entity detail → events. About 7 model calls per chunk; finds far more."
                : "One call per chunk. Fast, but tends to miss entities."}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 12 }}>
              <span style={{ ...label, margin: 0 }}>{(t.chunksAtOnce || "Chunks at once").toUpperCase()}</span>
              <span style={{ fontSize: 13, fontWeight: 700 }}>{parallel}</span>
            </div>
            <input type="range" min="1" max="6" step="1" value={parallel} onChange={(e) => setParallel(parseInt(e.target.value))}
              style={{ width: "100%", accentColor: "var(--signal-text)", marginTop: 6 }} />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--signal-text-dim)" }}>
              <span>1 — gentle</span><span>6 — fastest</span>
            </div>
            <div style={hint}>
              Chunks sent to the model at once. Lower it if your provider rate-limits you.
              {remaining > 0 && <> ≈ {remaining * (mode === "deep" ? 7 : 1)} model calls for the {remaining} chunk(s) left.</>}
            </div>

            {doneChunks > 0 && (
              <label style={checkRow}>
                <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
                Redo all chunks (ignore earlier results)
              </label>
            )}
            <label style={checkRow}>
              <input type="checkbox" checked={condense} onChange={(e) => setCondense(e.target.checked)} />
              Condense entities mentioned across many chunks (extra model calls)
            </label>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
              <button className="signal-btn" style={{ ...btnPrimary, flex: "1 1 100%", opacity: busy ? 0.5 : 1 }} disabled={busy} onClick={() => handleExtract(false)}>
                {busy && jobKind === "extract" ? "WORKING…" : doneChunks ? "⟳ EXTRACT REMAINING" : "⟳ EXTRACT"}
              </button>
              {doneChunks > 0 && <button className="signal-btn" style={{ ...btn, flex: 1 }} disabled={busy} onClick={() => handleExtract(true)}
                title={"Rebuild the review list from the chunks already extracted. No extraction calls" + (condense ? " (Condense is on: a few calls to condense long entries)" : "") + ". Keeps hand edits, the trash, keep/skip and manual merges."}>
                ↻ {(t.rebuildList || "Rebuild list").toUpperCase()}</button>}
              <button className="signal-btn" style={{ ...btn, flex: 1 }} disabled={busy} onClick={() => setAppendOpen((o) => !o)}
                title="New chapters, or a SillyTavern chat that continues the story. Existing chunks and review work stay.">+ {(t.addText || "Add text").toUpperCase()}</button>
            </div>
            {appendOpen && (
              <div style={{ border: "1px solid var(--signal-border)", padding: 10, marginTop: 8 }}>
                <div style={label}>ADD TO THE END</div>
                <textarea style={{ ...input, height: 100, resize: "vertical" }} value={appendTextVal} onChange={(e) => setAppendTextVal(e.target.value)}
                  placeholder="Paste new chapters..." aria-label="Text to add" />
                <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <input ref={appendRef} type="file" accept=".txt,.md,.html,.htm,.xhtml,.epub,.jsonl" aria-label="File to add"
                    onChange={(e) => e.target.files?.[0] && handleAppend(e.target.files[0])} style={{ ...input, padding: 6, flex: "1 1 200px", width: "auto" }} />
                  <button className="signal-btn" style={btnPrimary} disabled={appendTextVal.trim().length < 200} onClick={() => handleAppend(appendTextVal)}>ADD</button>
                </div>
                <div style={hint}>Pick a file to add it right away (.jsonl = SillyTavern chat). Only the new chunks are extracted next time.</div>
              </div>
            )}
            {doneChunks > 0 && (
              <div style={hint}>
                Rebuild list: free, keeps your review. A new chunk size? Use Resplit text under Chunk size (extraction starts over).
              </div>
            )}

            <Divider label={`CHUNKS (${project.chunks.length})`} style={{ marginTop: 16 }} />
            <div style={{ maxHeight: 260, overflowY: "auto", border: "1px solid var(--signal-border)" }}>
              {project.chunks.map((c) => (
                <div key={c.idx} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, padding: "6px 8px", borderBottom: "1px solid var(--signal-border)" }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={c.label}>{c.idx + 1}. {c.label}</span>
                  <span style={{ color: c.done ? "var(--signal-text)" : "var(--signal-text-dim)", flexShrink: 0 }}>
                    {(c.chars / 1000).toFixed(1)}k
                    {c.done ? ` · ${c.entities} ent / ${c.beats} ev ✓` : (busy && jobKind === "extract" ? " · …" : " ·")}
                    {c.done && c.chars >= 2000 && c.entities + c.beats < 3 && (
                      <b style={{ color: "#b8860b", marginLeft: 6 }} title="Few results for this much text. Re-run with Deep mode.">LOW</b>
                    )}
                    {c.done && (
                      <button onClick={() => handleExtract(false, [c.idx])} disabled={busy} title="Redo just this chunk with the model selected above"
                        style={{ ...btnSm, marginLeft: 6, padding: "0 6px", opacity: busy ? 0.4 : 1 }}>↻</button>
                    )}
                  </span>
                </div>
              ))}
            </div>

            {entities.length > 0 && recap && (<>
              <Divider label="STORY SO FAR" style={{ marginTop: 16 }} />
              <div style={label}>ROLEPLAY STARTS AFTER</div>
              <select style={input} value={recap.upto ?? -1}
                onChange={(e) => loadRecap(project.id, parseInt(e.target.value))}>
                <option value={-1}>the end of the text</option>
                {recap.chunks.map((lbl, i) => <option key={i} value={i}>{i + 1}. {lbl}</option>)}
              </select>
              <div style={label}>
                RECAP (always in context) {recap.edited && !recapDirty ? "· hand-edited" : ""}
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
                <span style={{ ...hint, margin: 0 }}>{t.recapPlacement || "Placed in SillyTavern"}</span>
                <select style={{ ...input, width: "auto", flex: 1, padding: "5px 8px", fontSize: 12 }} value={recap.position || "before"}
                  aria-label="Where SillyTavern inserts the recap"
                  title="Before the card: read as background. At depth 4: inserted near the latest messages as a system note, so it weighs more on what happens next."
                  onChange={async (e) => {
                    const position = e.target.value;
                    try { await saveRecapPosition(project.id, position); setRecap((r) => ({ ...r, position })); }
                    catch (er) { setError(er.message); }
                  }}>
                  <option value="before">before the character card</option>
                  <option value="depth">at depth 4, as a system note</option>
                </select>
              </div>
              <textarea style={{ ...input, height: Math.max(150, Math.min(520, 40 + Math.ceil((recap.text || "").length / 46) * 20)), resize: "vertical",
                fontFamily: (recap.text || "").startsWith("[HEADER]") ? "ui-monospace, Consolas, monospace" : undefined, fontSize: (recap.text || "").startsWith("[HEADER]") ? 12 : undefined }} value={recap.text}
                onChange={(e) => { setRecap({ ...recap, text: e.target.value }); setRecapDirty(true); setRecapTyped(true); }} />
              <div style={{ ...hint, color: (recap.text || "").length > recap.limit ? "#c84a3a" : undefined }}>
                {(recap.text || "").length.toLocaleString()} / {recap.limit.toLocaleString()} chars (about {Math.round((recap.text || "").length / 4)} tokens).
                The timeline and recap stop at the starting point.
                {(recap.text || "").length > 3000 && " This entry is always in context: in SillyTavern raise the World Info token budget (default 2048) so other entries still fit."}
              </div>
              {recap.timeline && (<>
                <div style={label}>STORY TIMELINE · CHAPTER LOG (loads when the chat mentions the past)</div>
                <textarea style={{ ...input, height: 160, resize: "vertical" }} value={recap.timeline}
                  onChange={(e) => { setRecap({ ...recap, timeline: e.target.value }); setRecapDirty(true); setTimelineTyped(true); }} />
                <div style={{ ...hint, color: timelineStale ? "#b8860b" : undefined }}>
                  {timelineStale ? "The starting point changed: this chapter log was written for the old one. Saving switches back to event lines; or write a new AI recap."
                    : `${recap.timeline.length.toLocaleString()} / ${(recap.timeline_limit || 9000).toLocaleString()} chars. Replaces the one-line-per-event timeline.`}
                </div>
              </>)}
              <button className="signal-btn" style={{ ...btnPrimary, width: "100%", marginTop: 8, opacity: recapAiBusy ? 0.6 : 1 }}
                disabled={recapAiBusy} onClick={aiRecap}
                title="Writes one always-on Story So Far entry: [HEADER] timeline/location/dynamic, [BODY] chapter log, [FOOTER] current situation and plot hooks">
                {recapAiBusy ? "WRITING RECAP…" : "✦ WRITE RECAP WITH AI"}
              </button>
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button className="signal-btn" style={{ ...btn, flex: 1, opacity: recapDirty ? 1 : 0.6 }} onClick={() => saveRecap(false)}>SAVE RECAP</button>
                <button className="signal-btn" style={btn} onClick={() => saveRecap(true)} title="Go back to the automatic recap and the one-line-per-event timeline">RESET</button>
              </div>
            </>)}

            {entities.length > 0 && (
              <button className="signal-btn" style={{ ...btnPrimary, width: "100%", marginTop: 14 }} onClick={(e) => commit(e.shiftKey)}
                title={project.lore_project_id ? "Updates the LORE project made last time. Shift-click: make a separate new project" : undefined}>
                → {project.lore_project_id ? "UPDATE" : "SEND"} {countToSend(entities.filter((e) => e.keep))} ENTRIES {project.lore_project_id ? "IN" : "TO"} LORE
              </button>
            )}
            {entities.length > 0 && (
              <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "stretch" }}>
                <button className="signal-btn" style={{ ...btn, flex: 1, opacity: castJob?.status === "running" ? 0.6 : 1 }}
                  disabled={castJob?.status === "running"} onClick={makeCastCards}
                  title="A full character card for each kept main character (up to 8), written from the fic, set at the starting point, aware of the lorebook">
                  {castJob?.status === "running" ? (castJob.message || "WRITING CARDS…") : `⚇ ${(t.castCards || "Cards for main cast").toUpperCase()} (${entities.filter((e) => e.keep && e.entity_type === "character" && e.tier === "main").length})`}
                </button>
                <label className="signal-btn" style={{ ...btn, display: "flex", alignItems: "center", gap: 6, fontSize: 11, cursor: "pointer" }}
                  title="Also write one card that plays the whole cast together (up to 6 members)">
                  <input type="checkbox" checked={castGroup} onChange={(e) => setCastGroup(e.target.checked)} /> + GROUP
                </label>
              </div>
            )}
            {entities.length > 0 && (
              <button className="signal-btn" style={{ ...btn, width: "100%", marginTop: 8, opacity: cardBusy === "narrator" ? 0.6 : 1 }}
                disabled={!!cardBusy} onClick={makeNarrator}
                title="A narrator / game-master card for roleplaying the whole world, with this story's lore embedded">
                {cardBusy === "narrator" ? "WRITING NARRATOR CARD…" : "⚑ WORLD NARRATOR CARD"}
              </button>
            )}
            {project.lore_project_id && (
              <button className="signal-btn" style={{ ...btn, width: "100%", marginTop: 8 }} onClick={onOpenLore}>OPEN LORE STUDIO</button>
            )}
          </>)}
        </section>

        {/* ───────── RIGHT: review ───────── */}
        <section className="signal-panel signal-panel-delay-3" style={panelStyle}>
          <h2 className="signal-heading" style={headingStyle}>REVIEW</h2>
          {!entities.length && (
            <div style={{ color: "var(--signal-text-dim)", fontSize: 13, padding: "12px 0", textAlign: "center" }}>Extracted entities appear here.</div>
          )}

          {entities.length > 0 && (<>
            {flaggedCount > 0 && (
              <div style={{ border: "1px solid #c84a3a", color: "#c84a3a", padding: "8px 12px", fontSize: 12, marginBottom: 8 }}>
                ⊗ {flaggedCount} character(s) flagged under 18 / check age. Keep romantic or sexual content out of anything involving them.
              </div>
            )}
            <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
              <input style={{ ...input, flex: 1, minWidth: 120, padding: "6px 10px", fontSize: 12 }} placeholder="Search entries..." value={search} onChange={(e) => setSearch(e.target.value)} />
              <select style={{ ...input, width: "auto", padding: "6px 10px", fontSize: 12 }} value={filterType} onChange={(e) => setFilterType(e.target.value)}>
                <option value="all">all types</option>
                {ENTITY_TYPES.filter((x) => x !== "event").map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
              <select style={{ ...input, width: "auto", padding: "6px 10px", fontSize: 12 }} value={filterIssue} onChange={(e) => setFilterIssue(e.target.value)}>
                <option value="all">all entries</option>
                <option value="any">any problem</option>
                <option value="dup">duplicates</option>
                <option value="empty">empty</option>
                <option value="junk">junk?</option>
                <option value="nokeys">no keywords</option>
                <option value="fic">fic-specific</option>
              </select>
              <select style={{ ...input, width: "auto", padding: "6px 10px", fontSize: 12 }} value={filterTier} onChange={(e) => setFilterTier(e.target.value)}>
                <option value="all">all importance</option>
                <option value="main">main</option>
                <option value="supporting">supporting</option>
                <option value="one-off">one-off</option>
              </select>
              <select style={{ ...input, width: "auto", padding: "6px 10px", fontSize: 12 }} value={filterFlag} onChange={(e) => setFilterFlag(e.target.value)}>
                <option value="all">all ages</option>
                <option value="flagged">flagged</option>
                <option value="minor">under 18</option>
                <option value="check">check</option>
                <option value="unknown">unknown</option>
              </select>
            </div>
            {(issueCount > 0) && (
              <div style={{ border: "1px solid var(--signal-border)", padding: 8, marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: "var(--signal-text-dim)", marginBottom: 6 }}>
                  ⚠ {issueCount} with problems{dupCount ? ` · ${dupCount} extra duplicate${dupCount === 1 ? "" : "s"}` : ""}
                </div>
                <div style={toolbarGrid}>
                  <button className="signal-btn" style={btnTool} onClick={() => selectProblems("issues")} title="Tick every duplicate extra, empty and junk entry">SELECT PROBLEMS</button>
                  {dupCount > 0 && <button className="signal-btn" style={btnTool} onClick={() => selectProblems("dups")} title="Tick every copy except the best one">SELECT DUPES</button>}
                  {dupCount > 0 && <button className="signal-btn" style={btnTool} onClick={mergeDuplicates} title="Combine each group of same-named entries into one">MERGE DUPES</button>}
                </div>
              </div>
            )}
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8, flexWrap: "wrap", fontSize: 11 }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer", flex: "1 1 auto" }}>
                <input type="checkbox" checked={showOneOffs} onChange={(e) => setShowOneOffs(e.target.checked)} /> show one-offs
                {oneOffHidden > 0 && <span style={{ color: "var(--signal-text-dim)" }}>({oneOffHidden} hidden)</span>}
              </label>
              {lastDeleted.length > 0 && (
                <button className="signal-btn" style={btnTool} onClick={undoDelete} title="Restore what you just deleted (U)">↶ UNDO</button>
              )}
              <button className={showTrash ? "signal-btn signal-btn-active" : "signal-btn"} style={{ ...btnTool,
                background: showTrash ? "var(--signal-btn-active-bg)" : undefined, color: showTrash ? "var(--signal-btn-active-text)" : undefined }}
                onClick={() => setShowTrash((v) => !v)}>TRASH ({(project.trash || []).length})</button>
            </div>

            {showTrash && (
              <div style={{ border: "1px solid var(--signal-border)", marginBottom: 8 }}>
                {(project.trash || []).length === 0 && <div style={{ padding: 12, fontSize: 12, color: "var(--signal-text-dim)", textAlign: "center" }}>The trash is empty.</div>}
                {(project.trash || []).map((x) => (
                  <div key={x.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderBottom: "1px solid var(--signal-border)", fontSize: 12 }}>
                    <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      <b>{x.name}</b> <span style={{ opacity: 0.6 }}>· {x.entity_type}</span>
                    </span>
                    <button className="signal-btn" style={btnSm} onClick={() => restoreOne(x.id)}>RESTORE</button>
                  </div>
                ))}
                {(project.trash || []).length > 0 && (
                  <div style={{ padding: 8, textAlign: "right" }}>
                    <button className="signal-btn" style={{ ...btnSm, borderColor: "#c84a3a", color: "#c84a3a" }} onClick={emptyTrash}>EMPTY TRASH</button>
                  </div>
                )}
              </div>
            )}

            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8, flexWrap: "wrap", fontSize: 11 }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer", flex: "1 1 auto" }}>
                <input type="checkbox" checked={shown.length > 0 && shown.every((e) => checked.has(e.id))} onChange={toggleAllShown} /> all shown
                {checked.size > 0 && <span style={{ color: "var(--signal-text-dim)" }}>· {checked.size} selected</span>}
              </label>
            </div>
            {checked.size > 0 && (
              <div style={{ ...toolbarGrid, marginBottom: 8 }}>
                <button className="signal-btn" style={btnTool} onClick={() => bulkKeep(true)}>KEEP</button>
                <button className="signal-btn" style={btnTool} onClick={() => bulkKeep(false)}>SKIP</button>
                <button className="signal-btn" style={{ ...btnTool, borderColor: "#c84a3a", color: "#c84a3a" }} onClick={bulkDelete}>DELETE</button>
                {checked.size >= 2 && <button className="signal-btn" style={btnTool} onClick={mergeChecked}>⇉ MERGE</button>}
              </div>
            )}

            <div style={{ maxHeight: 300, overflowY: "auto", border: "1px solid var(--signal-border)" }}>
              {shown.map((e) => (
                <div key={e.id} onClick={() => selectEntity(e)} style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", cursor: "pointer",
                  borderBottom: "1px solid var(--signal-border)", opacity: e.keep ? 1 : 0.45,
                  background: selectedId === e.id ? "var(--signal-btn-active-bg)" : "transparent",
                  color: selectedId === e.id ? "var(--signal-btn-active-text)" : "var(--signal-text)",
                }}>
                  <input type="checkbox" checked={checked.has(e.id)} title="select for merge"
                    onClick={(ev) => ev.stopPropagation()}
                    onChange={() => setChecked((s) => { const n = new Set(s); n.has(e.id) ? n.delete(e.id) : n.add(e.id); return n; })} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.name}</div>
                    <div style={{ fontSize: 11, opacity: 0.7 }}>{e.entity_type} · {e.mentions} chunk{e.mentions === 1 ? "" : "s"}{e.age ? ` · age ${e.age}` : ""}</div>
                  </div>
                  <TierBadge tier={e.tier} />
                  <OriginBadge origin={e.origin} />
                  {e.entity_type === "character" && <Flag flag={e.age_flag} />}
                  <IssueBadges i={issues.get(e.id)} />
                  {e.entity_type === "event" && e.confidence === "low" && (
                    <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px", background: "#b8860b", color: "#fff" }}>UNSURE</span>
                  )}
                  <button onClick={(ev) => toggleKeep(e, ev)} title={e.keep ? "Included — click to exclude" : "Excluded — click to include"}
                    style={btnSm}>{e.keep ? "KEEP" : "SKIP"}</button>
                </div>
              ))}
              {shown.length === 0 && <div style={{ padding: 12, fontSize: 12, color: "var(--signal-text-dim)", textAlign: "center" }}>No matches.</div>}
            </div>
            <div style={{ ...hint, marginTop: 6 }}>Keys: J/K or ↑/↓ move · X keep/skip · Del to trash · U undo · Ctrl+S save</div>

            {timelineEvents.length > 0 && (<>
              <div onClick={() => setShowTimeline((v) => !v)} style={{ cursor: "pointer", userSelect: "none" }}>
                <Divider label={`${showTimeline ? "▾" : "▸"} TIMELINE · ${timelineEvents.length} EVENTS · ${timelineEvents.filter((e) => e.keep).length} KEPT`} style={{ marginTop: 16 }} />
              </div>
              <div style={{ ...hint, marginTop: 0 }}>
                Not lore entries: each kept event is one line in the Story Timeline entry, in story order.
                Skip trivial moments; keep plot points.
              </div>
              {showTimeline && (
                <div style={{ maxHeight: 300, overflowY: "auto", border: "1px solid var(--signal-border)", marginTop: 6 }}>
                  {timelineEvents.map((e, n) => (
                    <div key={e.id} onClick={() => selectEntity(e)} style={{
                      display: "flex", alignItems: "center", gap: 8, padding: "5px 8px", cursor: "pointer", fontSize: 12,
                      borderBottom: "1px solid var(--signal-border)", opacity: e.keep ? 1 : 0.45,
                      background: selectedId === e.id ? "var(--signal-btn-active-bg)" : "transparent",
                      color: selectedId === e.id ? "var(--signal-btn-active-text)" : "var(--signal-text)",
                    }}>
                      <input type="checkbox" checked={checked.has(e.id)} onClick={(ev) => ev.stopPropagation()}
                        onChange={() => setChecked((s2) => { const nn = new Set(s2); nn.has(e.id) ? nn.delete(e.id) : nn.add(e.id); return nn; })} />
                      <span style={{ width: 26, flexShrink: 0, opacity: 0.6, textAlign: "right" }}>{n + 1}.</span>
                      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {e.name}
                        {e.first_chunk >= 0 && <span style={{ opacity: 0.55 }}> · part {e.first_chunk + 1}</span>}
                      </span>
                      {e.confidence === "low" && <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px", background: "#b8860b", color: "#fff" }}>UNSURE</span>}
                      <button onClick={(ev) => toggleKeep(e, ev)} style={btnSm}>{e.keep ? "KEEP" : "SKIP"}</button>
                    </div>
                  ))}
                </div>
              )}
            </>)}

            {draft && (
              <div style={{ marginTop: 4 }}>
                <Divider label="ENTRY EDITOR" style={{ marginTop: 16 }} />
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
                  <button className="signal-btn" style={btnSm} onClick={() => stepEntity(-1)} title="Previous entry">‹ PREV</button>
                  <button className="signal-btn" style={btnSm} onClick={() => stepEntity(1)} title="Next entry">NEXT ›</button>
                  <TierBadge tier={draft.tier} />
                  <OriginBadge origin={draft.origin} />
                  <IssueBadges i={issues.get(draft.id)} />
                  <span style={{ flex: 1, fontSize: 11, textAlign: "right", color: "var(--signal-text-dim)" }}>
                    {saving ? "saving…" : dirty ? "● editing (autosaves)" : "✓ saved"}
                  </span>
                  <button className="signal-btn" style={btnSm} onClick={() => toggleKeep(draft)}
                    title={draft.keep ? "Included — click to exclude" : "Excluded — click to include"}>{draft.keep ? "KEEP" : "SKIP"}</button>
                </div>
                <div style={label}>NAME</div>
                <input style={input} value={draft.name} onChange={(e) => editDraft({ name: e.target.value })} />
                <div style={{ display: "flex", gap: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={label}>TYPE</div>
                    <select style={input} value={draft.entity_type} onChange={(e) => editDraft({ entity_type: e.target.value })}>
                      {ENTITY_TYPES.map((x) => <option key={x} value={x}>{x}</option>)}
                    </select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={label}>AGE {draft.entity_type === "character" && <Flag flag={draft.age_flag} />}</div>
                    <input style={input} value={draft.age} onChange={(e) => editDraft({ age: e.target.value })} />
                  </div>
                </div>
                <div style={label}>ORIGIN (vs. the original work)</div>
                <select style={input} value={draft.origin || ""} onChange={(e) => editDraft({ origin: e.target.value })}>
                  <option value="">not set / not fan fiction</option>
                  <option value="canon">canon (as in the original work)</option>
                  <option value="altered">altered by this story</option>
                  <option value="original">original to this story</option>
                </select>
                <div style={label}>ALIASES (comma separated)</div>
                <input style={input} value={draft.aliasesCsv} onChange={(e) => editDraft({ aliasesCsv: e.target.value })} />
                <div style={label}>TRIGGER KEYWORDS (comma separated)</div>
                <input style={input} value={draft.keywordsCsv} onChange={(e) => editDraft({ keywordsCsv: e.target.value })} />
                {draft.evidence && (
                  <div style={{ ...hint, marginTop: 8 }}>
                    Evidence: “{draft.evidence}”{draft.confidence ? ` · confidence ${draft.confidence}` : ""}
                    {draft.story_order ? ` · order: ${draft.story_order}` : ""}
                  </div>
                )}
                <div style={label}>CONTENT</div>
                <textarea style={{ ...input, height: Math.max(130, Math.min(460, 40 + Math.ceil((draft.content || "").length / 48) * 20)), resize: "vertical" }} value={draft.content} onChange={(e) => editDraft({ content: e.target.value })} />
                {draft.entity_type === "character" && (<>
                  <div style={label}>RELATIONSHIPS (one per line: Name — relation)</div>
                  <textarea style={{ ...input, height: 70, resize: "vertical" }} value={draft.relText}
                    placeholder={"Rikku — cousin; teammate\nPaine — friend"} onChange={(e) => editDraft({ relText: e.target.value })} />
                  <div style={label}>VOICE SAMPLES (one per line)</div>
                  <textarea style={{ ...input, height: 70, resize: "vertical" }} value={draft.voiceText} onChange={(e) => editDraft({ voiceText: e.target.value })} />
                </>)}
                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  <button className="signal-btn" style={btnPrimary} onClick={() => saveDraft(false)}>SAVE</button>
                  <button className="signal-btn" style={{ ...btn, borderColor: "#c84a3a", color: "#c84a3a", background: "transparent" }}
                    onClick={removeEntity} title="Moves it to the trash (restorable)">DELETE</button>
                  {draft.entity_type === "character" && onMakeCard && (
                    <button className="signal-btn" style={{ ...btn, marginLeft: "auto", opacity: cardBusy === draft.id ? 0.6 : 1 }} disabled={!!cardBusy}
                      onClick={() => makeCard(draft)} title="Open this character in the CHARACTER studio as a source, ready to generate a full card">
                      {cardBusy === draft.id ? "PREPARING…" : "→ MAKE CARD"}
                    </button>
                  )}
                </div>
              </div>
            )}
          </>)}
        </section>
      </div>

    </div>
  );
}
