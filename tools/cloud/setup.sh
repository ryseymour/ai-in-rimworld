#!/usr/bin/env bash
# One-shot setup for running RimWorld + AiRim headless in a cloud container (Ubuntu).
# Usage: tools/cloud/setup.sh <github-release-asset-id-or-url-of-rimworld-linux-tarball>
# The asset must be a tar.gz or zip of the RimWorld Linux build (folder containing RimWorldLinux + RimWorldLinux_Data).
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_DIR="${GAME_DIR:-$HOME/rimworld}"
ASSET="${1:?asset id or download url}"
OWNER_REPO="${OWNER_REPO:-ryseymour/ai-in-rimworld}"

echo "== packages"
if ! command -v Xvfb >/dev/null; then
  sudo_cmd=""; [ "$(id -u)" -ne 0 ] && sudo_cmd=sudo
  $sudo_cmd apt-get update -qq
  $sudo_cmd apt-get install -y -qq xvfb libgl1-mesa-dri libglu1-mesa mesa-utils x11-apps imagemagick libxcursor1 libxrandr2 libxinerama1 libxi6 libxss1 libgtk-3-0 unzip curl
fi
command -v dotnet >/dev/null || { echo "dotnet SDK 8 required (apt-get install dotnet-sdk-8.0)"; exit 1; }

echo "== build mod"
(cd "$REPO_DIR/mod/Source/AiRim" && dotnet build -c Release --nologo -v q)

echo "== game files"
mkdir -p "$GAME_DIR"
if [ ! -x "$GAME_DIR/RimWorldLinux" ]; then
  TMP="$(mktemp -d)"
  if [[ "$ASSET" =~ ^[0-9]+$ ]]; then
    URL="https://api.github.com/repos/$OWNER_REPO/releases/assets/$ASSET"
  else
    URL="$ASSET"
  fi
  echo "downloading $URL"
  curl -fL --retry 3 -H "Authorization: Bearer ${GITHUB_TOKEN:?GITHUB_TOKEN needed}" -H "Accept: application/octet-stream" -o "$TMP/game.bin" "$URL"
  if file "$TMP/game.bin" | grep -qi zip; then unzip -q "$TMP/game.bin" -d "$TMP/x"; else mkdir "$TMP/x" && tar -xzf "$TMP/game.bin" -C "$TMP/x"; fi
  # find the folder containing the binary at any depth
  BIN="$(find "$TMP/x" -maxdepth 4 -name RimWorldLinux -type f | head -1)"
  [ -n "$BIN" ] || { echo "RimWorldLinux binary not found in archive"; exit 1; }
  cp -a "$(dirname "$BIN")"/. "$GAME_DIR"/
  chmod +x "$GAME_DIR/RimWorldLinux"
  rm -rf "$TMP"
fi
ls "$GAME_DIR" | head

echo "== mods"
mkdir -p "$GAME_DIR/Mods"
ln -sfn "$REPO_DIR/tools/harmony-mod" "$GAME_DIR/Mods/Harmony"
ln -sfn "$REPO_DIR/mod" "$GAME_DIR/Mods/AiRim"

echo "== config"
CFG="$HOME/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config"
mkdir -p "$CFG"
VER="$(cat "$GAME_DIR/Version.txt" 2>/dev/null || echo 1.6)"
cat > "$CFG/ModsConfig.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<ModsConfigData>
  <version>$VER</version>
  <activeMods>
    <li>ludeon.rimworld</li>
    <li>brrainz.harmony</li>
    <li>ryseymour.airim</li>
  </activeMods>
  <knownExpansions />
</ModsConfigData>
XML
cat > "$CFG/Prefs.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<PrefsData>
  <devMode>True</devMode>
  <logVerbose>False</logVerbose>
  <screenWidth>1600</screenWidth>
  <screenHeight>900</screenHeight>
  <fullscreen>False</fullscreen>
  <runInBackground>True</runInBackground>
  <pauseOnLoad>False</pauseOnLoad>
  <volumeMaster>0</volumeMaster>
  <uiScale>1</uiScale>
</PrefsData>
XML
echo "done. run: tools/cloud/run.sh"
