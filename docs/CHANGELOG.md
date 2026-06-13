# Changelog

All notable changes to Character Card Studio are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

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

---

## [2.1.0] — prior release

Initial public release with Character Studio, Lore Studio, and Config.

---
