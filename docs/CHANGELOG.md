# Changelog

All notable changes to Character Card Studio are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [2.6.0] - 2026-11-12

### Added
- NieR-style look across the app: warm beige with warm dark grey text, staff-line borders top and bottom, a large
  thin studio title with ":: subtitle" and what is open on the right, dark header strips on panels, borderless
  buttons with offset shadows, a single drab red-orange accent, darker screen edges and a key-hint footer.
  Noto Sans JP is bundled (no internet needed). Dark mode follows the same rules.
- Toolbars grouped into menus. CHARACTER: Scrape, Generate Card, Options, Batch, then NEW ▾ (blank card, import),
  TOOLS ▾ (Audit, Interview, View Source) and EXPORT ▾ (JSON, V3 JSON, CHARX, embedded lorebook). LORE: GENERATE ▾
  (from URL, several URLs, from a prompt, deep extraction), New Entry, TOOLS ▾ (Clean Keywords, Test Activation,
  Links, Trash all entries), EXPORT ▾ (SillyTavern .json, Send to SillyTavern, Quick Replies, Bible / Data Bank,
  DeepLore) and Trash. The LORE entry editor has CONTENT / KEYS / SILLYTAVERN tabs.
- SCRIBE-01 has a personality: a patient, precise instructor over a composed, duty-first unit, self-aware about
  being a tool built to make cards; you can simply chat with her or keep her in character. The persona is an editable
  text file (`backend/config/helper_persona.txt`); the work rules always apply on top of it.
- SCRIBE-01 as a SillyTavern card: ⇩ CARD in the console (or GET /api/helper/card, ?format=json) gives a card PNG
  with the glossary embedded as her lorebook.
- `docs/DESIGN.md`: the design system in depth (principles, color and contrast, type, spacing, ornaments, every
  component, motion, copy, dark mode, a drop-in stylesheet and React components) for use in other projects.
- Import character cards: CHARACTER NEW ▾ > Import card takes a card PNG (V2 or V3 data inside), a card .json
  (V1, V2 or V3, from this app or others) or a .charx. It becomes a new card with its portrait; an embedded lorebook
  becomes a LORE project and is attached to the card. Route: POST /api/card/import.
- Helper (SCRIBE-01) in the CHARACTER, LORE and TEXT studios: a support unit you talk to in plain words.
  It can create and edit character cards, create lorebooks and add, edit or trash their entries, read TEXT
  projects and their entries, and explain SillyTavern and card-writing ideas.
- It works on what is open: the studio tells it the open card, lorebook, entry or story, and unsaved edits are
  saved before it reads anything. The studio reloads whatever it changed; if you edited the same item meanwhile,
  your version is kept and you are told.
- Every change is applied at once and shown under the reply with OPEN, KEEP and UNDO (KEEP ALL / UNDO ALL for a
  reply with several). UNDO restores the earlier state, removes what it created (entries go to the trash), and
  refuses when the item was changed since, so newer work is never overwritten.
- Keyword glossary for the helper (`backend/config/helper_glossary.json`): like World Info, entries whose keys
  appear in the recent messages are added to its prompt. Editable.
- Default card layout the helper follows: plain prose paragraphs (optional opening quote, overview, backstory,
  personality with a few speech samples, likes/dislikes/relationships, appearance), no PList/W++.
- Chats are stored and can be reopened from the panel. New routes under `/api/helper/`.
- It lives in a console along the bottom (chat on the left, changes on the right). Drag the top edge to resize,
  HIDE shrinks it to a bar, FLOAT makes it a window you can drag and resize, Ctrl+/ or the footer hint shows and
  hides it. Its place and size are remembered.
- PROSE SCAN: a HABITS section for patterns models fall into: "not X, but Y" emphasis, narrating what doesn't
  happen ("she doesn't move"), a reply that repeats the other speaker's words as a question, em-dash overuse and
  most paragraphs opening the same way. Per-chapter columns too. Generated cards get the same checks in their
  warnings, plus a warning when a field reads like a model refusal.
- 40 more stock phrases in `backend/config/ai_cliches.txt` ("smell of ozone", "after a beat", "breath hitched", ...).
- First message point of view (first / second / third person), tense and greeting length in CHARACTER ⚙ Options.
  Remembered in the browser and used by Generate Card, Batch Generate, regenerating the first message, example
  messages or greetings, and the alternate greetings panel. Left on "Model's choice", nothing changes.
- Generated text is cleaned up before it is saved: straight quotes, "..." for the ellipsis, no stray <p>/<div>/
  <span>/<br>, no doubled spaces or extra blank lines, no code fence around a field, no "Name:" in front of a
  greeting. XML-style section tags are kept; Chinese and Japanese text keeps its own quotes. Text you type is never
  changed.

### Fixed
- The SCRIBE-01 console looked and sized its buttons differently in light and dark mode; it now has its own buttons,
  identical in both. Scrolling inside it no longer moves the page behind it.
