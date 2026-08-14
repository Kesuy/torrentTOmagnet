import hashlib
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from torrent_to_magnet import TorrentError, torrent_bytes_to_magnet, torrent_to_magnet


def bencode(value):
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, list):
        return b"l" + b"".join(bencode(item) for item in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(bencode(k) + bencode(value[k]) for k in sorted(value)) + b"e"
    raise TypeError(type(value))


class MagnetTests(unittest.TestCase):
    def test_special_characters_are_percent_encoded_and_round_trip(self):
        name = "中文 & # + % ? = 空格/emoji-🧲.mkv"
        tracker = "https://tracker.example/announce?a=1&名称=测试"
        info = {b"length": 1, b"name": name.encode(), b"piece length": 16384, b"pieces": b"x" * 20}
        data = bencode({b"announce": tracker.encode(), b"info": info})

        magnet = torrent_bytes_to_magnet(data)
        query = parse_qs(urlsplit(magnet).query)

        self.assertEqual(query["dn"], [name])
        self.assertEqual(query["tr"], [tracker])
        self.assertNotIn(" ", magnet)
        self.assertIn("%26", magnet)
        self.assertIn("%23", magnet)
        self.assertIn("%F0%9F%A7%B2", magnet)

    def test_info_hash_uses_original_info_bytes(self):
        # 非规范键顺序仍必须按原始字节计算哈希，不能解码后重新编码。
        info_bytes = b"d4:name4:test6:lengthi1ee"
        data = b"d4:info" + info_bytes + b"e"
        magnet = torrent_bytes_to_magnet(data)
        self.assertIn(hashlib.sha1(info_bytes).hexdigest(), magnet)

    def test_encoding_hint_supports_gb18030_names(self):
        name = "特殊字符测试【合集】"
        info = {b"name": name.encode("gb18030"), b"length": 1}
        data = bencode({b"encoding": b"GB18030", b"info": info})
        query = parse_qs(urlsplit(torrent_bytes_to_magnet(data)).query)
        self.assertEqual(query["dn"], [name])

    def test_name_utf8_takes_precedence(self):
        info = {b"name": b"legacy", b"name.utf-8": "优先名称".encode(), b"length": 1}
        data = bencode({b"info": info})
        query = parse_qs(urlsplit(torrent_bytes_to_magnet(data)).query)
        self.assertEqual(query["dn"], ["优先名称"])

    def test_v2_torrent_uses_btmh(self):
        info = {b"file tree": {}, b"meta version": 2, b"name": b"v2"}
        info_bytes = bencode(info)
        magnet = torrent_bytes_to_magnet(b"d4:info" + info_bytes + b"e")
        query = parse_qs(urlsplit(magnet).query)
        self.assertEqual(query["xt"], ["urn:btmh:1220" + hashlib.sha256(info_bytes).hexdigest()])

    def test_hybrid_torrent_has_v1_and_v2_hashes(self):
        info = {b"meta version": 2, b"name": b"hybrid", b"pieces": b"x" * 20}
        query = parse_qs(urlsplit(torrent_bytes_to_magnet(bencode({b"info": info}))).query)
        self.assertEqual(len(query["xt"]), 2)
        self.assertTrue(query["xt"][0].startswith("urn:btih:"))
        self.assertTrue(query["xt"][1].startswith("urn:btmh:"))

    def test_unicode_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "种子 & [测试] 🧲.torrent"
            path.write_bytes(bencode({b"info": {b"length": 1}}))
            query = parse_qs(urlsplit(torrent_to_magnet(path)).query)
            self.assertEqual(query["dn"], [path.stem])

    def test_invalid_torrent_has_clear_error(self):
        with self.assertRaisesRegex(TorrentError, "缺少 info"):
            torrent_bytes_to_magnet(b"de")


if __name__ == "__main__":
    unittest.main()
