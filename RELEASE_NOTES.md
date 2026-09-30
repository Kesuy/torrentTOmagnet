# v2.0.4

## 主要更新

- 兼容顶层 Bencode 结束后带 ASCII 空白字符的 `.torrent` 文件，包括空格、Tab、CR、LF、VT、FF。
- 修复部分种子末尾带真实 CRLF（`0D 0A`）时误报“种子文件末尾包含多余数据”、无法转换磁力链接的问题。
- 仍严格拒绝非空白尾随数据，避免把真正损坏或拼接额外数据的种子静默接受。
- 保持 `info` 字典原始字节不变，不影响 BTIH / BTMH 哈希计算。
- 新增真实 CR/LF 尾随数据回归测试，以及非空白尾随数据拒绝测试。
- 已通过 Windows PyInstaller 打包后的 EXE 级 CRLF torrent smoke test。
