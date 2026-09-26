#!/usr/bin/env bash
# 打包 macOS .app（arm64）。首次跑会自动建 venv 装依赖。
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="推特视频下载器"
VENV=".venv"

if [ ! -d "$VENV" ]; then
  echo "== 建 venv =="
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r requirements.txt
fi

echo "== 生成图标 =="
QT_QPA_PLATFORM=offscreen "$VENV/bin/python" make_icon.py

if [ ! -f icon.icns ] || [ icon.png -nt icon.icns ]; then
  echo "== PNG → icns =="
  rm -rf icon.iconset && mkdir icon.iconset
  for s in 16 32 128 256 512; do
    sips -z $s $s icon.png --out "icon.iconset/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) icon.png --out "icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns icon.iconset -o icon.icns
fi

echo "== PyInstaller 打包 =="
rm -rf build dist
"$VENV/bin/pyinstaller" --noconfirm --windowed \
  --name "$APP_NAME" \
  --icon icon.icns \
  --hidden-import PySide6.QtSvg \
  main.py

echo
echo "== 产物 =="
ls -d "dist/$APP_NAME.app"
/usr/libexec/PlistBuddy -c "Print :CFBundleIconFile" "dist/$APP_NAME.app/Contents/Info.plist" || true
du -sh "dist/$APP_NAME.app"
