import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import tt


class _FakeRegistryKey:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self.path

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def CreateKey(self, root, path):
        self.assert_root = root
        return _FakeRegistryKey(path)

    def SetValueEx(self, key, name, reserved, value_type, value):
        self.values[(key, name)] = (value_type, value)


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

    def test_context_menu_icon_uses_exe_path_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "torrentTOmagnet.exe"
            result = tt.context_menu_icon(os.fspath(executable))
            self.assertEqual(result, os.path.abspath(executable))

    def test_add_context_menu_sets_label_icon_multi_select_and_never_default(self):
        fake_winreg = _FakeWinreg()
        executable = os.path.join("some folder", "torrentTOmagnet.exe")
        absolute_executable = os.path.abspath(executable)
        output = StringIO()

        with (
            patch.object(tt, "winreg", fake_winreg),
            patch.object(tt, "notify_shell_association_changed") as notify,
            redirect_stdout(output),
        ):
            tt.add_context_menu(executable)

        values = fake_winreg.values
        self.assertEqual(values[(tt.REGISTRY_KEY, "")], (fake_winreg.REG_SZ, tt.MENU_LABEL))
        self.assertEqual(values[(tt.REGISTRY_KEY, "MUIVerb")], (fake_winreg.REG_SZ, tt.MENU_LABEL))
        self.assertEqual(values[(tt.REGISTRY_KEY, "NeverDefault")], (fake_winreg.REG_SZ, ""))
        self.assertEqual(values[(tt.REGISTRY_KEY, "MultiSelectModel")], (fake_winreg.REG_SZ, "Player"))
        self.assertEqual(values[(tt.REGISTRY_KEY, "Icon")], (fake_winreg.REG_SZ, absolute_executable))
        self.assertEqual(
            values[(tt.REGISTRY_KEY + r"\command", "")],
            (fake_winreg.REG_SZ, f'"{absolute_executable}" "%1"'),
        )
        self.assertIn(tt.MENU_LABEL, output.getvalue())
        notify.assert_called_once_with()

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
