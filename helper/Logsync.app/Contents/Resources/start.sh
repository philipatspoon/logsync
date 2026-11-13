#!/bin/bash
# Startar menyradsappen i bakgrunden och avslutar direkt. Används av appen som install.sh bygger.
# Alltid som Apple silicon: startas vi via Rosetta (Intel-läge) skulle Intel-versioner installeras,
# och Whisper-paketet (MLX) finns bara för Apple silicon.
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && [ "$(uname -m)" != "arm64" ]; then
  exec /usr/bin/arch -arm64 /bin/bash "$0" "$@"
fi
RES="$(cd "$(dirname "$0")" && pwd)"
LOG="$HOME/Library/Logs/Logsync.log"
mkdir -p "$HOME/Library/Logs"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
if curl -s -m 1 -H 'X-Logsync: 1' http://127.0.0.1:47811/status | grep -q '"ok"'; then exit 0; fi
if pgrep -f "$RES/run.sh" >/dev/null || pgrep -f "$RES/menubar.py" >/dev/null; then exit 0; fi
nohup /bin/bash "$RES/run.sh" >>"$LOG" 2>&1 </dev/null &
disown
exit 0
