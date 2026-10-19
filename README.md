# Character Card Studio

[![CI](https://github.com/accipe1342/character-card-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/accipe1342/character-card-studio/actions/workflows/ci.yml)
![version](https://img.shields.io/badge/version-2.4.0-informational)
![license](https://img.shields.io/badge/license-MIT-green)

A Signal UI–themed app for making SillyTavern character cards and lorebooks with AI: from Fandom wiki pages, from fan fiction and other long text, or from your own roleplay chats.

![Character Card Studio preview](preview.png)

---

## Quick Start

### Step 0 — Get the code

```bash
git clone https://github.com/accipe1342/character-card-studio.git
cd character-card-studio
```

Or download the ZIP from the green **Code** button on GitHub and unzip it.

### Step 1 — Install requirements (first time only)

**Windows:**
```bat
setup.bat
```

**Mac / Linux:**
```bash
chmod +x setup.sh
./setup.sh
```

The setup script will:
- Check that Python 3.10+ and Node.js 18+ are installed (and tell you where to get them if not)
- Create a Python virtual environment
- Install all Python and frontend dependencies
- Create your `.env` file from the example

> If Python or Node.js are missing, the script will give you the download link and stop — install them and run setup again.

### Step 2 — Add your API keys

Open `.env` in any text editor and add at least one API key:
```env
NANOGPT_API_KEY=your_key_here
```

### Step 3 — Launch

**Windows:**
```bat
start.bat
```

**Mac / Linux:**
```bash
./start.sh
```

Your browser will open automatically at `http://localhost:5173`.
After the first run, launching is instant.

---

## Features

### Character Studio
- Scrape any Fandom wiki page and generate a full SillyTavern V2 character card
- **New Card** — create a blank card manually without scraping, fill everything in yourself
- **Batch Generate** — paste up to 10 URLs and generate all cards in one job
- Natural & Structured views — edit description, personality, scenario, first message, and 22 structured profile fields
- Structured profile includes: age, sex, gender, ethnicity, race, pronouns, sexual attraction, appearance, clothing, accessories, backstory, speech patterns, personality traits, likes, dislikes, loves, hates, kinks, relationship status, height, weight
- Field regeneration with custom prompt support and live timer
- Alternate greetings with per-entry AI regeneration
- Generation options: story point, who {{user}} is, size, prose or PList style, in-depth mode; static AUDIT; per-field undo
- PNG export with embedded V2 (`chara`) and V3 (`ccv3`) metadata; V2 and V3 JSON; attach a LORE project as the card's lorebook
- Cheatsheet bar — click to insert SillyTavern variables into any field
- Library with save, load, search, rename, duplicate, and delete

### Lore Studio
- Single page or batch multi-URL lorebook generation (up to 20 URLs)
- Valid/reason validation — bad pages are skipped with a logged reason instead of generating garbage entries
- Named projects to organise separate lorebooks
- Every SillyTavern World Info setting per entry: scan depth, order, position/depth/role, sticky, cooldown, delay, probability, secondary keys and logic, inclusion groups, character filter, vectorized, constant
- Test Activation (which entries fire for a chat and why, with the token budget), Links (recursion map), budget meter
- Trash with restore, keyboard review (J/K/X/U, Ctrl+S), Clean Keywords, move entries between projects
- Manual entry creation and AI generation from custom text
- SillyTavern World Info JSON export and DeepLore (.zip) export

### Text Studio (fan fiction → lorebook)
- Load a fic by paste, file (.txt .md .html .epub), URL (AO3 full works, chapter-by-chapter "follow next", wiki pages) or a SillyTavern chat (.jsonl); + ADD TEXT appends new chapters later
- Deep extraction in parallel: characters, places, factions, items, abilities, concepts and plot events, with tiers (main / supporting / one-off), fic-only flags, relationships and age flags
- Review with autosave, keyboard shortcuts, duplicate/junk detection, merge, trash and undo
- Story So Far with a starting point ("roleplay starts after chapter N"), an AI archive recap and a timeline; place it before the card or at depth 4
- Send to LORE (re-sending updates the same project and keeps your LORE edits), with an always-on Cast Roster and Relationships entry
- Make a card for one character, for the whole main cast (plus a group card), or a World Narrator card
- Critic: brutally honest critique, chapter sweep, score history and passage rewrites

### Config
- Model presets per task, database backups and restore, model usage, project bundles (.zip export / import)
- Temperature slider (0.0–1.0) — controls creativity vs precision
- Max Tokens dropdown (1024 / 2048 / 4096 / 8192)
- Custom system prompt templates per generation type
- API key management in-app for all three providers
- Model picker with live fetch from NanoGPT or OpenRouter (shows context window and price per token)

### Scraper
- Supports 50+ section heading aliases across action games, JRPGs, fighting games, and general wikis
- URL fragment stripping (`Chun-Li#SF6` → `Chun-Li`)
- Fandom tab panel extraction (Personality, Appearance tabs on RE wiki etc.)
- JSON-LD image fallback for wikis without standard infobox images
- Date-pattern section routing (`Raccoon City (1998)` → history)
- Birth year → age calculation (`c. 1974` → `~52 (b. c. 1974)`)
- Wiki hedging cleanup (`"Unknown or Chinese"` → `"Chinese"`)

### UI
- Signal UI design system — light and dark mode
- EN / 日本語 / 中文 interface
- Ctrl+K search across everything
- Live elapsed timer on all jobs and field regeneration
- Animated progress bar, typing effect, glitch label, save flash

---

## Configuration

Copy `_env.example` to `.env` and add your API keys:

```env
# NanoGPT
NANOGPT_API_KEY=your_key_here
NANOGPT_MODEL=deepseek/deepseek-v4.1-flash

# OpenRouter
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini

# Local / OpenAI-compatible (LM Studio, Ollama, KoboldCPP, etc.)
LOCAL_OPENAI_BASE_URL=http://localhost:1234/v1
LOCAL_MODEL=local-model
LOCAL_API_KEY=local
```

Or manage everything in **Config → API Keys** inside the app.

Your data lives in `data/fandom_chars.db`; automatic backups go to `data/backups/` (Config → Backups).

---

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest backend/tests -q          # backend, with a throwaway database
python tests/e2e/run_all.py                # browser tests (see tests/e2e/README.md)
```

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3 · Flask · SQLite |
| Frontend | React 18 · Vite |
| AI | NanoGPT · OpenRouter · Local OpenAI-compatible |
| Scraping | BeautifulSoup4 · requests |

---

## Requirements

- Python 3.10+
- Node.js 18+

---

## Supported Providers

| Provider | Notes |
|---|---|
| [NanoGPT](https://nano-gpt.com) | Default — GLM, Qwen, and many others |
| [OpenRouter](https://openrouter.ai) | Claude, GPT-4o, Llama, Mistral, and more |
| Local | Any OpenAI-compatible server — LM Studio, Ollama, KoboldCPP |

---

## Uninstalling

Delete the project folder. Nothing is written to your system, registry, or AppData outside the folder itself. Python and Node.js can be uninstalled separately from your system's app manager if no longer needed.

---

## What's new

See [docs/UPDATE-v2.4.md](docs/UPDATE-v2.4.md) for the v2.4 overview and [docs/CHANGELOG.md](docs/CHANGELOG.md) for every change.

---

## License

MIT — see [LICENSE](LICENSE).
