#!/bin/sh
# Builds TurboSwitch-x86_64.AppImage from ./AppDir
set -e
cd "$(dirname "$0")"
[ -x appimagetool ] || {
  curl -fsSL -o appimagetool \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x appimagetool
}
ARCH=x86_64 ./appimagetool --appimage-extract-and-run AppDir TurboSwitch-x86_64.AppImage
echo "Built: TurboSwitch-x86_64.AppImage"
