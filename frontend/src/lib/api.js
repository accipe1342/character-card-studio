/**
 * api.js — Frontend API client
 * ==============================
 * All fetch() calls to the Flask backend live here. No component
 * should call fetch() directly — they import from this file instead.
 * This makes it easy to change base URLs, add auth headers, or mock
 * responses for testing without touching component code.
 *
 * HELPER
 * ------
 * readJsonSafe(res)
 *   Safely parses a fetch Response as JSON regardless of status code.
 *   Used internally by all exported functions.
 *
 * CHARACTER CARD FUNCTIONS
 * ------------------------
 * startScrape(url)               POST /api/scrape
 * startCharacterGenerate(...)    POST /api/generate
 * startBatchGenerate(...)        POST /api/generate/batch
 * saveCard(cardId, card)         POST /api/card/:id
 * getCard(cardId)                GET  /api/card/:id
 * listCards()                    GET  /api/cards
 * deleteCard(cardId)             DELETE /api/card/:id
 * duplicateCard(cardId)          POST /api/card/:id/duplicate
 * regenerateField(...)           POST /api/card/:id/field/regen
 * regenerateFullCard(...)        POST /api/generate
 * fetchModels(provider)          GET  /api/models/:provider
 * getImageProxyUrl(imageUrl)     Returns proxied URL string (no fetch)
 *
 * LORE FUNCTIONS
 * --------------
 * startLoreCrawl(...)            POST /api/lore/crawl
 * startMultiLore(...)            POST /api/lore/multi
 * listLoreProjects()             GET  /api/lore/projects
 * createLoreProject(name)        POST /api/lore/project
 * renameLoreProject(id, name)    PATCH /api/lore/project/:id
 * deleteLoreProject(id)          DELETE /api/lore/project/:id
 * listLoreEntries(crawlId)       GET  /api/lore/entries/:id
 * newLoreEntry(projectId, title) POST /api/lore/entry/new
 * generateLoreEntry(...)         POST /api/lore/entry/generate
 * updateLoreEntry(id, entry)     PATCH /api/lore/entry/:id
 * deleteLoreEntry(id)            DELETE /api/lore/entry/:id
 * moveEntryToProject(id, projId) PATCH /api/lore/entry/:id/project
 * exportLorebook(projectId)      GET  /api/lore/export?project_id=N  (no id = every project)
 *
 * JOB POLLING
 * -----------
 * getJob(jobId)                  GET  /api/job/:id
 *   Returns job status, progress, message, result, error.
 *
 * HOW TO EXTEND
 * -------------
 * - Add a new API call: export an async function that calls fetch()
 *   with the correct method/headers/body. Use readJsonSafe() to parse
 *   the response and throw on error.
 * - Change the base URL: add a BASE_URL constant and prefix all paths.
 * - Add auth: add an Authorization header to all requests.
 */

export async function readJsonSafe(res) {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    if (res.status === 404) {
      // a route the frontend knows but the running backend doesn't: almost always an old backend process
      throw new Error("The backend doesn't have this feature yet (404). Restart the backend (close its window or Ctrl+C, then start it again) and refresh the page.");
    }
    if (res.status === 502 || res.status === 504 || res.status === 500 && !text) {
      throw new Error("Can't reach the backend. Is it running? Start it and refresh the page.");
    }
    throw new Error(`Server returned non-JSON (${res.status}): ${text.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 200)}`);
  }
}

export async function startScrape(url) {
  const res = await fetch("/api/scrape/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || `Scrape failed (${res.status})`);
  return data;
}

export async function getJob(jobId) {
  const res = await fetch(`/api/job/${jobId}`);
  const data = await readJsonSafe(res);
  if (res.status === 404) {
    // the backend restarted and the job is gone: report it as failed so every poller stops cleanly
    const msg = data.error || "This job no longer exists (the backend restarted). Run it again.";
    return { status: "failed", stage: "failed", progress: 100, message: msg, error: msg };
  }
  if (!res.ok) throw new Error(data.error || "Job request failed");
  return data;
}

/** asNew: save as a new card instead of replacing the latest card made from this source. */
/** opts: {story_point, user_role, token_target, style, deep, lore_project_id} (all optional). */
export async function startCharacterGenerate(sourceId, provider, model, asNew = false, opts = {}) {
  const res = await fetch("/api/generate/start", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      source_id: sourceId,
      provider,
      model,
      as_new: asNew,
      ...opts,
    }),
  });

  const data = await readJsonSafe(res);
  if (!res.ok) {
    throw new Error(data.error || `Generation failed (${res.status})`);
  }

  return data;
}

