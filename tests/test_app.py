import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import tt


class ApplicationTests(unittest.TestCase):
    def test_application_directory_uses_executable_when_frozen(self):
        executable = Path("C:/工具目录/torrentTOmagnet.exe")

        result = tt.application_directory(
            is_frozen=True,
            executable_path=executable,
            source_path=Path("C:/源码/tt.py"),
        )

        self.assertEqual(result, executable.resolve().parent)

    def test_find_torrent_files_returns_all_immediate_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            expected = [directory / "B.TORRENT", directory / "中文 & 🧲.torrent"]
            for path in expected:
                path.write_bytes(b"torrent")
            (directory / "ignore.txt").write_text("not a torrent", encoding="utf-8")
            nested = directory / "nested"
            nested.mkdir()
            (nested / "nested.torrent").write_bytes(b"torrent")

            result = tt.find_torrent_files(directory)

            self.assertEqual(result, expected)

    def test_process_torrents_in_directory_converts_discovered_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            name = "特殊 & 🧲".encode()
            torrent = b"d4:infod4:name" + str(len(name)).encode() + b":" + name + b"ee"
            (directory / "特殊 & 🧲.torrent").write_bytes(torrent)
            output = StringIO()

            with redirect_stdout(output):
                result = tt.process_torrents_in_directory(directory, pause=False)

            self.assertEqual(result, 0)
            self.assertIn("找到 1 个种子文件", output.getvalue())
            self.assertIn("magnet:?xt=urn:btih:", output.getvalue())

    def test_run_without_arguments_scans_executable_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            name = "自动发现".encode()
            torrent = b"d4:infod4:name" + str(len(name)).encode() + b":" + name + b"ee"
            (directory / "自动发现.torrent").write_bytes(torrent)
            output = StringIO()

            with redirect_stdout(output):
                result = tt.run(
                    [],
                    is_frozen=True,
                    executable_path=directory / "torrentTOmagnet.exe",
                    source_path=Path(tt.__file__),
                    pause=False,
                )

            self.assertEqual(result, 0)
            self.assertIn("自动发现.torrent", output.getvalue())


if __name__ == "__main__":
    unittest.main()
