"""torrentTOmagnet Windows 命令行入口。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

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
CONTEXT_MUTEX_NAME = r"Local\torrentTOmagnet-context-batch"
CONTEXT_QUEUE_DIR_NAME = "torrentTOmagnet-context"
CONTEXT_QUIET_SECONDS = 0.45
CONTEXT_TIMEOUT_SECONDS = 2.0


def application_directory(
    *, is_frozen: bool, executable_path: Path, source_path: Path
) -> Path:
    return (executable_path if is_frozen else source_path).resolve().parent


def find_torrent_files(directory: Path) -> list[Path]:
    """返回目录第一层中的所有 .torrent 文件，名称匹配不区分大小写。"""
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.casefold() == ".torrent"
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )


def ensure_console() -> None:
    """按需连接或创建控制台。

    发布版使用 Windows GUI 子系统启动，这样 Explorer 为多选文件创建的辅助进程
    不会各自闪出控制台。只有最终负责处理整批文件的进程才会调用本函数。
    """
    if os.name != "nt":
        return

    kernel32 = ctypes.windll.kernel32
    if not kernel32.GetConsoleWindow():
        attach_parent_process = 0xFFFFFFFF
        if not kernel32.AttachConsole(attach_parent_process):
            if not kernel32.AllocConsole():
                raise OSError("无法创建控制台")

    kernel32.SetConsoleCP(65001)
    kernel32.SetConsoleOutputCP(65001)
    sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
    sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
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


def context_menu_icon(executable_path: str) -> str:
    """返回 Explorer 右键菜单使用的 EXE 图标路径。"""
    return os.path.abspath(executable_path)


def notify_shell_association_changed() -> None:
    """通知 Explorer 文件关联已改变，避免继续使用旧菜单缓存。"""
    if os.name != "nt":
        return
    shcne_assocchanged = 0x08000000
    shcnf_idlist = 0x0000
    ctypes.windll.shell32.SHChangeNotify(
        shcne_assocchanged, shcnf_idlist, None, None
    )


def add_context_menu(executable_path: str) -> None:
    if winreg is None:
        raise RuntimeError("右键菜单仅支持 Windows")

    executable_path = os.path.abspath(executable_path)
    command = f'"{executable_path}" --context "%1"'
    icon = context_menu_icon(executable_path)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, MENU_LABEL)
        winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, MENU_LABEL)
        winreg.SetValueEx(key, "NeverDefault", 0, winreg.REG_SZ, "")
        winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY + r"\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

    notify_shell_association_changed()
    print(f"已添加 .torrent 文件右键菜单“{MENU_LABEL}”（无需管理员权限）。")


def remove_context_menu() -> None:
    if winreg is None:
        raise RuntimeError("右键菜单仅支持 Windows")
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY + r"\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
        notify_shell_association_changed()
        print(f"已删除右键菜单“{MENU_LABEL}”。")
    except FileNotFoundError:
        print("右键菜单尚未安装。")


def context_queue_directory() -> Path:
    return Path(tempfile.gettempdir()) / CONTEXT_QUEUE_DIR_NAME


def enqueue_context_paths(paths: list[str], queue_dir: Path | None = None) -> Path:
    """把本次 Explorer 调用收到的文件路径原子写入临时队列。"""
    queue_dir = queue_dir or context_queue_directory()
    queue_dir.mkdir(parents=True, exist_ok=True)
    normalized = [os.path.abspath(path) for path in paths]
    token = f"{time.time_ns()}-{uuid.uuid4().hex}"
    temp_path = queue_dir / f".{token}.tmp"
    final_path = queue_dir / f"{token}.json"
    payload = {"created": time.time(), "paths": normalized}
    temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temp_path, final_path)
    return final_path


def collect_queued_context_paths(
    queue_dir: Path | None = None, *, stale_after: float = 30.0
) -> list[str]:
    """取出当前批次队列中的路径，并清理残留项。"""
    queue_dir = queue_dir or context_queue_directory()
    if not queue_dir.exists():
        return []

    now = time.time()
    paths: list[str] = []
    seen: set[str] = set()
    for item in sorted(queue_dir.glob("*.json"), key=lambda path: path.name):
        try:
            if now - item.stat().st_mtime > stale_after:
                continue
            payload = json.loads(item.read_text(encoding="utf-8"))
            for raw_path in payload.get("paths", []):
                if not isinstance(raw_path, str):
                    continue
                path = os.path.abspath(raw_path)
                key = os.path.normcase(path)
                if key not in seen:
                    seen.add(key)
                    paths.append(path)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        finally:
            try:
                item.unlink()
            except OSError:
                pass
    return paths


def wait_for_context_batch(
    queue_dir: Path | None = None,
    *,
    quiet_seconds: float = CONTEXT_QUIET_SECONDS,
    timeout_seconds: float = CONTEXT_TIMEOUT_SECONDS,
) -> list[str]:
    """等待 Explorer 把同一次多选产生的调用全部送入队列。"""
    queue_dir = queue_dir or context_queue_directory()
    deadline = time.monotonic() + timeout_seconds
    last_snapshot: tuple[str, ...] | None = None
    quiet_since = time.monotonic()

    while time.monotonic() < deadline:
        snapshot = tuple(sorted(path.name for path in queue_dir.glob("*.json")))
        now = time.monotonic()
        if snapshot != last_snapshot:
            last_snapshot = snapshot
            quiet_since = now
        elif now - quiet_since >= quiet_seconds:
            break
        time.sleep(0.05)

    return collect_queued_context_paths(queue_dir)


def acquire_context_batch_mutex():
    """只有一个 Explorer 调用负责最终汇总并打开处理窗口。"""
    if os.name != "nt":
        return None, True

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, CONTEXT_MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    error_already_exists = 183
    if ctypes.get_last_error() == error_already_exists:
        kernel32.CloseHandle(handle)
        return None, False
    return (kernel32, handle), True


def release_context_batch_mutex(mutex) -> None:
    if mutex is None:
        return
    kernel32, handle = mutex
    kernel32.ReleaseMutex(handle)
    kernel32.CloseHandle(handle)


def run_context_selection(paths: list[str]) -> int:
    """把 Explorer 的多进程逐文件调用合并为一次批量处理。"""
    if not paths:
        return 0

    queue_dir = context_queue_directory()
    enqueue_context_paths(paths, queue_dir)
    mutex, is_leader = acquire_context_batch_mutex()
    if not is_leader:
        return 0

    try:
        batch = wait_for_context_batch(queue_dir)
    finally:
        release_context_batch_mutex(mutex)

    if not batch:
        return 0

    ensure_console()
    configure_console()
    return process_files(batch)


def run_smoke_test(arguments: list[str]) -> int:
    """供 GitHub Actions 验证 windowed EXE 的核心转换逻辑。"""
    if len(arguments) != 2:
        return 2
    try:
        magnet = torrent_to_magnet(arguments[0])
        Path(arguments[1]).write_text(magnet, encoding="utf-8")
    except (TorrentError, OSError):
        return 1
    return 0


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


def process_torrents_in_directory(directory: Path, pause: bool = True) -> int | None:
    torrent_files = find_torrent_files(directory)
    if not torrent_files:
        return None

    print(f"在程序目录中找到 {len(torrent_files)} 个种子文件，开始自动转换。\n")
    result = process_files([os.fspath(path) for path in torrent_files])
    if pause and result == 0:
        input("\n全部转换完成，按 Enter 键退出...")
    return result


def run(
    arguments: list[str],
    *,
    is_frozen: bool,
    executable_path: Path,
    source_path: Path,
    pause: bool = True,
) -> int | None:
    if arguments:
        return process_files(arguments)
    directory = application_directory(
        is_frozen=is_frozen,
        executable_path=executable_path,
        source_path=source_path,
    )
    return process_torrents_in_directory(directory, pause=pause)


def main() -> int:
    arguments = sys.argv[1:]

    if arguments[:1] == ["--smoke-test"]:
        return run_smoke_test(arguments[1:])

    if arguments[:1] == ["--context"]:
        try:
            return run_context_selection(arguments[1:])
        except Exception as exc:
            ensure_console()
            configure_console()
            print(f"右键批量处理失败：{exc}")
            input("按 Enter 键退出...")
            return 1

    ensure_console()
    configure_console()
    result = run(
        arguments,
        is_frozen=bool(getattr(sys, "frozen", False)),
        executable_path=Path(sys.executable),
        source_path=Path(__file__),
    )
    if result is not None:
        return result

    print("torrentTOmagnet 2.0.3 — 种子转磁力链接")
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