"""torrentTOmagnet Windows 命令行入口。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import sys
import time

from torrent_to_magnet import TorrentError, torrent_to_magnet

try:
    import winreg
except ImportError:  # 允许在非 Windows 平台运行核心测试
    winreg = None


APP_NAME = "torrentTOmagnet"
MENU_LABEL = "种子转磁力链接"
REGISTRY_KEY = (
    r"Software\Classes\SystemFileAssociations\.torrent\shell\torrentTOmagnet"
)


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(errors="replace")


def copy_to_clipboard(text: str) -> None:
    """通过 Win32 Unicode Clipboard 写入文本，不依赖第三方包。"""
    if os.name != "nt":
        raise RuntimeError("剪贴板功能仅支持 Windows")

    cf_unicode_text = 13
    gmem_moveable = 0x0002
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)
    user32.SetClipboardData.restype = ctypes.c_void_p
    payload = (text + "\0").encode("utf-16-le")

    handle = kernel32.GlobalAlloc(gmem_moveable, len(payload))
    if not handle:
        raise OSError("GlobalAlloc 失败")
    clipboard_owns_handle = False
    try:
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise OSError("GlobalLock 失败")
        try:
            ctypes.memmove(pointer, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(handle)

        for attempt in range(10):
            if user32.OpenClipboard(None):
                break
            time.sleep(0.05 * (attempt + 1))
        else:
            raise OSError("剪贴板正被其他程序占用")

        try:
            if not user32.EmptyClipboard():
                raise OSError("EmptyClipboard 失败")
            if not user32.SetClipboardData(cf_unicode_text, handle):
                raise OSError("SetClipboardData 失败")
            clipboard_owns_handle = True
        finally:
            user32.CloseClipboard()
    finally:
        if not clipboard_owns_handle:
            kernel32.GlobalFree(handle)


def add_context_menu(executable_path: str) -> None:
    if winreg is None:
        raise RuntimeError("右键菜单仅支持 Windows")
    command = f'"{executable_path}" "%1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, MENU_LABEL)
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, executable_path)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY + r"\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
    print(f"已添加 .torrent 文件右键菜单“{MENU_LABEL}”（无需管理员权限）。")


def remove_context_menu() -> None:
    if winreg is None:
        raise RuntimeError("右键菜单仅支持 Windows")
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY + r"\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
        print(f"已删除右键菜单“{MENU_LABEL}”。")
    except FileNotFoundError:
        print("右键菜单尚未安装。")


def process_files(paths: list[str]) -> int:
    magnet_links = []
    failures = []
    for raw_path in paths:
        path = os.path.abspath(raw_path)
        try:
            magnet = torrent_to_magnet(path)
        except (TorrentError, OSError) as exc:
            failures.append((path, str(exc)))
            print(f"[失败] {path}\n  {exc}")
            continue
        magnet_links.append(magnet)
        print(f"[成功] {path}\n{magnet}\n")

    if magnet_links:
        try:
            copy_to_clipboard("\r\n".join(magnet_links))
            print(f"已将 {len(magnet_links)} 个磁力链接复制到剪贴板。")
        except Exception as exc:
            print(f"无法写入剪贴板（磁力链接已显示在上方）：{exc}")

    if failures:
        input("\n部分文件转换失败，按 Enter 键退出...")
        return 1
    return 0


def main() -> int:
    configure_console()
    if len(sys.argv) > 1:
        return process_files(sys.argv[1:])

    print("torrentTOmagnet 2.0.0 — 种子转磁力链接")
    print("可把一个或多个 .torrent 文件拖到本程序图标上直接转换。\n")
    print("1. 安装 .torrent 文件右键菜单（无需管理员权限）")
    print("2. 删除右键菜单")
    print("3. 退出")
    choice = input("请选择（1/2/3）：").strip()

    try:
        if choice == "1":
            add_context_menu(os.path.abspath(sys.argv[0]))
        elif choice == "2":
            remove_context_menu()
        elif choice != "3":
            print("无效选择。")
            return 2
    except (OSError, RuntimeError) as exc:
        print(f"操作失败：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())