- Unavailable menu items now say what they need ("open a card first", "pick a lorebook first") instead of only
  looking faded. Escape closes the Interview dialog.
- A floating SCRIBE-01 window saved on a bigger screen opens fully on screen; menus near the edge of a phone open the
  other way instead of off-screen.
- The app no longer breaks in a private window or with site storage blocked (theme and language settings).
- Saving prompt templates or model presets with a partial request no longer blanks the templates, turns templates
  off or clears the other presets; numbers are checked.
- Saving a lore entry changes only the fields that were sent (a partial save could blank the title and content);
  keywords sent as text become a list; bad numbers are refused; a new entry for a missing lorebook is refused.
- Saving or exporting a card keeps every field in its shape (tags and greetings stay lists, the profile stays an object).
- Every API route answers a missing or broken request body with a readable JSON message instead of an HTML error page,
  and a missing card or entry is a 404 instead of a 500.
- SCRIBE-01 says when a message is over 6,000 characters instead of silently cutting it.
- A .charx import that would unpack to more than 200 MB is refused.
- Starting the app no longer floods the log with proxy errors: the browser opens once the backend answers, and
  SCRIBE-01 retries loading its last chat instead of forgetting it when the backend is still starting.
- Accent and dark-mode dim text darkened / lightened to meet 4.5:1 contrast.
- Cards the helper writes now fill the Structured view: it used field names the view does not show
  (speech_patterns, goals, fears, skills). It now uses the view's fields, maps common other names onto them, and
  fills the profile whenever it creates a card.

### Tests
- `backend/tests/test_helper.py` (through the real request code, with a scripted model) and browser suite
  `tests/e2e/e2e11.py`; `backend/tests/test_v26_writing.py` for the writing checks, clean-up and greeting style; `backend/tests/test_card_import.py`;
  browser suite `tests/e2e/e2e12.py` for the layout, console and import (tests/e2e/ui.py opens menus).

---

## [2.5.1] - 2026-11-11

### Fixed
Every feature that calls a model now copes with the ways real models stray from the requested format, instead of
failing or storing garbled text. Checked end to end through the real request code against a test server that
answers like real models do.
- Plain-text answers (common with roleplay-tuned models) are accepted wherever the answer is one piece of text:
  interview, trim, alternate greeting, compile description/personality, field regenerate, passage rewrite,
  entry condensing, arc summaries and the critic's per-chapter notes. Before, these failed with "the model call
  failed" or a JSON parse error.
- A single string where a list belongs is no longer split into letters (aliases "Mar" became M, a, r); "a, b, c"
  becomes three items. Affects TEXT extraction (quick and deep), tags, profile lists and event participants.
- A list or object where text belongs is joined into readable text instead of being stored as "['a', 'b']".
- Relations are read in the shapes models actually use ({"Tomas": "friend"}, "Tomas - friend", other key names)
  instead of being dropped; hyphenated names stay whole.
- Deep extraction matches details to the right entry when the model writes a fuller or shorter name
  ("Mara Vell" for "Mara"), instead of falling back to "Mentioned in ...".
- Critic and Chapter sweep read scores like "7/10" or "8 out of 10", and per-category scores as a list or an
  object; the score history no longer loses them.
- Field regenerate accepts a profile field the model put at the top level, and its errors come back as a
  readable message instead of a server error page.
- Lore entry generation accepts a bare list of entries or a single entry object, and no longer crashes on a sparse
  wiki page (no summary, infobox or abilities).
- A dialogue line that starts with a quote keeps its opening quote.

## [2.5.0] - 2026-11-11

### Added
- TEXT: **lore as of the starting point.** With "roleplay starts after" set, LORE entries and cards use only what the
  chapters up to that point say (age, relations, voice, facts); characters who first appear later are left out.
  A checkbox turns it off. Hand-edited entries are always used as written.
