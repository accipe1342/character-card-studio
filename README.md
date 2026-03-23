# Character Card Studio

Character Card Studio is a local web app for scraping a Fandom wiki page, generating a SillyTavern-style character card with AI, editing it in your browser, and exporting the final `.card.json` file.

This package is set up for people who are **new to Python, SQLite, and local web apps**.

## What this app does

- Scrapes a Fandom page
- Saves scraped data in a local SQLite database
- Generates a character card with NanoGPT or OpenRouter
- Lets you edit natural fields and structured profile fields
- Lets you regenerate individual fields with a custom prompt
- Exports a SillyTavern-compatible `.card.json`
- Includes a built-in SQLite table viewer and `.env` editor

## What is included

- `app.py` - the Flask web app
- `database.py` - database helpers
- `scraper.py` - Fandom scraping logic
- `generator.py` - AI card generation logic
- `preview.py` - export/preview formatting helpers
- `fandom_chars.db` - the SQLite database file
- `templates/` - all HTML pages
- `.env.example` - sample environment file
- `requirements.txt` - Python packages needed
- `setup_windows.bat` - first-time setup for Windows
- `start_windows.bat` - run the app on Windows
- `start_mac_linux.sh` - run the app on macOS/Linux

## Before you start

You need:

1. A computer with internet access
2. A NanoGPT API key or OpenRouter API key
3. Python installed

## Step 1 - Install Python

### Windows
1. Go to the official Python website.
2. Download **Python 3.11 or newer**.
3. Run the installer.
4. **Important:** check the box that says **Add Python to PATH**.
5. Finish the install.

### macOS / Linux
Install Python 3.11 or newer using your normal package manager or from the official Python website.

## Step 2 - Download this project

1. Download this project ZIP from GitHub.
2. Extract it to a folder such as:
   - `Desktop\character-card-studio`
   - or `Downloads\character-card-studio`

## Step 3 - Set up the app (Windows)

1. Open the project folder.
2. Double-click `setup_windows.bat`.
3. Wait for it to finish.
4. It will create:
   - a virtual environment in `.venv`
   - install the required packages
   - create `.env` from `.env.example` if needed

## Step 4 - Add your API key

You have two easy options.

### Option A - edit the `.env` file manually
Open `.env` in Notepad and fill in your key.

Example for NanoGPT:

```env
NANOGPT_API_KEY=your_real_key_here
NANOGPT_MODEL=zai-org/glm-4.7:thinking
```

Example for OpenRouter:

```env
OPENROUTER_API_KEY=your_real_key_here
OPENROUTER_MODEL=z-ai/glm-4.7
```

### Option B - use the built-in `.env` page
After the app starts, visit:

- `http://127.0.0.1:5000/env`

Then paste your key and save.

## Step 5 - Start the app

### Windows
Double-click `start_windows.bat`

### macOS / Linux
Open Terminal in the project folder and run:

```bash
./start_mac_linux.sh
```

## Step 6 - Open the app

Open your browser and go to:

```text
http://127.0.0.1:5000
```

## Basic workflow

1. Go to **Main**
2. Enter a Fandom wiki base and page name
3. Click **Scrape**
4. Open the card from **Library**
5. Click **Generate Full Card**
6. Edit fields as needed
7. Regenerate specific fields if needed
8. Export the finished `.card.json`

## Example scrape values

- Wiki Base: `https://gundam.fandom.com`
- Page Name: `Rain_Mikamura`

## Common pages in the app

- `/` - dashboard
- `/library` - all saved cards
- `/card/<id>` - editor for one card
- `/db` - SQLite database viewer
- `/env` - environment variable editor

## If something goes wrong

### "Python is not recognized"
Python was not installed correctly or was not added to PATH. Reinstall Python and check **Add Python to PATH**.

### The app opens but generation fails
Usually this means:
- your API key is missing
- your API key is wrong
- your selected provider does not match your key

Check your `.env` file.

### The page says a module is missing
Run the setup script again:

- `setup_windows.bat`

### The site does not load
Make sure the terminal or batch window is still open. The app only runs while that window is open.

## Safety note

Do not put real API keys directly inside Python files. Keep them in `.env` only.

## Want to start clean?

You can delete `fandom_chars.db` and the app will recreate the tables the next time it runs.

## License / personal use

Use, edit, and adapt this project however you want for your own local workflow.
