"""离线单元测试：不需要网络，也不需要图形界面。

跑法：python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twdownloader import api  # noqa: E402

TWEET_ID = "2103456485179261344"

# 一条真实推文的 fxtwitter 响应（截取自 2026-09，字段名照抄接口）
FX_VIDEO = {
    "code": 200,
    "message": "OK",
    "tweet": {
        "url": f"https://x.com/xiaoyuanovo00/status/{TWEET_ID}",
        "id": TWEET_ID,
        "text": "都说萝莉有三好！~ #小远 #萌萌出击",
        "created_at": "Fri Sep 25 12:08:01 +0000 2026",
        "author": {"screen_name": "xiaoyuanovo00", "name": "小远ovo"},
        "media": {
            "all": [
                {
                    "id": "2103448726065020928",
                    "type": "video",
                    "url": "https://video.twimg.com/amplify_video/x/vid/avc1/720x1280/hi.mp4?tag=14",
                    "thumbnail_url": "https://pbs.twimg.com/thumb.jpg",
                    "duration": 9.541,
                    "width": 1080,
                    "height": 1920,
                    "format": "video/mp4",
                    "formats": [
                        {"url": "https://video.twimg.com/pl/x.m3u8?tag=14", "container": "m3u8"},
                        {"url": "https://video.twimg.com/x/vid/avc1/320x568/lo.mp4?tag=14",
                         "bitrate": 632000, "container": "mp4", "codec": "h264"},
                        {"url": "https://video.twimg.com/x/vid/avc1/480x852/mid.mp4?tag=14",
                         "bitrate": 950000, "container": "mp4", "codec": "h264"},
                        {"url": "https://video.twimg.com/x/vid/avc1/720x1280/hi.mp4?tag=14",
                         "bitrate": 2176000, "container": "mp4", "codec": "h264"},
                    ],
                }
            ]
        },
    },
}

FX_PHOTO = {
    "code": 200,
    "message": "OK",
    "tweet": {
        "id": "999",
        "text": "两张图",
        "author": {"screen_name": "someone", "name": "某人"},
        "media": {
            "all": [
                {"type": "photo", "url": "https://pbs.twimg.com/media/a.jpg",
                 "thumbnail_url": "https://pbs.twimg.com/media/a?format=jpg&name=small",
                 "width": 1200, "height": 1600, "altText": "图一"},
                {"type": "photo", "url": "https://pbs.twimg.com/media/b.jpg", "width": 800, "height": 600},
            ]
        },
    },
}

FX_MIXED = {
    "code": 200,
    "tweet": {
        "id": "12345",
        "text": "带图和视频",
        "author": {"screen_name": "mix"},
        "media": {"all": [
            {"type": "photo", "url": "https://pbs.twimg.com/media/p.jpg"},
            {"type": "gif", "url": "https://video.twimg.com/gif.mp4",
             "formats": [{"url": "https://video.twimg.com/t/gif/320x320/g.mp4", "container": "mp4",
                          "bitrate": 1}]},
        ]},
    },
}

FX_FAIL = {"code": 404, "message": "NOT_FOUND", "tweet": None}

VX_JSON = {
    "tweetID": TWEET_ID,
    "user_screen_name": "xiaoyuanovo00",
    "user_name": "小远ovo",
    "text": "都说萝莉有三好！~",
    "date": "Fri Sep 25 12:08:01 +0000 2026",
    "media_extended": [
        {"type": "video", "url": "https://video.twimg.com/vx.mp4",
         "thumbnail_url": "https://pbs.twimg.com/vx.jpg",
         "duration_millis": 9541, "size": {"width": 1080, "height": 1920}},
    ],
}


class TestLinkParse(unittest.TestCase):
    def test_variants(self):
        cases = {
            f"https://x.com/xiaoyuanovo00/status/{TWEET_ID}": ("xiaoyuanovo00", TWEET_ID),
            f"https://x.com/xiaoyuanovo00/status/{TWEET_ID}?s=20&t=abc": ("xiaoyuanovo00", TWEET_ID),
            f"https://twitter.com/x/status/{TWEET_ID}/video/1": ("x", TWEET_ID),
            f"https://x.com/i/status/{TWEET_ID}": (None, TWEET_ID),
            f"https://x.com/i/web/status/{TWEET_ID}": (None, TWEET_ID),
            f"  {TWEET_ID}  ": (None, TWEET_ID),
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(api.parse_ref(raw), want)

    def test_reject(self):
        for bad in ("", "你好", "https://x.com/someone", "https://youtube.com/watch?v=1"):
            with self.subTest(bad=bad):
                with self.assertRaises(api.ParseError):
                    api.parse_ref(bad)

    def test_split_dedupe(self):
        # 推文 ID 是 19 位雪花号，太短的（如 12345）不认
        second = "1900000000000000123"
        text = f"{TWEET_ID}\nhttps://x.com/a/status/{TWEET_ID}\n垃圾\n {second} \n{second}\n12345"
        out = api.split_inputs(text)
        self.assertEqual([tid for _, tid in out], [TWEET_ID, second])


class TestFxParse(unittest.TestCase):
    def test_video(self):
        tw = api.fx_json_to_tweet(FX_VIDEO, "xiaoyuanovo00", TWEET_ID)
        self.assertEqual(tw.handle, "xiaoyuanovo00")
        self.assertEqual(len(tw.media), 1)
        m = tw.media[0]
        self.assertTrue(m.is_video)
        self.assertAlmostEqual(m.duration, 9.541, places=3)
        # 竖屏 720x1280 要按短边标成 720p，不能标 1280p
        self.assertEqual(m.quality_labels(), ["720p", "480p", "320p"])
        self.assertIn("720x1280", m.pick("最高"))
        self.assertIn("480x852", m.pick("480p"))
        # 360p 没有对应档位 → 退到最接近的低档
        self.assertIn("320x568", m.pick("360p"))

    def test_m3u8_excluded(self):
        tw = api.fx_json_to_tweet(FX_VIDEO)
        self.assertNotIn(".m3u8", tw.media[0].pick("最高"))

    def test_photo(self):
        tw = api.fx_json_to_tweet(FX_PHOTO, "someone", "999")
        self.assertEqual([m.kind for m in tw.media], ["photo", "photo"])
        self.assertEqual(tw.media[0].alt, "图一")
        # 图片没有档位概念
        self.assertEqual(tw.media[0].pick("480p"), tw.media[0].url)

    def test_mixed(self):
        tw = api.fx_json_to_tweet(FX_MIXED)
        self.assertEqual([m.kind for m in tw.media], ["photo", "gif"])
        self.assertTrue(tw.media[1].is_video)
        self.assertEqual(tw.media[1].quality_labels(), ["320p"])

    def test_bad_code(self):
        with self.assertRaises(api.ParseError):
            api.fx_json_to_tweet(FX_FAIL)


class TestVxParse(unittest.TestCase):
    def test_video(self):
        tw = api.vx_json_to_tweet(VX_JSON, "xiaoyuanovo00", TWEET_ID)
        self.assertEqual(tw.source, "vxtwitter")
        self.assertEqual(tw.handle, "xiaoyuanovo00")
        self.assertAlmostEqual(tw.media[0].duration, 9.541, places=3)
        self.assertEqual(tw.page_url, f"https://x.com/xiaoyuanovo00/status/{TWEET_ID}")


class TestDownloadGuard(unittest.TestCase):
    """用 file:// 本地文件验证 <2KB 判失败 + .part 不留残片。"""

    def test_tiny_content_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "tiny.bin"
            src.write_bytes(b"x" * 100)
            dest = Path(d) / "out.mp4"
            with self.assertRaises(api.ParseError):
                api.download(src.as_uri(), dest)
            self.assertFalse(dest.exists())
            self.assertFalse((dest.parent / (dest.name + ".part")).exists())

    def test_ok_content(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "ok.bin"
            src.write_bytes(b"y" * 5000)
            dest = Path(d) / "out.bin"
            n = api.download(src.as_uri(), dest)
            self.assertEqual(n, 5000)
            self.assertEqual(dest.stat().st_size, 5000)
            self.assertFalse((dest.parent / (dest.name + ".part")).exists())


class TestCompat(unittest.TestCase):
    """Windows 控制台默认 cp1252，打印中文会 UnicodeEncodeError（CI 上真挂过）。"""

    def test_enable_utf8_stdout(self):
        from twdownloader import compat

        compat.enable_utf8_stdout()
        print("中文打印正常：推特视频下载器")

    def test_survives_none_stdout(self):
        # 打包成 windowed 应用时 sys.stdout 是 None
        from twdownloader import compat

        old = sys.stdout
        try:
            sys.stdout = None
            compat.enable_utf8_stdout()
        finally:
            sys.stdout = old


class TestSummary(unittest.TestCase):
    def test_truncate(self):
        tw = api.fx_json_to_tweet(FX_VIDEO)
        self.assertTrue(tw.summary(6).endswith("…"))
        self.assertEqual(tw.summary(100), " ".join(tw.text.split()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