export async function regenerateFullCard(cardId) {
  const res = await fetch(`/api/generate/full/${cardId}`, {
    method: "POST",
  });

  const data = await readJsonSafe(res);
  if (!res.ok) {
    throw new Error(data.error || "Full card regeneration failed");
  }

  return data;
}

export async function regenerateField(cardId, fieldName, options = {}) {
  const {
    customPrompt = "",
    includeCurrentCard = true,
    includeSource = true,
  } = options;

  const formData = new URLSearchParams();
  formData.append("field_name", fieldName);
  formData.append("custom_prompt", customPrompt);
  formData.append("include_current_card", String(includeCurrentCard));
  formData.append("include_source", String(includeSource));

  const res = await fetch(`/api/generate/field/${cardId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: formData.toString(),
  });

  const data = await readJsonSafe(res);
  if (!res.ok) {
    throw new Error(data.error || "Field regeneration failed");
  }

  return data;
}

export async function saveCard(cardId, card) {
  const res = await fetch(`/api/save-card/${cardId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(card),
  });

  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Save failed");

  return data;
}
export async function listCards() {
  const res = await fetch("/api/cards");
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed to load library");
  return data;
}

export async function loadCard(cardId) {
  const res = await fetch(`/api/card/${cardId}`);
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed to load card");
  // Returns { card, source }
  return data;
}

export async function fetchModels(provider) {
  const res = await fetch(`/api/models/${provider}`);
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed to fetch models");
  return data.models;
}

