#!/bin/sh
# Bygger K-114.app: spelet i eget fönster (fonster.py) med en enda ubåtsikon i Docken.
#
#   sh ikon/bygg-app.sh [mål]        # standard ~/Projekt/Lokalt/K-114.app
#
# Appens startskript gör `exec` till Python, så fönstret är samma process som appen
# (en ikon, prick för "körs", ⌘Q och Dock-menyn träffar spelet). Python körs genom en
# länk i Contents/MacOS så att macOS ser appens bunt (namn och ikon); Contents ser ut
# som en venv (pyvenv.cfg, lib -> projektets .venv/lib) så att paketen hittas.
# Projektmappen är inskriven: flyttas den, bygg om. Fel hamnar i logs/fonster.log.
set -eu

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/Projekt/Lokalt/K-114.app}"
UV="$(command -v uv || echo /opt/homebrew/bin/uv)"

cd "$PROJ"
"$UV" sync --quiet --extra fonster --inexact

PY="$(readlink -f .venv/bin/python)"
TMP="$(mktemp -d)/K-114.app"
mkdir -p "$TMP/Contents/MacOS" "$TMP/Contents/Resources"

cp ikon/K-114.icns "$TMP/Contents/Resources/K-114.icns"
cp .venv/pyvenv.cfg "$TMP/Contents/pyvenv.cfg"
ln -s "$PROJ/.venv/lib" "$TMP/Contents/lib"
ln -s "$PY" "$TMP/Contents/MacOS/python"

cat > "$TMP/Contents/MacOS/K-114" <<EOF
#!/bin/sh
cd "$PROJ" || exit 1
mkdir -p logs
exec "\$(dirname "\$0")/python" fonster.py "\$@" > logs/fonster.log 2>&1
EOF
chmod +x "$TMP/Contents/MacOS/K-114"

cat > "$TMP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>K-114</string>
  <key>CFBundleDisplayName</key><string>K-114</string>
  <key>CFBundleIdentifier</key><string>local.k114.spel</string>
  <key>CFBundleExecutable</key><string>K-114</string>
  <key>CFBundleIconFile</key><string>K-114</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1962</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
</dict>
</plist>
EOF

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
mv "$TMP" "$DEST"
touch "$DEST"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$DEST" 2>/dev/null || true
echo "Byggd: $DEST"
