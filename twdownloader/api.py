"""推文媒体解析 —— 纯标准库 HTTP，不依赖 yt-dlp。

主接口 api.fxtwitter.com（无需登录，返回结构化 JSON），
备用 api.vxtwitter.com，再不行退回本机 yt-dlp 命令行。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Referer": "https://x.com/", "Accept": "*/*"}

FX = "https://api.fxtwitter.com"
VX = "https://api.vxtwitter.com"
TIMEOUT = 25

LINK_RE = re.compile(
    r"(?:x|twitter)\.com/(?:i/(?:web/)?status/|([A-Za-z0-9_]{1,20})/status(?:es)?/)(\d{6,25})"
)
BARE_ID_RE = re.compile(r"^(\d{15,25})$")
RES_RE = re.compile(r"/(\d{3,4})x(\d{3,4})/")


class ParseError(Exception):
    """解析失败，message 直接给用户看。"""


@dataclass
class Variant:
    url: str
    label: str = ""
    bitrate: int = 0
    height: int = 0


@dataclass
class MediaItem:
    kind: str                      # video / gif / photo
    url: str                       # 最高画质
    thumbnail: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    alt: str = ""
    variants: list = field(default_factory=list)   # 仅视频/GIF

    @property
    def is_video(self) -> bool:
        return self.kind in ("video", "gif")

    def quality_labels(self) -> list:
        """返回可选清晰度标签，最高的排前面。"""
        seen, out = set(), []
        for v in sorted(self.variants, key=lambda x: x.bitrate, reverse=True):
            if v.label and v.label not in seen:
                seen.add(v.label)
                out.append(v.label)
        return out or (["最高"] if self.is_video else [])

    def pick(self, prefer: str) -> str:
        """按清晰度标签选 URL；找不到就退回最接近的低档。"""
        if not self.variants:
            return self.url
        vs = sorted(self.variants, key=lambda x: x.bitrate, reverse=True)
        if not prefer or prefer.startswith("最高"):
            return vs[0].url
        for v in vs:
            if v.label == prefer:
                return v.url
        m = re.search(r"\d{3,4}", prefer)
        if m:
            want = int(m.group())
            lower = [v for v in vs if v.height and v.height <= want]
            if lower:
                return lower[0].url
        return vs[-1].url


@dataclass
class Tweet:
    id: str
    handle: str
    author: str
    text: str
    created: str
    media: list = field(default_factory=list)
    source: str = "fxtwitter"

    @property
    def page_url(self) -> str:
        return f"https://x.com/{self.handle}/status/{self.id}"

    def summary(self, limit: int = 40) -> str:
        t = " ".join(self.text.split())
        return t[:limit] + ("…" if len(t) > limit else "")


# --------------------------------------------------------------------------- #
# 链接解析
# --------------------------------------------------------------------------- #

def parse_ref(raw: str):
    """把用户贴进来的东西解析成 (handle 或 None, tweet_id)。

    支持：x.com/twitter.com 链接、/i/status/ 形式、带 ?s= 后缀、裸推文ID。
    """
    s = (raw or "").strip()
    if not s:
        raise ParseError("是空的")
    m = LINK_RE.search(s)
    if m:
        return (m.group(1) or None), m.group(2)
    m = BARE_ID_RE.match(s)
    if m:
        return None, m.group(1)
    raise ParseError("认不出推文链接 / ID")


def split_inputs(text: str) -> list:
    """从多行文本里抽出所有链接或ID，去重保序。"""
    out, seen = [], set()
    for tok in re.split(r"[\s,，、;；]+", text or ""):
        if not tok:
            continue
        try:
            handle, tid = parse_ref(tok)
        except ParseError:
            continue
        if tid in seen:
            continue
        seen.add(tid)
        out.append((handle, tid))
    return out


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def _get(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _from_fx(handle, tid) -> Tweet:
    path = f"/{handle}/status/{tid}" if handle else f"/status/{tid}"
    data = json.loads(_get(FX + path).decode("utf-8", "replace"))
    return fx_json_to_tweet(data, handle, tid)


def fx_json_to_tweet(data, handle=None, tid=None) -> Tweet:
    """把 fxtwitter 的 JSON 转成 Tweet（与网络解耦，方便离线测试）。"""
    if data.get("code") != 200 or not data.get("tweet"):
        raise ParseError(f"接口返回 code={data.get('code')}")
    t = data["tweet"]
    media = []
    for m in (t.get("media") or {}).get("all") or []:
        mtype = m.get("type") or ""
        if mtype in ("video", "gif"):
            variants = []
            for f in m.get("formats") or []:
                if f.get("container") != "mp4":
                    continue
                res = RES_RE.search(f.get("url", ""))
                # 竖屏视频 URL 形如 /vid/avc1/720x1280/，X 是按短边命名清晰度的，
                # 所以取小值当“720p/480p/320p”，别拿 1280 当高度
                h = min(int(res.group(1)), int(res.group(2))) if res else 0
                variants.append(
                    Variant(
                        url=f["url"],
                        label=f"{h}p" if h else "最高",
                        bitrate=int(f.get("bitrate") or 0),
                        height=h,
                    )
                )
            if not variants and m.get("url"):
                variants = [Variant(url=m["url"], label="最高")]
            best = max(variants, key=lambda v: v.bitrate, default=None)
            media.append(
                MediaItem(
                    kind=mtype,
                    url=best.url if best else m.get("url", ""),
                    thumbnail=m.get("thumbnail_url") or "",
                    duration=float(m.get("duration") or 0),
                    width=int(m.get("width") or 0),
                    height=int(m.get("height") or 0),
                    variants=variants,
                )
            )
        elif mtype == "photo":
            media.append(
                MediaItem(
                    kind="photo",
                    url=m.get("url", ""),
                    thumbnail=m.get("thumbnail_url") or m.get("url", ""),
                    width=int(m.get("width") or 0),
                    height=int(m.get("height") or 0),
                    alt=m.get("altText") or "",
                )
            )
    return Tweet(
        id=str(t.get("id") or tid),
        handle=(t.get("author") or {}).get("screen_name") or (handle or "i"),
        author=(t.get("author") or {}).get("name") or "",
        text=t.get("text") or "",
        created=t.get("created_at") or "",
        media=media,
    )


def _from_vx(handle, tid) -> Tweet:
    if not handle:
        raise ParseError("备用接口需要带用户名的链接")
    data = json.loads(_get(f"{VX}/{handle}/status/{tid}").decode("utf-8", "replace"))
    return vx_json_to_tweet(data, handle, tid)


def vx_json_to_tweet(data, handle=None, tid=None) -> Tweet:
    """把 vxtwitter 的 JSON 转成 Tweet（与网络解耦）。"""
    media = []
    for m in data.get("media_extended") or []:
        mtype = m.get("type") or ""
        if mtype in ("video", "gif"):
            media.append(
                MediaItem(
                    kind=mtype,
                    url=m.get("url", ""),
                    thumbnail=m.get("thumbnail_url") or "",
                    duration=float(m.get("duration_millis") or 0) / 1000.0,
                    width=int((m.get("size") or {}).get("width") or 0),
                    height=int((m.get("size") or {}).get("height") or 0),
                )
            )
        elif mtype in ("image", "photo"):
            media.append(MediaItem(kind="photo", url=m.get("url", ""), thumbnail=m.get("url", "")))
    if not media:
        raise ParseError("备用接口没有媒体信息")
    return Tweet(
        id=str(data.get("tweetID") or tid),
        handle=data.get("user_screen_name") or handle,
        author=data.get("user_name") or "",
        text=data.get("text") or "",
        created=data.get("date") or "",
        media=media,
        source="vxtwitter",
    )


def fetch_tweet(handle, tid) -> Tweet:
    """解析一条推文，接口全挂时退回本机 yt-dlp。"""
    errs = []
    for fn in (_from_fx, _from_vx):
        try:
            tw = fn(handle, tid)
            if tw.media:
                return tw
            errs.append(f"{fn.__name__}: 这条推文没有媒体（纯文字）")
        except ParseError as e:
            errs.append(f"{fn.__name__}: {e}")
        except urllib.error.HTTPError as e:
            errs.append(f"{fn.__name__}: HTTP {e.code}")
        except Exception as e:                     # 接口挂了会返回 HTML，json 直接炸
            errs.append(f"{fn.__name__}: {type(e).__name__} {e}")
    raise ParseError("；".join(errs))


# --------------------------------------------------------------------------- #
# 下载
# --------------------------------------------------------------------------- #

def download(url: str, dest: Path, on_progress=None, should_stop=None) -> int:
    """流式下载，返回字节数。on_progress(已下载, 总大小)，should_stop() -> True 表示取消。"""
    req = urllib.request.Request(url, headers=HEADERS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    got = 0
    with urllib.request.urlopen(req, timeout=30) as r:
        total = int(r.headers.get("Content-Length") or 0)
        with open(tmp, "wb") as f:
            while True:
                if should_stop and should_stop():
                    raise InterruptedError("已取消")
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if on_progress:
                    on_progress(got, total)
    if got < 2048:
        tmp.unlink(missing_ok=True)
        raise ParseError("下载内容过小，多半是链接失效或被墙（只有 %d 字节）" % got)
    tmp.replace(dest)
    return got


def ytdlp_path():
    for p in ("/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp", shutil.which("yt-dlp")):
        if p and Path(p).exists():
            return p
    return None


def download_by_ytdlp(url: str, outdir: Path, on_log=None, should_stop=None) -> list:
    """兜底方案：调用本机 yt-dlp（走 guest token，能处理需要登录的推文）。"""
    exe = ytdlp_path()
    if not exe:
        raise ParseError("本机没装 yt-dlp，兜底方案不可用")
    cmd = [
        exe, "--no-warnings", "--no-playlist",
        "-f", "http-2176/http-950/http-632/bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", str(outdir / "%(uploader_id)s_%(id)s_%(autonumber)02d.%(ext)s"),
        url,
    ]
    if on_log:
        on_log("调用本机 yt-dlp 兜底…")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    made = [Path(l) for l in (r.stdout or "").splitlines() if l.startswith("[download] Destination:")]
    files = sorted(outdir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[:4]
    files = [f for f in files if f.is_file() and f.suffix in (".mp4", ".jpg", ".png", ".webp")]
    if not files:
        raise ParseError("yt-dlp 也没抓到：" + (r.stderr or r.stdout or "无输出").strip().splitlines()[-1:][0])
    return files