export async function compileField(cardId, target) {
  const res = await fetch(`/api/generate/compile/${cardId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Compile failed");
  return data;
}

export async function regenerateGreeting(cardId, idx, customPrompt = "") {
  const res = await fetch(`/api/generate/greeting/${cardId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idx, custom_prompt: customPrompt }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Greeting regeneration failed");
  return data;
}


export async function deleteCard(cardId) {
  const res = await fetch(`/api/card/${cardId}`, { method: "DELETE" });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Delete failed");
  return data;
}

export async function renameCard(cardId, name) {
  const res = await fetch(`/api/card/${cardId}/name`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Rename failed");
  return data;
}

export async function duplicateCard(cardId) {
  const res = await fetch(`/api/card/${cardId}/duplicate`, { method: "POST" });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Duplicate failed");
  return data;
}

// ── Lore Studio ──────────────────────────────────────────────────────────────

export async function startLoreCrawl(opts) {
  const res = await fetch("/api/lore/crawl/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Crawl start failed");
  return data;
}

export async function listLoreEntries() {
  const res = await fetch("/api/lore/entries");
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed to load entries");
  return data;
}

export async function getLoreEntry(id) {
  const res = await fetch(`/api/lore/entry/${id}`);
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed to load entry");
  return data;
}

export async function updateLoreEntry(id, entry) {
  const res = await fetch(`/api/lore/entry/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Update failed");
  return data;
}

/** Moves the entry to the LORE trash (purge=true deletes it for good). */
export async function deleteLoreEntry(id, purge = false) {
  const res = await fetch(`/api/lore/entry/${id}${purge ? "?purge=1" : ""}`, { method: "DELETE" });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Delete failed");
  return data;
}

/** Empty a LORE project but keep it (same id). */
export async function clearLoreProject(projectId) {
  const res = await fetch(`/api/lore/project/${projectId}/entries`, { method: "DELETE" });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Clear failed");
  return data;
}

/** Remove generic words and other entries' names from keywords. apply=false previews. */
export async function cleanLoreKeywords(projectId, apply = false) {
  const res = await fetch(`/api/lore/project/${projectId}/clean-keywords`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ apply }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Keyword cleanup failed");
  return data;
}

export async function exportLorebook(projectId) {
  const res = await fetch(projectId != null ? `/api/lore/export?project_id=${encodeURIComponent(projectId)}` : "/api/lore/export");
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Export failed");
  return data;
}

export async function startLoreSingle(opts) {
  const res = await fetch("/api/lore/single", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed to start");
  return data;
}

export async function startLoreMulti(opts) {
  const res = await fetch("/api/lore/multi", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed to start");
  return data;
}

export async function listLoreProjects() {
  const res = await fetch("/api/lore/projects");
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed");
  return data;
}

export async function createLoreProject(name) {
  const res = await fetch("/api/lore/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed");
  return data;
}

export async function renameLoreProject(id, name) {
  const res = await fetch(`/api/lore/project/${id}/name`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed");
  return data;
}

export async function deleteLoreProject(id) {
  const res = await fetch(`/api/lore/project/${id}`, { method: "DELETE" });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed");
  return data;
}

export async function newLoreEntry(projectId, title = "New Entry") {
  const res = await fetch("/api/lore/entry/new", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, title }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed");
  return data;
}

export async function generateLoreEntry(opts) {
  const res = await fetch("/api/lore/entry/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed");
  return data;
}

export async function startBatchGenerate(urls, provider, model) {
  const res = await fetch("/api/generate/batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls, provider, model }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Batch generate failed");
  return data;
}

export function getImageProxyUrl(imageUrl) {
  if (!imageUrl) return "";
  return `/api/image-proxy?url=${encodeURIComponent(imageUrl)}`;
}

export async function moveEntryToProject(loreId, projectId) {
  const res = await fetch(`/api/lore/entry/${loreId}/project`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId ?? null }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Move failed");
  return data;
}

export async function newBlankCard(name = "New Character") {
  const res = await fetch("/api/card/new", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Failed to create card");
  return data;
}

// ─────────────────────────────────────────────────────────────────────────────
// TEXT STUDIO (fanfiction / long-form text -> lorebook)
// ─────────────────────────────────────────────────────────────────────────────
async function _textJson(res, fallback) {
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || fallback);
  return data;
}

const _post = (url, body) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

/** Paste: textIngest({name, text, chunk_chars}). File: textIngestFile(file, name, chunk_chars). */
export async function textIngest(opts) {
  return _textJson(await _post("/api/text/ingest", opts), "Ingest failed");
}
export async function textIngestFile(file, name = "", chunkChars = 6000) {
  const fd = new FormData();
  fd.append("file", file);
  if (name) fd.append("name", name);
  fd.append("chunk_chars", String(chunkChars));
  return _textJson(await fetch("/api/text/ingest", { method: "POST", body: fd }), "Upload failed");
}
/** Add text to the end of a project (file: .jsonl SillyTavern chat / .txt / .md / .html / .epub, or a string). */
export async function appendText(projectId, fileOrText) {
  if (typeof fileOrText === "string") return _textJson(await _post(`/api/text/project/${projectId}/append`, { text: fileOrText }), "Could not add the text");
  const fd = new FormData();
  fd.append("file", fileOrText);
  return _textJson(await fetch(`/api/text/project/${projectId}/append`, { method: "POST", body: fd }), "Could not add the text");
}
export async function textIngestUrls(opts) {
  return _textJson(await _post("/api/text/ingest-urls", opts), "Fetch failed");
}
export async function listTextProjects() {
  return _textJson(await fetch("/api/text/projects"), "Failed to list text projects");
}
export async function getTextProject(id) {
  return _textJson(await fetch(`/api/text/project/${id}`), "Failed to load text project");
}
export async function deleteTextProject(id) {
  return _textJson(await fetch(`/api/text/project/${id}`, { method: "DELETE" }), "Delete failed");
}
export async function rechunkTextProject(id, chunkChars) {
  return _textJson(await _post(`/api/text/project/${id}/rechunk`, { chunk_chars: chunkChars }), "Rechunk failed");
}
export async function startTextExtract(id, opts) {
  return _textJson(await _post(`/api/text/project/${id}/extract`, opts), "Failed to start extraction");
}
export async function patchTextEntity(id, data) {
  return _textJson(
    await fetch(`/api/text/entity/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
    "Save failed"
  );
}
/** Moves the entry to the trash (restorable); purge=true deletes it for good. */
export async function deleteTextEntity(id, purge = false) {
  return _textJson(await fetch(`/api/text/entity/${id}${purge ? "?purge=1" : ""}`, { method: "DELETE" }), "Delete failed");
}
export async function restoreTextEntity(id) {
  return _textJson(await _post(`/api/text/entity/${id}/restore`, {}), "Restore failed");
}
export async function emptyTextTrash(projectId) {
  return _textJson(await fetch(`/api/text/project/${projectId}/trash`, { method: "DELETE" }), "Emptying the trash failed");
}
/** Story So Far preview. upto: chunk index the roleplay starts after (-1 = end); omit to get the saved one. */
export async function getTextRecap(projectId, upto) {
  const q = upto === undefined || upto === null ? "" : `?upto=${upto}`;
  return _textJson(await fetch(`/api/text/project/${projectId}/recap${q}`), "Failed to load the recap");
}
/** timeline: chapter-log text for the Story Timeline entry ("" = one line per kept event; undefined = leave as is). */
export async function saveTextRecap(projectId, text, upto, timeline, position) {
  const body = timeline === undefined ? { text, upto } : { text, upto, timeline };
  if (position) body.position = position;      // "before" (before the card) | "depth" (@ depth 4, as system)
  return _textJson(
    await fetch(`/api/text/project/${projectId}/recap`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    "Failed to save the recap"
  );
}
/** Where SillyTavern inserts the Story So Far: "before" the character card, or "depth" (@ depth 4 as system). */
export async function saveRecapPosition(projectId, position) {
  return _textJson(
    await fetch(`/api/text/project/${projectId}/recap`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ position }) }),
    "Failed to save the recap placement"
  );
}
/** Story So Far (current status) + chapter-log timeline written by the model. Saved server-side. */
export async function writeRecapAI(projectId, opts) {
  return _textJson(await _post(`/api/text/project/${projectId}/recap/ai`, opts), "AI recap failed");
}
/** A reviewed character -> CHARACTER studio source ({source_id, source}). */
export async function textEntityToSource(id) {
  return _textJson(await _post(`/api/text/entity/${id}/to-source`, {}), "Could not prepare the character");
}
/** Critic: start a critique job ({job_id}); scope = chunk indices ([] = whole text). */
export async function startCritique(projectId, opts) {
  return _textJson(await _post(`/api/text/project/${projectId}/critique`, opts), "Could not start the critique");
}
export async function listCritiques(projectId) {
  return _textJson(await fetch(`/api/text/project/${projectId}/critiques`), "Could not load critiques");
}
export async function getCritique(id) {
  return _textJson(await fetch(`/api/text/critique/${id}`), "Could not load the critique");
}
/** Score every part on its own (a job; the result is saved as a critique with scope "Chapter sweep"). */
export async function startSweep(projectId, opts) {
  return _textJson(await _post(`/api/text/project/${projectId}/critique/sweep`, opts), "Could not start the sweep");
}
/** Rewrite the paragraph around a quoted line with a fix applied: {found, label, original, rewrite, notes}. */
export async function rewritePassage(projectId, opts) {
  return _textJson(await _post(`/api/text/project/${projectId}/rewrite`, opts), "Rewrite failed");
}
export async function deleteCritique(id) {
  return _textJson(await fetch(`/api/text/critique/${id}`, { method: "DELETE" }), "Delete failed");
}
/** World Narrator card for the whole story ({card_id, card: V2 JSON, entries}). */
/** Cards for the kept main cast (or opts.ids), one after another, plus an optional group card. Returns {job_id, count}. */
export async function startCastCards(projectId, opts) {
  return _textJson(await _post(`/api/text/project/${projectId}/cast-cards`, opts), "Could not start the cast cards");
}
export async function makeNarratorCard(projectId, opts) {
  return _textJson(await _post(`/api/text/project/${projectId}/narrator`, opts), "Narrator card failed");
}
export async function mergeTextEntities(projectId, ids) {
  return _textJson(await _post(`/api/text/project/${projectId}/merge`, { ids }), "Merge failed");
}
/** mode: undefined = update the LORE project made last time (if it still exists), "new" = always a new project. */
export async function commitTextProject(projectId, mode) {
  return _textJson(await _post(`/api/text/project/${projectId}/commit`, mode ? { mode } : {}), "Commit failed");
}

