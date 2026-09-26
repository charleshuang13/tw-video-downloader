#!/usr/bin/env bash
# twdl —— 推特(X) 视频/图片下载器（命令行版）
# 用法:
#   ./tools/twdl.sh <推文链接或ID> [...]
#   ./tools/twdl.sh -o ~/Desktop <链接>
# 原理: 先用 yt-dlp 抓(走 guest token)，失败就退回 fxtwitter API 拿直链 curl。
set -uo pipefail

OUTDIR="$HOME/Downloads/TwitterDL"
if [ "${1:-}" = "-o" ]; then OUTDIR="$2"; shift 2; fi
[ $# -eq 0 ] && { echo "用法: twdl [-o 输出目录] <推文链接或ID> [...]"; exit 1; }
mkdir -p "$OUTDIR"

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"

for ARG in "$@"; do
  echo "=========================================="
  echo "处理: $ARG"

  # ---- 解析出 screen_name / tweet_id ----
  CLEAN=$(echo "$ARG" | sed -E 's#\?.*$##; s#/video/[0-9]+$##; s#/photo/[0-9]+$##')
  ID=$(echo "$CLEAN" | grep -oE '[0-9]{15,25}' | tail -1)
  if [ -z "$ID" ]; then
    echo "  认不出推文ID，请贴完整链接"
    continue
  fi
  NAME=$(echo "$CLEAN" | sed -E 's#^(https?://)?(www\.)?(x|twitter)\.com/##; s#/.*$##')
  [ -z "$NAME" ] && NAME="i"

  URL="https://x.com/${NAME}/status/${ID}"

  # ---- 主路径: yt-dlp ----
  echo "  → yt-dlp 抓取..."
  yt-dlp --no-warnings --no-playlist \
        -f "http-2176/http-950/http-632/bv*+ba/b" \
        --merge-output-format mp4 \
        -o "${OUTDIR}/${NAME}_${ID}_%(autonumber)02d.%(ext)s" \
        "$URL" 2>&1 | grep -viE '^\s*$' | tail -8 || true

  GOT=$(find "$OUTDIR" -maxdepth 1 -name "${NAME}_${ID}_*.mp4" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$GOT" != "0" ]; then
    echo "  视频已下载 ($GOT 个)"
  else
    # ---- 备用路径: fxtwitter API + curl ----
    echo "  → 视频没拿到，改走 fxtwitter 直链..."
    JSON=$(curl -s -m 25 -A "$UA" "https://api.fxtwitter.com/${NAME}/status/${ID}")
    echo "$JSON" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)["tweet"]
except Exception: sys.exit(3)
media=(d.get("media") or {}).get("all") or []
n=0
for m in media:
    if m.get("type")=="video" or m.get("type")=="gif":
        best=max((f for f in m.get("formats",[]) if f.get("container")=="mp4"),
                 key=lambda f: f.get("bitrate") or 0, default=None)
        print("VID", best["url"] if best else m.get("url"))
        n+=1
    elif m.get("type")=="photo":
        print("PHO", m["url"]+"?name=orig")
        n+=1
if n==0: sys.exit(4)
' > /tmp/twdl_links.txt
    RC=$?
    if [ $RC -eq 0 ]; then
      i=0
      while read -r KIND LINK; do
        i=$((i+1))
        EXT=$([ "$KIND" = "PHO" ] && echo jpg || echo mp4)
        DEST="${OUTDIR}/${NAME}_${ID}_$(printf '%02d' $i).${EXT}"
        curl -sL -m 120 -A "$UA" -e "https://x.com/" -o "$DEST" "$LINK"
        SZ=$(stat -f%z "$DEST" 2>/dev/null || echo 0)
        if [ "$SZ" -gt 20000 ]; then
          echo "  已下载 $(basename "$DEST")  ($((SZ/1024)) KB)"
        else
          rm -f "$DEST"; echo "  第 ${i} 个媒体下载失败"
        fi
      done < /tmp/twdl_links.txt
    else
      echo "  这条推文可能已删除/受保护/仅有文字，或网络被墙"
    fi
  fi
done

echo "=========================================="
echo "输出目录: $OUTDIR"
ls -lh "$OUTDIR" 2>/dev/null | tail -20
