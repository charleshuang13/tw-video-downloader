@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo == 推特视频下载器 Windows 打包 ==
echo.

REM ---- venv ----
if not exist .venv (
  echo == 建 venv ==
  python -m venv .venv || goto :fail
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\pip install -q -r requirements.txt || goto :fail
)

REM ---- 图标 ----
echo == 生成图标 ==
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python make_icon.py || goto :fail

REM ---- 打包 ----
echo == PyInstaller 打包（单文件 exe）==
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
.venv\Scripts\pyinstaller --noconfirm --windowed --onefile ^
  --name TwVideoDownloader ^
  --icon icon.ico ^
  --hidden-import PySide6.QtSvg ^
  main.py || goto :fail

REM ---- 产物改名成中文（打包用英文名更稳，交付用中文名更友好）----
if exist "dist\TwVideoDownloader.exe" move /y "dist\TwVideoDownloader.exe" "dist\推特视频下载器.exe" >nul

echo.
echo == 产物 ==
dir /b dist
echo.
echo 可执行文件在 dist\推特视频下载器.exe
goto :eof

:fail
echo.
echo 打包失败，看上面的报错。
exit /b 1
