# Character Card Studio — v2.4 Update

A large update across all three studios. LORE now uses every SillyTavern World Info setting. TEXT gains a
full lorebook workflow and a stronger critic. The app adds backups, project bundles, search and a test suite.
Your existing data is migrated automatically and nothing is lost.

> **After updating:** restart the app (`start.bat` / `start.sh`). The backend has new routes, and an old backend
> still running will return "not found" errors.

---

## Highlights

- **Every SillyTavern World Info setting** is now stored per entry and exported.
- **Test Activation** previews which lore entries would fire for a piece of chat, and why.
- **Re-sending from TEXT updates the same LORE project** and keeps your hand edits.
- **Cast Roster and Relationships** entries are added automatically, and both are always on.
- **Cards for the whole main cast** in one click, plus an optional group card.
- **Critic upgrades:** chapter sweep, score history, and passage rewrites.
- **Safety:** automatic database backups, a trash in LORE, and a warning before closing the tab mid-job.
- **Ctrl+K search** across cards, lore, texts and characters.

---

## Lore Studio

### SillyTavern World Info, complete
Each entry now has **Advanced SillyTavern settings** in the editor. Leave a field blank to use the default for the
entry's type. Everything below goes into the exported lorebook JSON and into lorebooks you attach to cards.

| Setting | What it does |
|---|---|
| Activation | Default / Always on (constant) / Keywords only |
| Position | Before or after the character card, top or bottom of the Author's Note, before or after example messages, or **At depth** |
| Role | System / User / Assistant when inserted at depth |
| Sticky | Messages the entry stays active after it fires. **Characters default to 2** |
| Cooldown | Messages before it can fire again |
| Delay | Only fires once the chat has this many messages |
| Probability | Chance of insertion when triggered |
| Secondary keys | An extra filter with AND ANY / AND ALL / NOT ANY / NOT ALL logic |
| Inclusion group | Entries in a group compete, and only one is inserted (weighted, or highest order wins) |
| Character filter | Only active for the named characters |
| Vectorized | Can also fire by meaning (needs SillyTavern's Vector Storage) |

### New tools
- **▶ Test Activation:** paste chat text and see which entries would be inserted and why (keyword, recursion,
  or always on), with token counts. It also shows what the token budget or an inclusion group would cut.
- **⌘ Links:** which entries pull in which through recursion, entries that can never fire (no keys), unlinked
  entries, and pairs that mention each other.
- **Budget meter:** how much of SillyTavern's World Info budget (2048 tokens by default) your always-on entries
  use. It warns before keyword entries start getting cut.
- **♻ Trash:** deleting, or trashing all entries, is now restorable. You can restore, delete for good, or empty the trash.
- **Keyboard review:** J/K to move, X to delete, U to undo a delete, Ctrl+S to save.
- **New badges:** ALWAYS ON for any constant entry; EDITED for entries you changed by hand after they came from TEXT.

### Renamed controls

| Before | After |
|---|---|
| Generate Entry | Generate from URL |
| Multiple Pages | Several URLs |
| Export Lorebook | SillyTavern (.json) |
| Clear entries | Trash all entries |
| Insertion Order | Order (priority) |
| Entry Depth | `Depth (@Depth only)` |

---

## Text Studio

### Sources
- **SillyTavern chat logs (.jsonl)** can be loaded like any story, so a roleplay can become lore too.
- **Wiki links** (any `/wiki/` page) are read through the wiki's own API, giving clean text: infobox, sections and
  lists, without navigation boxes or references.
- **+ Add text** appends new chapters or a chat log to an existing project. Only the new parts need extracting.

### Story So Far
- **Placement option:** put the recap before the character card, or at depth 4 as a system note. Depth 4 weighs
  more heavily on what happens next.
- **Long stories:** the AI recap condenses older parts into arc summaries and keeps recent parts detailed. It no
  longer drops the newest chapters when the input is too long.

### Sending to LORE
- **The first send** creates a LORE project. **Later sends update that same project:**
  - entries you edited by hand in LORE are kept as they are;
  - the rest are refreshed;
  - new entries are added;
  - entries you no longer keep go to the LORE trash.
- **Shift-click** the send button for a separate new project.
- **New always-on entries:**
  - **Cast Roster:** one line per main or supporting character.
  - **Relationships:** "A & B: relationship" lines built from your review.

### Cards
- **Cards for main cast:** writes a full card for every kept main character, set at your chosen starting point and
  aware of the lorebook. **+ Group** also writes one card that plays the whole cast together. Re-running keeps
  earlier cards.
- **World Narrator card:** its rules now live in the card's real System Prompt field.

### Critic
- **Chapter sweep:** scores every part on its own (1–10, with its worst problem, a fix, and its best moment).
  Sort by story order or weakest first.
- **Rewrite the passage:** available on any quoted problem or line fix. It finds the paragraph in your text and
  rewrites it with the fix applied, keeping your voice, point of view and tense. Your text is never changed.
- **Score history:** a chart of the average score across critiques, so you can see whether revisions help.

### Renamed controls

| Before | After |
|---|---|
| RE-MERGE | **Rebuild list**: rebuilds the review from existing results, keeps your work, no extraction calls |
| RE-CHUNK | **Resplit text**: moved under Chunk size and marked red; warns how much extraction it deletes |
| Parallel chunks | Chunks at once |

---

## Character Studio

- **Generation options:** story point, who {{user}} is, card size (small / lean / standard / rich), writing style
  (prose or PList), and **in-depth mode**, which builds a character bible, then the card, then a check.
- **New fields:** Character's Note (injected at depth) and System Prompt.
- **Audit:** a static check that flags weak spots without a model call.
- **Per-field undo/redo.**
- **Export:** V3 JSON in addition to V2. PNG exports now embed both V2 (`chara`) and V3 (`ccv3`) data.
- **Minor safety:** the card generator leaves sexual profile fields empty for characters who read as under 18.

---

## App-wide

- **Ctrl+K search:** find any card, lore entry, text or reviewed character and jump straight to it.
- **Config → Model presets:** a default provider and model per task (extraction, critic, cards, lore).
- **Config → Backups:** automatic on start (at most hourly, newest 12 kept), plus Back up now and Restore. Restore
  backs up your current data first.
- **Config → Model usage:** calls and tokens per model over a chosen period.
- **Config → Project bundles:** export TEXT and LORE projects and cards as one `.zip`, including ready-to-use
  SillyTavern lorebook and card JSON files. Importing always adds and never overwrites.
- **Leave warning:** closing the tab during a job or with unsaved edits asks first.
- **Reliability:**
  - jobs survive a backend restart (they are marked interrupted, not lost);
  - rate limits wait for the provider's retry time;
  - saved API keys are masked in Config.
- **Accessibility and layout:**
  - labels on icon buttons;
  - visible keyboard focus;
  - LORE and TEXT stack properly on narrow windows;
  - new controls translated into 日本語 and 中文.

---

## Fixes

- Generating a card for a source that already had one replaced the existing card. It now saves a new card.
- The cast (group) card overwrote the first member's card. It is now saved separately.
- Renaming a card from its title field didn't save.
- Changing a lore entry's type in the editor wasn't saved.
- Clearing a LORE project changed its ID, which broke links from TEXT and attached lorebooks.
- Lore project entry counts included deleted entries.
- The Insertion Order hint was backwards. Higher means closer to the chat and higher priority.

## Removed

- The old server-rendered pages (library, config, env editor, card pages). The React app replaces them.

---

## Under the hood

- The backend is split into focused modules: lore routes, lore tools (simulator, links, trash), critic tools,
  admin (backups, presets, usage), bundles, and search.
- The frontend has new standalone components for the critic panel, the lore tools, the admin panels and the
  search modal.
- **Tests:**
  - a pytest suite for the backend, using a throwaway database;
  - browser tests in `tests/e2e/` that drive the real app with simulated model replies (no API key needed).
    Run them with `python tests/e2e/run_all.py`.
