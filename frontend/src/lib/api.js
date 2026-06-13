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
 * exportLorebook(crawlId)        GET  /api/lore/export/:id
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
    throw new Error(`Server returned non-JSON: ${text.slice(0, 200)}`);
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
  if (!res.ok) throw new Error(data.error || "Job request failed");
  return data;
}

export async function startCharacterGenerate(sourceId, provider, model) {
  const res = await fetch("/api/generate/start", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      source_id: sourceId,
      provider,
      model
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

export async function deleteLoreEntry(id) {
  const res = await fetch(`/api/lore/entry/${id}`, { method: "DELETE" });
  const data = await readJsonSafe(res);
  if (!res.ok) throw new Error(data.error || "Delete failed");
  return data;
}

export async function exportLorebook() {
  const res = await fetch("/api/lore/export");
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
