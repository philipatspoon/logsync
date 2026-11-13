#!/bin/bash
# Kör menyradsappen. Startas av startfilen, eller direkt i Terminal vid felsökning.
# Allt Logsync laddar ner (uv, Python, paket, Whisper-modellen) hamnar i EN mapp:
#   ~/Library/Application Support/Logsync
# så att Avinstallera i LS-menyn tar bort alltihop.
# Alltid som Apple silicon: startas vi via Rosetta (Intel-läge) skulle Intel-versioner installeras,
# och Whisper-paketet (MLX) finns bara för Apple silicon.
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && [ "$(uname -m)" != "arm64" ]; then
  exec /usr/bin/arch -arm64 /bin/bash "$0" "$@"
fi
RES="$(cd "$(dirname "$0")" && pwd)"
SUPPORT="$HOME/Library/Application Support/Logsync"
export HF_HOME="$SUPPORT/models"            # Whisper och andra modeller
export UV_CACHE_DIR="$SUPPORT/cache"         # Python-paket
export UV_PYTHON_INSTALL_DIR="$SUPPORT/python"
export HF_HUB_DISABLE_TELEMETRY=1
export PATH="$SUPPORT/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p "$SUPPORT"
echo "=== $(date) start ==="
# Modellen som tidigare laddades ner till den gemensamma cachen flyttas hit i stället för att laddas ner igen
OLD="$HOME/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo"
NEW="$HF_HOME/hub/models--mlx-community--whisper-large-v3-turbo"
if [ -d "$OLD" ] && [ ! -e "$NEW" ]; then
  mkdir -p "$HF_HOME/hub" && mv "$OLD" "$NEW" && echo "Flyttade Whisper-modellen till $HF_HOME"
fi
if [ ! -x "$SUPPORT/bin/uv" ]; then   # egen uv i Logsync-mappen, så att Avinstallera tar bort den
  osascript -e 'display notification "Installerar första gången – tar några minuter" with title "Logsync"'
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$SUPPORT/bin" UV_NO_MODIFY_PATH=1 sh || {
    osascript -e 'display dialog "Kunde inte installera. Kontrollera internetanslutningen." buttons {"OK"} with title "Logsync"'; exit 1; }
fi
exec uv run --python 3.12 --with rumps --with mlx-whisper --with numpy --with static-ffmpeg --with huggingface_hub \
  python "$RES/menubar.py"
