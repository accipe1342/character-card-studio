# Character Card Studio

Character Card Studio is a local web app for scraping a Fandom wiki page, generating a SillyTavern-style character card with AI, editing it in your browser, and exporting the final `.card.json` file.

This package is designed for people who are new to Python, SQLite, and local web apps.

## Current Status

The app is now configured to work with local OpenAI-compatible servers (including LM Studio style endpoints) and has guardrails added to prevent common crash paths.

## What This App Does

- Scrapes a Fandom page
- Saves scraped data in a local SQLite database
- Generates character cards with local or cloud LLM providers
- Lets you edit natural fields and structured profile fields
- Lets you regenerate specific fields with custom prompts
- Exports a SillyTavern-compatible `.card.json`
- Includes a built-in SQLite table viewer and `.env` editor

## Included Files

- `app.py`: Flask web app and routes
- `database.py`: SQLite helpers and persistence logic
- `scraper.py`: Fandom scraping and URL parsing
- `generator.py`: LLM request and generation logic
- `preview.py`: export/preview formatting helpers
- `templates/`: HTML templates
- `.env.example`: sample environment file
- `requirements.txt`: Python dependencies
- `setup_windows.bat`: first-time setup on Windows
- `start_windows.bat`: run app on Windows
- `start_mac_linux.sh`: run app on macOS/Linux

## Recent Changes (What and Why)

- Added local provider support (`local`) with optional `LOCAL_API_KEY`.
- Why: you are running a local model at `http://127.0.0.1:1234` without a cloud API key.

- Added provider/model editing in the card editor.
- Why: cards saved with wrong provider values (for example a model name in provider field) were causing generation failures.

- Added fallback for unknown provider values to local provider.
- Why: avoid hard crashes from bad historical card values.

- Fixed `UnboundLocalError` when templates were enabled but template text was blank.
- Why: prompt could be left undefined in template mode.

- Fixed preview crash when `backstory` arrived as a list instead of a string.
- Why: model output shape can vary across runs.

- Added card deletion from Library.
- Why: easier cleanup and recovery after bad scrapes/tests.

- Switched scrape input from two fields to one full Fandom URL.
- Why: simpler UX and fewer formatting mistakes.

- Prevented blank card entries on scrape failures.
- Why: scraping errors now return to main page with a visible error and do not write empty rows.

- Softened strict generation-key failure behavior.
- Why: if the model omits fields like `mes_example` or `tags`, defaults are filled instead of crashing.

## Before You Start

You need:

1. A computer with internet access
2. Python 3.11+
3. A model provider (local or cloud)
4. Cloud API keys only if you use cloud providers

## Setup on Windows

1. Open the project folder.
2. Run `setup_windows.bat` once.
3. Run `start_windows.bat` to launch the app.

## Configure Provider (`.env`)

### Local OpenAI-Compatible Server (Recommended)

```env
DEFAULT_PROVIDER=local
LOCAL_OPENAI_BASE_URL=http://127.0.0.1:1234
LOCAL_MODEL=Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K
LOCAL_API_KEY=
```

Notes:

- `LOCAL_API_KEY` can stay blank for local servers that do not require auth.
- The app automatically targets `/v1/chat/completions`.

### NanoGPT

```env
NANOGPT_API_KEY=your_real_key_here
NANOGPT_MODEL=zai-org/glm-4.7:thinking
```

### OpenRouter

```env
OPENROUTER_API_KEY=your_real_key_here
OPENROUTER_MODEL=z-ai/glm-4.7
```

You can also edit env values from `http://127.0.0.1:5000/env`.

## Basic Workflow

1. Open `http://127.0.0.1:5000`.
2. Paste one full Fandom page URL (example: `https://gundam.fandom.com/wiki/Rain_Mikamura`).
3. Click **Scrape**.
4. Open the card from **Library**.
5. In editor top bar, verify `Provider` and `Model` are correct.
6. Click **Generate Full Card**.
7. Edit or regenerate fields as needed.
8. Export `.card.json` when finished.

## Common Pages

- `/`: dashboard
- `/library`: saved cards
- `/card/<id>`: card editor
- `/db`: SQLite viewer
- `/env`: environment editor

## Troubleshooting

### App Starts but Generation Fails

Check:

- Provider/model values on the card editor page
- `.env` values for selected provider
- Local server is running and reachable at `LOCAL_OPENAI_BASE_URL`

### Scrape Fails

- Use a full Fandom page URL containing `/wiki/`.
- On failure, the app returns to main page with an error message and does not create blank card rows.

### Python Not Recognized

Reinstall Python and ensure Add Python to PATH is enabled.

### Missing Module Error

Run setup again:

- `setup_windows.bat`

## Safety Note

Keep real API keys in `.env`, not in source files.

## Clean Reset

Delete `fandom_chars.db` to rebuild tables on next app start.

## License / Personal Use

Use, edit, and adapt this project for your own local workflow.