/** Build a Character Card V2 object server-side (single source of truth for JSON + PNG export). */
export async function exportCardV2(card, mode = "natural", loreProjectId = null, spec = "v2") {
  const res = await fetch("/api/export/v2", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ card, mode, lore_project_id: loreProjectId || null, spec }),
  });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Export failed");
  return data;
}

/** DeepLore (Obsidian vault) export of one LORE project: a zip of markdown notes. */
export async function exportDeepLore(projectId) {
  const res = await fetch(`/api/lore/export/deeplore${projectId ? `?project_id=${projectId}` : ""}`);
  if (!res.ok) {
    const data = await readJsonSafe(res);
    throw new Error(data.error || "DeepLore export failed");
  }
  return res.blob();
}

// ─────────────────────────────────────────────────────────────────────────────
// Config: model presets, backups, usage
// ─────────────────────────────────────────────────────────────────────────────
async function _json(res, fallback) {
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || fallback);
  return data;
}
const _postJson = (url, body) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

let _presetCache = null;
/** Model presets per task: {extract|critic|card|lore: {provider, model}}. Cached for the page session. */
export async function getPresets(fresh = false) {
  if (_presetCache && !fresh) return _presetCache;
  _presetCache = await _json(await fetch("/api/config/presets"), "Could not load model presets");
  return _presetCache;
}
export async function savePresets(presets) {
  const r = await _json(await _postJson("/api/config/presets", presets), "Could not save model presets");
  _presetCache = r.presets;
  return r;
}
export async function listBackups() { return _json(await fetch("/api/backups"), "Could not list backups"); }
export async function makeBackup() { return _json(await _postJson("/api/backups", {}), "Backup failed"); }
export async function restoreBackup(name) { return _json(await _postJson("/api/backups/restore", { name }), "Restore failed"); }
export async function getUsage(days = 30) { return _json(await fetch(`/api/usage?days=${days}`), "Could not load usage"); }

