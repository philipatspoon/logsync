#!/bin/bash
# Installerar Logsync-appen på en Mac:
#   curl -fsSL https://philipatspoon.github.io/logsync/install.sh | bash
#
# Appen byggs här på datorn (med osacompile) i stället för att laddas ner färdig.
# En app som skapats lokalt räknas inte som nedladdad, så macOS spärrar den inte
# på datorer som bara tillåter appar från App Store och kända utvecklare.
set -euo pipefail
BASE="https://philipatspoon.github.io/logsync"
SUPPORT="$HOME/Library/Application Support/Logsync"
CODE="$SUPPORT/app"                         # Python-koden och startskripten
APP="$HOME/Applications/Logsync.app"         # appen du dubbelklickar på
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

[ "$(uname)" = "Darwin" ] || { echo "Logsync-appen fungerar bara på Mac."; exit 1; }

# Avinstallera:  curl -fsSL https://philipatspoon.github.io/logsync/install.sh | bash -s -- --avinstallera
if [ "${1:-}" = "--avinstallera" ]; then
  pkill -f "Logsync/app/menubar.py" 2>/dev/null || true; pkill -f "Logsync.app/Contents/Resources/menubar.py" 2>/dev/null || true
  du -sh "$SUPPORT" 2>/dev/null | awk '{print "• Tar bort "$1" i '"'"'"$2" "$3" "$4"'"'"'"}' || true
  rm -rf "$SUPPORT" "$APP" "$HOME/Library/Logs/Logsync.log"
  rm -rf /Applications/Logsync.app 2>/dev/null || true
  [ -e /Applications/Logsync.app ] && echo "  Dra /Applications/Logsync.app till papperskorgen i Finder."
  echo "Logsync är avinstallerat. Manus och loggar i webbläsaren påverkas inte."
  exit 0
fi
echo "• Hämtar Logsync …"
curl -fsSL -o "$TMP/logsync.zip" "$BASE/Logsync-app.zip"
ditto -x -k "$TMP/logsync.zip" "$TMP/u"

echo "• Lägger koden i $CODE"
pkill -f "Logsync/app/menubar.py" 2>/dev/null || true
# Rensa Intel-versioner som kan ha installerats av en tidigare start via Rosetta
for d in "$SUPPORT/bin" "$SUPPORT/python"; do
  if [ -d "$d" ] && file -b "$d"/*/bin/python3* "$d"/uv 2>/dev/null | grep -q "x86_64" && ! file -b "$d"/*/bin/python3* "$d"/uv 2>/dev/null | grep -q arm64; then rm -rf "$d"; fi
done
rm -rf "$CODE"; mkdir -p "$CODE"
cp "$TMP/u/Logsync.app/Contents/Resources/"* "$CODE/"
chmod 755 "$CODE/"*.sh

echo "• Bygger appen i $APP"
mkdir -p "$HOME/Applications"; rm -rf "$APP"
cat > "$TMP/Logsync.applescript" <<'AS'
on run
	startLogsync()
end run
on open location theURL
	startLogsync()
end open location
on startLogsync()
	set s to POSIX path of (path to home folder) & "Library/Application Support/Logsync/app/start.sh"
	do shell script "/bin/bash " & quoted form of s & " >/dev/null 2>&1 &"
end startLogsync
AS
osacompile -o "$APP" "$TMP/Logsync.applescript"
P="$APP/Contents/Info.plist"; PB=/usr/libexec/PlistBuddy
$PB -c "Set :CFBundleIdentifier app.logsync.launcher" "$P"
$PB -c "Set :CFBundleName Logsync" "$P" 2>/dev/null || $PB -c "Add :CFBundleName string Logsync" "$P"
$PB -c "Add :LSUIElement bool true" "$P" 2>/dev/null || $PB -c "Set :LSUIElement true" "$P"
$PB -c "Delete :CFBundleURLTypes" "$P" 2>/dev/null || true
$PB -c "Add :CFBundleURLTypes array" -c "Add :CFBundleURLTypes:0 dict" \
    -c "Add :CFBundleURLTypes:0:CFBundleURLName string app.logsync.launcher" \
    -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" \
    -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string logsync" "$P"
# Bara Apple silicon-delen av startprogrammet: annars kan macOS köra det via Rosetta och varna för Intel-appar
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
  lipo "$APP/Contents/MacOS/applet" -thin arm64 -output "$TMP/applet" 2>/dev/null && mv -f "$TMP/applet" "$APP/Contents/MacOS/applet" && chmod 755 "$APP/Contents/MacOS/applet"
  $PB -c "Delete :LSArchitecturePriority" "$P" 2>/dev/null || true
  $PB -c "Add :LSArchitecturePriority array" -c "Add :LSArchitecturePriority:0 string arm64" "$P"
fi
codesign --force --deep -s - "$APP" 2>/dev/null || true      # lokal signatur efter ändringen
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
[ -x "$LSREG" ] && "$LSREG" -f "$APP" || true                 # så att logsync:// hittar den här appen

if [ -e /Applications/Logsync.app ]; then
  echo "• Tar bort den gamla appen i Program …"
  rm -rf /Applications/Logsync.app 2>/dev/null || echo "  Gick inte från Terminal – dra /Applications/Logsync.app till papperskorgen i Finder."
fi

echo "• Startar Logsync"
open "$APP"
echo
echo "Klart. Om några sekunder syns LS i menyraden."
echo "Appen ligger i Program-mappen i din hemmapp (~/Applications) och kan startas därifrån eller från webbläsaren."
echo "Logg: tail -n 30 ~/Library/Logs/Logsync.log"
echo "Allt Logsync laddar ner (Whisper-modellen, Python och paket) hamnar i: $SUPPORT"
echo "Avinstallera: LS-menyn → Avinstallera Logsync, eller: curl -fsSL $BASE/install.sh | bash -s -- --avinstallera"
