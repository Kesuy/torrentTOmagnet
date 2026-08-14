"""BitTorrent 元数据解析与 Magnet URI 生成。"""

from __future__ import annotations

import hashlib
import os
import unicodedata
from pathlib import Path
from urllib.parse import quote

MAX_TORRENT_SIZE = 64 * 1024 * 1024
MAX_BENCODE_DEPTH = 512


class TorrentError(ValueError):
    """种子文件无效或不受支持。"""


def _decode_bytes(data: bytes, offset: int) -> tuple[bytes, int]:
    colon = data.find(b":", offset)
    if colon < 0:
        raise TorrentError("Bencode 字符串缺少长度分隔符")
    length_raw = data[offset:colon]
    if not length_raw or not length_raw.isdigit():
        raise TorrentError("Bencode 字符串长度无效")
    if len(length_raw) > 1 and length_raw.startswith(b"0"):
        raise TorrentError("Bencode 字符串长度包含前导零")
    length = int(length_raw)
    start = colon + 1
    end = start + length
    if end > len(data):
        raise TorrentError("Bencode 字符串内容不完整")
    return data[start:end], end


def _decode_value(data: bytes, offset: int, depth: int = 0):
    if depth > MAX_BENCODE_DEPTH:
        raise TorrentError("Bencode 嵌套层级过深")
    if offset >= len(data):
        raise TorrentError("Bencode 数据意外结束")

    token = data[offset : offset + 1]
    if token == b"i":
        end = data.find(b"e", offset + 1)
        if end < 0:
            raise TorrentError("Bencode 整数缺少结束符")
        raw = data[offset + 1 : end]
        digits = raw[1:] if raw.startswith(b"-") else raw
        if (
            not digits
            or not digits.isdigit()
            or raw == b"-0"
            or (digits.startswith(b"0") and len(digits) > 1)
        ):
            raise TorrentError("Bencode 整数格式无效")
        try:
            return int(raw), end + 1
        except ValueError as exc:
            raise TorrentError("Bencode 整数格式无效") from exc
    if token == b"l":
        result = []
        offset += 1
        while offset < len(data) and data[offset : offset + 1] != b"e":
            value, offset = _decode_value(data, offset, depth + 1)
            result.append(value)
        if offset >= len(data):
            raise TorrentError("Bencode 列表缺少结束符")
        return result, offset + 1
    if token == b"d":
        result = {}
        offset += 1
        while offset < len(data) and data[offset : offset + 1] != b"e":
            key, offset = _decode_bytes(data, offset)
            value, offset = _decode_value(data, offset, depth + 1)
            result[key] = value
        if offset >= len(data):
            raise TorrentError("Bencode 字典缺少结束符")
        return result, offset + 1
    if token.isdigit():
        return _decode_bytes(data, offset)
    raise TorrentError(f"未知的 Bencode 标记: 0x{data[offset]:02x}")


def _decode_torrent(data: bytes) -> tuple[dict, bytes]:
    """解析顶层字典，并保留 info 字典的原始字节用于精确哈希。"""
    if not data.startswith(b"d"):
        raise TorrentError("种子文件顶层必须是 Bencode 字典")

    metadata: dict = {}
    info_bytes: bytes | None = None
    offset = 1
    while offset < len(data) and data[offset : offset + 1] != b"e":
        key, offset = _decode_bytes(data, offset)
        value_start = offset
        value, offset = _decode_value(data, offset, 1)
        if key == b"info":
            if info_bytes is not None:
                raise TorrentError("种子文件包含重复的 info 字典")
            if not isinstance(value, dict):
                raise TorrentError("info 字段不是字典")
            info_bytes = data[value_start:offset]
        metadata[key] = value

    if offset >= len(data) or data[offset : offset + 1] != b"e":
        raise TorrentError("种子文件顶层字典缺少结束符")
    if offset + 1 != len(data):
        raise TorrentError("种子文件末尾包含多余数据")
    if info_bytes is None:
        raise TorrentError("种子文件缺少 info 字典")
    return metadata, info_bytes


def _decode_text(value, encoding_hint: str | None = None) -> str | None:
    if not isinstance(value, bytes):
        return None

    encodings = ["utf-8"]
    if encoding_hint:
        encodings.append(encoding_hint)
    encodings.extend(("gb18030", "big5", "shift_jis", "cp1252", "latin-1"))

    seen: set[str] = set()
    for encoding in encodings:
        normalized = encoding.lower().replace("_", "-")
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return unicodedata.normalize("NFC", value.decode(encoding))
        except (LookupError, UnicodeDecodeError):
            continue
    return None


def _encoding_hint(metadata: dict) -> str | None:
    raw = metadata.get(b"encoding")
    if not isinstance(raw, bytes):
        return None
    try:
        return raw.decode("ascii").strip() or None
    except UnicodeDecodeError:
        return None


def _display_name(metadata: dict, fallback_name: str) -> str:
    info = metadata[b"info"]
    hint = _encoding_hint(metadata)
    for key in (b"name.utf-8", b"name"):
        decoded = _decode_text(info.get(key), "utf-8" if key.endswith(b".utf-8") else hint)
        if decoded:
            return decoded
    return fallback_name


def _trackers(metadata: dict) -> list[str]:
    values = []
    announce_list = metadata.get(b"announce-list")
    if isinstance(announce_list, list):
        for tier in announce_list:
            if isinstance(tier, list):
                values.extend(tier)
            else:
                values.append(tier)
    values.append(metadata.get(b"announce"))

    result = []
    seen = set()
    hint = _encoding_hint(metadata)
    for value in values:
        tracker = _decode_text(value, hint)
        if tracker and tracker not in seen:
            seen.add(tracker)
            result.append(tracker)
    return result


def torrent_bytes_to_magnet(data: bytes, fallback_name: str = "未命名种子") -> str:
    """将 .torrent 原始字节转换为正确转义的 Magnet URI。"""
    metadata, info_bytes = _decode_torrent(data)
    info = metadata[b"info"]
    is_v2 = info.get(b"meta version") == 2
    is_hybrid = is_v2 and b"pieces" in info

    params: list[tuple[str, str]] = []
    if not is_v2 or is_hybrid:
        params.append(("xt", f"urn:btih:{hashlib.sha1(info_bytes).hexdigest()}"))
    if is_v2:
        digest = hashlib.sha256(info_bytes).hexdigest()
        params.append(("xt", f"urn:btmh:1220{digest}"))

    params.append(("dn", _display_name(metadata, fallback_name)))
    params.extend(("tr", tracker) for tracker in _trackers(metadata))
    return "magnet:?" + "&".join(
        f"{key}={quote(value, safe=':')}" for key, value in params
    )


def torrent_to_magnet(torrent_file: str | os.PathLike[str]) -> str:
    path = Path(torrent_file)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise TorrentError(f"无法读取文件: {exc}") from exc
    if size > MAX_TORRENT_SIZE:
        raise TorrentError(f"种子文件过大（上限 {MAX_TORRENT_SIZE // 1024 // 1024} MiB）")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TorrentError(f"无法读取文件: {exc}") from exc
    return torrent_bytes_to_magnet(data, fallback_name=path.stem)
