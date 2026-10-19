# Browser tests (end to end)

Real Flask app + real React build, with every model call faked, driven by Playwright in Chromium.
Nothing touches your database (`mock_backend.py` uses a throwaway one) and no API key is needed.

## Run

```bash
pip install playwright requests && python -m playwright install chromium   # once
cd frontend && npm run build && cd ..
python tests/e2e/run_all.py
```

Ports 5000 and 5173 must be free (stop `start.bat` / `start.sh` first). Screenshots land in `tests/e2e/out/`.

| Script | Covers |
|---|---|
| e2e1.py | TEXT: paste, extract, review, keep/skip, trash, recap, send to LORE, make card, narrator card |
| e2e2.py | TEXT: timeline section, AI recap (archive layout) |
| e2e3.py | Critic: critique job, full view, .md download, history |
| e2e4.py | LORE autosave, badges, Clean Keywords, Trash all entries; CHARACTER autosave |
| e2e5.py | LORE: budget meter, advanced SillyTavern settings, activation test, links, trash, J/K/X/U keys; V3 JSON |
| e2e6.py | Recap placement, + ADD TEXT, cast cards, chapter sweep + rewrite, score history, Ctrl+K search, bundles, narrow layout, leave warning |

The scripts run in order: later ones use projects the earlier ones made.
Fake model replies live in `mock_backend.py` (`fake` for extraction, `_req` for every other prompt).
