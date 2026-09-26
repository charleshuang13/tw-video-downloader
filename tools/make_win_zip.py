"""把 Windows 打包产物打成 zip（在 CI 里跑，也可以本地跑）。

用法：python tools/make_win_zip.py <版本号或标识>
产物：dist/TwVideoDownloader_<版本>_windows_x64.zip
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
EXE = DIST / "推特视频下载器.exe"
ASCII_EXE = DIST / "TwVideoDownloader.exe"


def main() -> int:
    ver = sys.argv[1] if len(sys.argv) > 1 else "dev"
    exe = EXE if EXE.exists() else ASCII_EXE
    if not exe.exists():
        print(f"找不到 exe：{EXE} 或 {ASCII_EXE}")
        return 1

    out = DIST / f"TwVideoDownloader_{ver}_windows_x64.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        # zip 里统一用中文名，解压出来就是「推特视频下载器.exe」
        z.write(exe, "推特视频下载器.exe")
        readme = ROOT / "README.md"
        if readme.exists():
            z.write(readme, "README.md")

    print(f"打包完成：{out}  {out.stat().st_size/1024/1024:.1f} MB")
    with zipfile.ZipFile(out) as z:
        for info in z.infolist():
            print(f"  {info.filename}  {info.file_size} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