// ─────────────────────────────────────────────────────────────────────────────
// LORE tools: activation simulator, links graph, trash
// ─────────────────────────────────────────────────────────────────────────────
export async function simulateLore(projectId, text, budget = 2048, wholeWords = false) {
  return _json(await _postJson("/api/lore/simulate", { project_id: projectId, text, budget, whole_words: wholeWords }), "Simulation failed");
}
export async function getLoreGraph(projectId) {
  return _json(await fetch(`/api/lore/project/${projectId}/graph`), "Could not load links");
}
export async function listLoreTrash(projectId) {
  return _json(await fetch(`/api/lore/trash${projectId ? `?project_id=${projectId}` : ""}`), "Could not load the trash");
}
export async function restoreLoreEntry(id) {
  return _json(await _postJson(`/api/lore/entry/${id}/restore`, {}), "Restore failed");
}
export async function emptyLoreTrash(projectId) {
  return _json(await fetch(`/api/lore/trash${projectId ? `?project_id=${projectId}` : ""}`, { method: "DELETE" }), "Could not empty the trash");
}

// ─────────────────────────────────────────────────────────────────────────────
// Bundles: TEXT / LORE projects and cards as one .zip
// ─────────────────────────────────────────────────────────────────────────────
export async function getBundleContents() { return _json(await fetch("/api/bundle/contents"), "Could not list projects"); }
export async function exportBundle(sel) {
  const res = await _postJson("/api/bundle/export", sel);
  if (!res.ok) { const d = await readJsonSafe(res); throw new Error(d.error || "Export failed"); }
  return res.blob();
}
export async function importBundle(file) {
  const fd = new FormData();
  fd.append("file", file);
  return _json(await fetch("/api/bundle/import", { method: "POST", body: fd }), "Import failed");
}

/** One search across cards, lore entries, TEXT projects and reviewed TEXT entities. */
export async function searchAll(q, limit = 8) {
  return _json(await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`), "Search failed");
}