- TEXT: entry tabs **BY CHAPTER** (what each chapter's extraction said, with a ROLEPLAY STARTS HERE line) and
  **MENTIONS** (every line of the text that names the entry, by chapter; one-word names keep their capital letter
  so ordinary words don't match).
- TEXT: **UPDATE IN LORE preview.** Before anything is written, see each entry that would be refreshed (word diff),
  added, sent to the LORE trash or kept as you edited it, and untick any to leave them as they are.
- TEXT: places can get an **"Often here:"** line (who is usually found there, counted from events and shared
  chapters; no model call). On by default, with a checkbox.
- TEXT: **INTERVIEW** tab on characters (and an Interview button in CHARACTER): ask the character questions to test
  its voice, then ✓ CHECK AGAINST NOTES lists answers that contradict its notes. Not saved.
- TEXT: **◇ RELATIONSHIP MAP**: who is linked to whom, drawn as a map (squares are characters, diamonds factions,
  size by number of links). Drag, click for both sides of each relation, open in review, download as SVG.
- TEXT: **secrets / who knows this** (optional, per entry): a fact only some characters know becomes its own LORE
  entry with SillyTavern's character filter, so it only reaches the prompt when one of them is speaking. The
  character's interview knows its own secrets. Never put in the Data Bank pack.
- TEXT and LORE: **story bible** as Markdown or a printable page (portraits, print / save as PDF), and a
  **Data Bank pack** (.zip, one Markdown note per entry, with instructions) for SillyTavern's Data Bank.
- TEXT and LORE: **SillyTavern Quick Replies**: a Quick Reply set with a button per place and character plus
  recap / time skip / scene check, to download or send.
- Critic: **✓ PROSE SCAN** (instant, no model call): stock "AI-sounding" phrases with examples, overused words,
  filler, -ly adverbs, dialogue tags, repeated sentence starts, and a by-chapter table (story order or worst first).
  The phrase list is `backend/config/ai_cliches.txt`; edit it to taste.
- LORE: entries over ~150 tokens show a size hint and stock phrases; long ones get a LONG badge. **✂ TRIM** asks
  the model for a shorter version and shows it next to the original before anything changes.
- CHARACTER: profile fields **With strangers** and **With people close to them** (how the character changes with
  closeness). AUDIT now also flags heavy trauma wording, many absolutes ("always", "never"), oversized group cards,
  missing or identical layers, and stock phrases; a long description gets ✂ TRIM DESCRIPTION.
- **Send to SillyTavern**: cards (PNG with the portrait and the attached lorebook; sending again replaces the card
  instead of adding a copy), lorebooks (World Info) and Quick Reply sets go straight into a running SillyTavern.
  Config → SillyTavern: address, optional basic-auth user and password (stored masked), TEST CONNECTION.
  Tested against SillyTavern 1.19 with basic auth.
- **Saved portraits**: card pictures are stored in `data/images` and come back when a card is reopened; the
  Library shows thumbnails. TEXT characters can have a picture that MAKE CARD carries over. Project bundles
  include the pictures, plus a ready-to-use card PNG for each card that has one.
- CHARACTER: **CHARX** export (Character Card V3 zip with the portrait and the attached lorebook).
- tests: pytest for every new endpoint (including live SillyTavern tests, skipped when none is running) and
  browser suites e2e7–e2e10.

### Changed
- CHARACTER toolbar is two rows: making and checking cards on top, exports below.
- Rebuild list and hand merges keep pictures and secrets.

### Fixed
- Opening a card from the Library kept showing the previous card's picture.
- Dialogs opened from inside a panel (trim compare, update preview) could be clipped by the panel; they now open
  above the whole page.

## [2.4.0] - 2026-10-18

### Added
- SillyTavern World Info: every entry setting is stored and exported (JSON lorebook and the card's embedded
  character_book): position (↑/↓ Char, ↑/↓ AN, `@Depth` with role, ↑/↓ EM), sticky, cooldown, delay, probability,
  secondary keys with AND ANY / AND ALL / NOT ANY / NOT ALL, inclusion groups (weight, prioritize), character filter,
  vectorized, constant. LORE editor: "Advanced SillyTavern settings" (empty = the default for the entry type).
- Character entries are sticky for 2 messages by default (r/SillyTavernAI tip).
- TEXT → LORE adds an always-on **Cast Roster** (main and supporting characters) and a **Relationships** tracker
  ("A & B: cousins; rivals") built from the reviewed relationships.
- TEXT: the Story So Far can be placed before the card or at depth 4 as a system note.
- TEXT: re-sending UPDATES the LORE project made last time: hand-edited entries are kept, the rest refreshed, new ones
  added, ones no longer kept go to the LORE trash. Shift-click makes a separate new project.
- TEXT: ⚇ CARDS FOR MAIN CAST writes a card for every kept main character (set at the starting point, lorebook-aware),
  plus an optional group card.
- TEXT: + ADD TEXT appends new chapters or a SillyTavern chat (.jsonl) to a project; only the new chunks are extracted.
- TEXT: SillyTavern chat exports (.jsonl) can be loaded as a source (a roleplay becomes lore like a fic).
- TEXT: wiki pages (Fandom, Wikipedia, any /wiki/ link) are read through the wiki's API: infobox, sections and lists,
  no navboxes or references.
- AI recap: long stories are condensed in tiers (older parts become arc summaries first, recent parts stay detailed).
- Critic: ▤ CHAPTER SWEEP scores every part on its own (weakest first), a score history across critiques, and
  ✎ REWRITE THE PASSAGE on any quoted problem or line fix (finds the paragraph in your text and rewrites it).
- LORE: ▶ Test Activation — paste chat text and see which entries SillyTavern would insert, why (key, recursion,
  constant), and which the token budget or an inclusion group would cut.
- LORE: ⌘ Links — which entries pull in which by recursion, unlinked entries, entries that never fire, mutual pairs.
- LORE: trash with restore / delete for good / empty (deletes and "Clear entries" are restorable), an EDITED badge,
  an always-on token budget meter, keyboard review (J/K move, X delete, U undo delete, Ctrl+S save).
- CHARACTER: V3 JSON export (PNG exports already carry both V2 `chara` and V3 `ccv3`). Generation options: story point,
  who {{user}} is, size (small/lean/standard/rich), style (prose/PList), in-depth mode (bible → card → check);
  Character's Note and System Prompt fields; static card AUDIT; per-field undo/redo.
- Config: model presets per task (extraction, critic, cards, lore), database backups (one per start at most hourly,
  newest 12 kept, BACK UP NOW, RESTORE with a safety backup first), model usage (calls and tokens per model),
  project bundles (.zip of TEXT/LORE projects and cards with ready-to-use SillyTavern JSON; import adds as new).
- Ctrl+K search across cards, lore entries, TEXT projects and reviewed entities; Enter opens the hit in its studio.
- Closing the tab while a job runs or an edit isn't saved asks first.
- Interface strings for the new controls in EN / 日本語 / 中文; aria-labels on icon buttons; visible keyboard focus rings;
  LORE and TEXT layouts stack on narrow windows.
- tests/e2e: the browser tests (mock backend, no API key) with `run_all.py`.

### Changed
- Jobs survive in SQLite: a backend restart marks running jobs as interrupted instead of losing them.
- 429 rate limits wait for the provider's Retry-After.
- Saved API keys are shown masked in Config; saving the masked value keeps the key.
- The narrator card stores its rules in the card's System Prompt instead of folding them into the description.
- Insertion Order hint corrected: higher = closer to the chat, more influence, kept first under the budget.
- Code split: lore_routes.py, lore_tools.py, critic_tools.py, admin_routes.py, bundle_routes.py, search_routes.py;
  CriticPanel.jsx, LoreTools.jsx, AdminPanels.jsx, SearchModal.jsx.
- Old helper scripts (start_windows.bat, setup_windows.bat, start_mac_linux.sh) now forward to start/setup.
- Clearer button names. TEXT: RE-MERGE → **Rebuild list** (no extraction calls, keeps your review);
  RE-CHUNK → **Resplit text**, moved under Chunk size with a red outline and a confirmation that says how much
  extraction it deletes; PARALLEL CHUNKS → **Chunks at once**. LORE: Generate Entry → **Generate from URL**,
  Multiple Pages → **Several URLs**, Export Lorebook → **SillyTavern (.json)**, Clear entries → **Trash all entries**,
  Insertion Order → **Order (priority)**, Entry Depth → **Depth (`@Depth` only)**. Translated in 日本語 / 中文.

### Fixed
- The cast card overwrote the first member's card; it is saved as a new card.
- Renaming a card from its title field silently failed (missing import).
- The AI recap kept the earliest part summaries when the input was too long; it now keeps the latest.
- Lore project entry counts included deleted entries.

### Removed
- Legacy server-rendered pages (/library, /config, /env, /card/…): the React app replaces them.

## [2.3.x] - earlier changes (previously "Unreleased")

### Added
- TEXT review: trash with restore, UNDO DELETE, and EMPTY TRASH (deletes are restorable now).
- TEXT review: keyboard shortcuts (J/K or arrows move, X keep/skip, Del to trash, U undo, Ctrl+S save).
- TEXT review: re-extract / re-merge keep your work (hand edits, trash, keep/skip choices, manual merges).
- TEXT: redo a single chunk (↻ in the chunk list) with the selected model.
- TEXT: live chunk progress while extracting, and a time estimate in the job message.
- TEXT: importance tiers (MAIN / SUP / 1×) with one-offs collapsed; one-off items/abilities start skipped.
- TEXT: fic-specific flag (FIC = original to the story, ALT = changed from canon), filter, and an origin field in the editor;
  sent to LORE as "Original to this story:" / "In this story (differs from canon):".
- TEXT: relationships per character (extracted, editable), appended to the character's lore entry.
- TEXT: Story So Far editor with a starting point ("roleplay starts after chunk N"); recap and timeline stop there.
- TEXT: → MAKE CARD sends a reviewed character to the CHARACTER studio as a source, ready for Generate Card.
- TEXT: ⚑ WORLD NARRATOR CARD builds a narrator/game-master V2 card with the story's lore embedded (also saved to the library).
- CHARACTER: attach a LORE project to exported cards (JSON and PNG) as the card's own lorebook (character_book).
- LORE: DeepLore export (.zip of markdown notes with keys, priority and a "When to select" summary).
- TEXT: CRITIC panel under Text Sources: a brutally honest critique (verdict, scores, ranked problems with quotes,
  step-by-step plan, line rewrites), whole text or one chapter, optional focus, own model; history, full view, .md download.
- TEXT: ✦ WRITE RECAP WITH AI: one always-on Story So Far entry in [HEADER] / [BODY - CHAPTER LOG] / [FOOTER - CURRENT STATUS] layout.
- TEXT: events moved to a collapsed TIMELINE section in story order (they are timeline lines, not lore entries).
- LORE: entries autosave (and switching entries never loses edits), list badges (NO KEYS, EMPTY, DUP, ALWAYS ON),
  token estimates, Clean Keywords (preview, then apply), dismissible errors, failed jobs shown.
- CHARACTER: cards autosave with a saved/editing indicator.
- backend/tests: pytest suite (cleaning, chunking, filters, the full TEXT → LORE flow, cards and exports).
- TEXT studio: ingest fic text/files/URLs, chunk, deep-extract entities and events, review, send to LORE.
- Parallel extraction (1-6 workers, default 3), double-start guard, call estimate.
- Step-by-step `[TEXT]` / `[DEEP]` terminal logging with timings.
- Per-project lorebook export with layered default order and `order_manual` tracking.
- Max-token sliders.
- TEXT review: autosaving editor that keeps your place, PREV/NEXT, bulk keep/skip/delete, and DUP / EMPTY / JUNK? / NO KEYS flags with select-and-delete and merge-duplicates.
- TEXT studio defaults NanoGPT to deepseek/deepseek-v4.1-flash.

### Changed
- Default NanoGPT model is now deepseek/deepseek-v4.1-flash everywhere (was a slow thinking model).
- Sending to LORE: events no longer become one entry each. They roll up into an always-on "Story So Far" recap (constant) and one "Story Timeline" entry.
- Trigger keywords are cleaned on send: generic words and other entries' names are removed, so "Yuna" no longer fires 240 entries.
- Extraction prompt and filter skip body parts, acts, feelings and generic scenery; events must be plot-significant.
- A failed events step keeps the inventory event titles instead of saving 0 events.
- Chub-compatible V2 card export.
- Generator settings read at call time (no restart needed after saving Config).
- Repeated sends to LORE get distinct project names.
- Missing ids return 404 instead of a 500.

### Fixed
- LORE: changing an entry's type in the editor was never saved.
- LORE: "Clear entries" recreated the project with a new id, breaking TEXT links and card lorebook attachments; it now empties it in place.
- CHARACTER: Generate Card on a source that already has a card replaced that card; it now saves a new card and keeps the old one.
- A 404 from an outdated backend now says to restart the backend instead of showing raw HTML.
- Chunks whose events step failed are retried by a normal Extract (no force needed).
- Editing or merging an entry in review now refreshes its one-line summary.
- Duplicate trigger keywords that differ only in case are removed on send.
- Chunking: strict chapter detection, fic-page boilerplate removal, duplicate section/chunk/page dedupe.
- U+FFFD and mojibake repair on ingest.

### Security
- Host/Origin guard, whitelisted `.env` editor, SSRF-hardened image proxy.

---

## [2.3.1] — 2026-06-17

### Changed
- Background grid pattern now fills the full window width instead of stopping
  at the padded content edge
- Action button row in Character Studio: buttons now space evenly across
  the full bar width; View Source moved to the end of the row (after Export)
- Nav bar (Character/Lore/Config tabs): inverted button colors for stronger
  visual contrast — inactive tabs are now filled, active tab is light
- Character name field in Character Studio inverted to a solid dark
  background with light text, matching other highlighted UI elements
- Section headings (Preview, Character System, etc.) now bold and
  slightly larger for clearer visual hierarchy

---

## [2.3.0] — 2026-06-13

### Added

#### Character Studio
- **Progress badge** — live field completion bar between Regenerate Full Card and the field list
  - Shows filled/total count per tab (Natural: 5 fields, Structured: 25 fields)
  - Color coded: red → orange → green as fields fill in
  - Lists blank field names below the bar
  - Blank dot indicator on each empty field button
- **Tags generation** — generator now produces at least 10 tags per card covering franchise,
  character type, personality, setting, abilities, genre, and physical traits

#### Lorebook
- **Layered architecture** — entries now follow a four-layer system:
  - Layer 1: World rules / concepts
  - Layer 2: Faction anchors (names all key members)
  - Layer 3: Character entries
  - Layer 4: Places, items, events, abilities
- **10-20+ entries per page** — generator now extracts every named entity from the source
- **Uncategorized section mining** — episode summaries, season recaps, and raw narrative
  sections now scanned for named characters, locations, factions, and events
- **Schema 3 export** — lorebook JSON now exports in SillyTavern standalone lorebook format
  with `key`, `order`, `preventRecursion`, `recursive_scanning` etc.
- **Layer defaults at export time** — `preventRecursion`, `position`, `order` assigned
  automatically by entry type; no DB changes required

#### Generator
- **Three-level field inference** — character card fields now filled via priority chain:
  - Level 1: Explicit infobox fields and named sections (Personality, Quotes, Likes/Dislikes)
  - Level 2: Structured source sections (history, biography, raw_sections)
  - Level 3: story_sections and uncategorized_sections — raw narrative fallback
- **Quotes section** — if present, used directly for `mes_example` and `speech` patterns
- **Infobox Likes/Dislikes** — used directly when present rather than inferred

#### Scraper
- **Birth year → age calculation** — `Date of birth: c. 1974` → `~52 (b. c. 1974)`
- **Birth date aliases** — `date of birth`, `born`, `dob`, `birthdate` all map to age
- **Wiki hedging cleaned** — `"Unknown or Chinese"` → `"Chinese"`
- **`species` renamed to `ethnicity`** — covers nationality, cultural background, biological type
- **`nationality` merged into `ethnicity`** — no longer a separate field
- **`race`** retained for biological subtype
- **Fandom tab panel extraction** — Personality and Appearance tabs now extracted separately
  before the main section walk
- **Date-pattern history routing** — sections named `Raccoon City (1998)` now route to history
- **JSON-LD image fallback** — catches pages where portable infobox image is missing
- **Faction/affiliation aliases expanded** — `faction`, `clan`, `guild`, `side`, `crew` etc.
- **Language aliases added to ethnicity** — `language`, `native language`, `homeland` etc.

### Fixed
- Skip reason truncated in job status bar — full reason still logged to console
- `title` UnboundLocalError in single-page lore job
- DB migration order — runs after table creation on fresh databases

---

## [2.2.0] — 2026-06-13

### Added

#### Launch & Infrastructure
- **Combined launcher** — single `start.bat` / `start.sh` replaces the old two-terminal workflow
  - Flask starts in the foreground (logs visible)
  - Vite starts in the background and auto-opens `http://localhost:5173`
  - Dependency hash check skips `pip install` when `requirements.txt` hasn't changed
- **Setup scripts** — `setup.bat` / `setup.sh` for first-time users
  - Checks Python 3.10+ and Node.js 18+ are installed, gives exact download URLs if not
  - Creates `.venv`, installs all dependencies, copies `_env.example` to `.env`
  - `chmod +x start.sh` handled automatically on Mac/Linux
- **Restructured project layout**
  - `backend/` — all Python source files and config
  - `data/` — runtime DB and logs (gitignored, created on first run)
  - `docs/` — changelog
  - `start.bat` / `start.sh` at project root

#### Character Studio
- **New Card** button — create a blank card manually without scraping a wiki page; all fields editable immediately in both Natural and Structured view
- **Batch Generate** — paste up to 10 wiki URLs and generate all cards in one job; results saved to library automatically
- **Auto image from scrape** — infobox/portrait image detected from wiki page (checks `data-src` for Fandom lazy-loading) and pre-filled into the card image slot via local proxy (no CORS issues)
- **Library search** — text filter in the library drawer, filters by card name and source URL in real time
- **Cast card endpoint** — `/api/generate/cast` for combining 2–6 existing cards into a single multi-character persona card (backend ready, optional UI feature)
- **Save button** moved into the Character System panel next to Regenerate Field

#### Lore Studio
- **ST lorebook fields per entry** — each lore entry now has:
  - **Scan Depth** (slider, 1–20) — how many recent messages SillyTavern scans for trigger keywords
  - **Insertion Order** (slider, 0–1000) — priority order for insertion; lower = first
  - **Entry Depth** (slider, 0–20) — where in context the entry is inserted
  - All three values exported correctly in the SillyTavern V2 lorebook JSON
- **Move entry to project** — `↪` button on each entry opens a dropdown to reassign it to any project
- **Multiple Pages mode** — converted from a toggle to a batch-style dropdown panel (mirrors Batch Generate in Character Studio); supports up to 20 URLs
- **Save flash** — entry editor panel flashes green on save
- **Delete flash** — entry turns red and fades out before being removed from the list

#### Animations
- **Glitch label** — constant subtle glitch loop on the active field label (DESCRIPTION, PERSONALITY, etc.) in Character Studio
- **Typing effect** — regenerated field text types in character-by-character at a speed proportional to length
- **Progress bar simulation** — indeterminate sweeping animation while any job runs
- **Save flash** — green outline pulse on editor panel on save in both studios
- **Live elapsed timer** — ticks during every job and field regeneration; freezes on completion showing total time (e.g. "18s")

#### Internationalisation
- All new UI strings added to EN / JA / ZH translation tables:
  - New Card, Batch Generate, Cancel Batch, Batch title and hint
  - Export Lorebook, New Entry, Generate from Prompt, Add URL, Lore batch hint
  - Export Card JSON / Export Structured JSON (context-aware label)
  - Natural, Structured (image export toggle), Export Failed, Selected
  - Scan Depth, Insertion Order, Entry Depth, SillyTavern settings hint
  - Move to Project, No Project, Entry Saved, Entry Deleted

#### Developer
- **Inline documentation** added to every source file — docstrings for all Python modules, JSDoc for all frontend components, explaining schema, props, handlers, and extension points

---

### Fixed

#### Bugs
- **`alternate_greetings` data loss** — were silently dropped on every save/load cycle; now correctly read and written to DB
- **JOBS memory leak** — completed/failed jobs now pruned after 1 hour
- **`__import__` hacks** — all `__import__('database')` inline calls replaced with proper top-level imports
- **`project_id` NameError in multi-URL lore** — variable used in background thread before being extracted from request data
- **`entry.keywords` crash** — keywords returned as JSON string from DB instead of array; normalised on load in LoreStudio and in generator via `_ensure_list()`
- **`setCornersReady` undefined** — leftover reference from removed corner animation
- **Debug print in generator** — stray `print("[GENERATOR] result keys: ...")` removed
- **Windows Unicode crash** — `✓`, `✗`, `·`, `→`, `—` characters in log functions and comments replaced with plain ASCII throughout `app.py` and `generator.py`
- **Library drawer text invisible in dark mode** — drawer container missing `color: var(--signal-text)` and had hardcoded `#3a3a3a` borders
- **Highlighted items unreadable in dark mode** — all components using `--signal-text-inv` on active backgrounds switched to `--signal-btn-active-text`
- **DB migrations consolidated** — migration loop replaces repeated try/except blocks

#### Generator (major rewrite)
- **System/user message split** — definitions (`CHARACTER_CARD_DEFINITION`, `LOREBOOK_DEFINITION`) now sent as the system message; source content sent as the user message. Better model behaviour.
- **Three inconsistent lore prompts unified** — multi-URL, single-page, and generate-from-prompt paths all now call `generate_lore_entry()` in `generator.py` instead of building separate inline prompts
- **`valid/reason` pattern for lore** — model explicitly validates each page before generating entries; skipped pages log a reason instead of producing garbage entries
- **Detailed field definitions** — both `CHARACTER_CARD_DEFINITION` and `LOREBOOK_DEFINITION` rewritten with purpose, examples, and keyword guidance
- **`_ensure_list()` helper** — normalises any field that should be a list regardless of how the model returns it
- **Structured profile source trimmed** — `generate_full_card` now sends a compact subset of normalized fields instead of the full blob
- **Field regeneration trimmed** — each field regen only sends relevant card context (e.g. personality regen excludes mes_example); significantly faster per-field generation
- **`use_config` parameter** — was dead code; now correctly reads `settings.json` and applies custom templates
- **Inline generator imports cleaned up** — all `from generator import ...` scattered through `app.py` consolidated into top-level import

#### Job Status
- **Stage map expanded** — `formatStage()` now covers all 12 stages used across all job types; unknown stages fall back to humanised string instead of raw underscored name
- **Thinking animation** — now fires on `building_prompt` and `generating` stages too, not just `requesting_model`
- **Skipped pages** — show `—` indicator and skip reason in modal instead of `OK`
- **Descriptive messages** — all job stage messages updated to include provider/model name and specific action (e.g. "Sending to nanogpt/glm-4.7:thinking...")

#### Performance
- **WAL mode** — SQLite runs in WAL journal mode with `NORMAL` sync
- **`pip install` skip** — start scripts hash `requirements.txt` and skip reinstall if unchanged

#### Dark Mode
- **`--signal-text-inv`** corrected — was beige on beige in dark mode; now dark on beige active backgrounds
- Lore entry list, project list, model picker, and library drawer all readable in dark mode

#### Scraper
- **Fandom lazy-load images** — `data-src` checked before `src` for infobox image detection
- Image URLs cleaned of Fandom resize transforms

#### CSS / UI
- **Corner brackets** — rewritten using inline SVG data URIs with correct L-shape per corner
- **Image preview frame** — clip-path polygon clipped corners (Frame 5 style)
- **Default wiki URL cleared** — URL input starts empty instead of pre-filled with a test URL
- **OpenRouter model picker** — filters to text-only models, sorted alphabetically, shows context window size and price per million tokens per model

#### Config
- **Temperature slider** — adjustable 0.0–1.0 in the Config tab; controls creativity vs precision of AI output
- **Max Tokens dropdown** — presets: 1024 / 2048 / 4096 (default) / 8192; controls maximum response length
- Both values saved to `settings.json` and applied per-generation without restart

#### Scraper improvements
- **URL fragment stripping** — `#section-anchor` removed before fetching (fixes `Chun-Li#SF6` style URLs)
- **Expanded section aliases** — 40+ new section names added to abilities bucket including:
  `powers and abilities`, `powers & abilities`, `supernatural abilities`, `demonic abilities`,
  `devil trigger`, `special moves`, `super arts`, `critical arts`, `moveset`, `attacks` and more
- **`uncategorized_sections` exposed** — available at top level of source dict for generator use
- **Extra ability sections** — generator now scans uncategorized sections for ability-related content
  and includes them in both character card and lore prompts

#### Generator improvements
- **Inference instructions strengthened** — `speech`, `likes`, `dislikes`, `loves`, `hates` now
  explicitly instructed to infer from story actions, quotes, and emotional reactions rather than
  requiring explicit source statements
- **`mes_example` format enforced** — prompt now specifies two newlines (`\n\n`) between blocks;
  prevents `<START>` running onto the same line as previous dialogue
- **Fictional examples in definitions** — `CHARACTER_CARD_DEFINITION` and `LOREBOOK_DEFINITION`
  now use invented characters and places; no real IP referenced

#### Bug fixes (late session)
- **DB migration order** — migrations now run after `CREATE TABLE IF NOT EXISTS`; fixes
  `table cards has no column named alternate_greetings_json` on fresh databases
- **`title` UnboundLocalError** — variable used before assignment in single-page lore job; fixed
- **`project_id` in multi-URL lore** — was not extracted from request before background thread used it

### Changed
- **Signal UI theme** — all legacy CSS classes, variables, and keyframes renamed to `signal-*`; CSS file renamed to `signal-ui.css`
- **Project structure** — Python source moved to `backend/`, runtime data to `data/`, changelog to `docs/`
- **Lorebook export** — includes `scan_depth` and `depth` fields per entry
- **`start.bat`/`start.sh`** — Flask foreground, Vite background; browser opens automatically to `localhost:5173`

#### Structured profile field changes
- **`species` renamed to `ethnicity`** — more accurate for roleplay; covers nationality, cultural background, and biological type in one field
- **`nationality` merged into `ethnicity`** — no longer a separate internal field; `Race/Nationality` infobox fields now map directly to `ethnicity`
- **`race`** — retained as a separate field for biological subtype when the source supports it (e.g. High Elf, Nephilim)

#### Infobox normalisation improvements
- **Birth year → age calculation** — `Date of birth: c. 1974` now becomes `~52 (b. c. 1974)` automatically
- **Birth date aliases** — `date of birth`, `born`, `dob`, `birthdate` all map to the `age` field
- **Wiki hedging cleaned** — `"Unknown or Chinese"` → `"Chinese"`, `"Unknown (possibly British)"` → `"possibly British"`
- **Nationality/ethnicity aliases** — `Race/Nationality`, `ethnicity`, `citizenship`, `country of origin` all map to `ethnicity`
- **Date-pattern history sections** — sections named with year patterns (`Raccoon City (1998)`, `2012-2013`) now route to `history` instead of `uncategorized_sections`

#### Scraper fixes
- **`.wds-tab__content` handling** — Fandom tab panels (Personality, Appearance, etc.) now extracted separately before the main section walk, preventing tab content from being stripped or corrupting section order
- **JSON-LD image extraction** — `<script type="application/ld+json">` is now checked as a fallback image source; catches Fandom pages where the portable infobox image is missing (e.g. Resident Evil wiki)
- **Story sections fallback** — when `personality` and `appearance` are sparse, uncategorized narrative sections are included as `story_sections` for the generator to infer from

## [2.1.0] — 2026-06-12

First public release. Established the full three-tab layout and core feature set.

### Added

#### Character Studio
- Scrape any Fandom wiki URL and generate a SillyTavern V2 character card in one step
- Natural view — description, personality, scenario, first message, message examples, tags
- Structured view — 22 profile fields across identity, physical, character, and card sections
- Field regeneration with custom prompt support
- Alternate greetings with per-entry AI regeneration
- PNG export with embedded SillyTavern V2 metadata (`chara` tEXt chunk)
- Cheatsheet bar — click to insert SillyTavern variables into any field
- Library with save, load, search, rename, duplicate, and delete

#### Lore Studio
- Single-page lorebook generation from a Fandom wiki URL
- Named projects to organise separate lorebooks
- Manual entry creation and AI generation from custom text prompt
- SillyTavern V2 lorebook JSON export

#### Config
- API key management for NanoGPT, OpenRouter, and local servers
- Custom system prompt templates per generation type (character, field regen, lore)
- OpenRouter model picker with live fetch, context window size, and price per token
- NanoGPT model picker

#### Backend
- Flask backend with SQLite database
- BeautifulSoup scraper for Fandom/MediaWiki pages
- Support for NanoGPT, OpenRouter, and any local OpenAI-compatible server

#### UI
- NieR:Automata–inspired design system (light and dark mode)
- EN / 日本語 / 中文 interface

---

## [2.0.0] — 2026-06-10

Major rewrite from single-script experiment to full Flask + React application.

### Added
- Flask backend replacing the original standalone Python script
- React + Vite frontend replacing terminal output
- SQLite database for persistent card and source storage
- Basic character card generation from Fandom wiki URLs
- Basic lorebook generation
- NanoGPT provider support

### Changed
- Output moved from terminal JSON to interactive browser UI
- Card data now stored in DB and editable after generation

---

## [1.0.0] — 2026-03-22

Initial local experiment. Single Python script, no UI.

### Added
- Fandom wiki scraper using BeautifulSoup
- Character card JSON generation via NanoGPT API
- Output printed to terminal as raw JSON
- Manual copy-paste into SillyTavern

---
