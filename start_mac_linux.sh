#!/usr/bin/env bash
# Old launcher kept for people who still run it. It used to run "python app.py" from the wrong folder.
# start.sh is the real launcher (venv, dependencies, backend + frontend).
cd "$(dirname "$0")"
echo "This launcher is outdated - starting start.sh instead..."
exec ./start.sh "$@"
