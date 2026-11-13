#!/bin/bash
# Kör menyradsappen. Startas av Contents/MacOS/Logsync, eller direkt i Terminal vid felsökning.
# Första gången installeras uv, Python och paketen automatiskt.
RES="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
echo "=== $(date) start ==="
if ! command -v uv >/dev/null; then
  osascript -e 'display notification "Installerar första gången – tar några minuter" with title "Logsync"'
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh || {
    osascript -e 'display dialog "Kunde inte installera. Kontrollera internetanslutningen." buttons {"OK"} with title "Logsync"'; exit 1; }
fi
exec uv run --python 3.12 --with rumps --with mlx-whisper --with numpy --with static-ffmpeg --with huggingface_hub \
  python "$RES/menubar.py"
