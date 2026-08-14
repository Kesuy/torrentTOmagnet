# v2.0.0

## 主要更新

- 修复种子名称中的 `&`、`#`、`+`、`%`、`?`、`=`、空格、斜杠、中文及 Emoji 会破坏磁力链接的问题。
- 支持 `name.utf-8` 及 UTF-8、GB18030/GBK、Big5、Shift-JIS、Windows-1252 名称编码。
- 直接对种子内原始 `info` 字典计算哈希，避免重编码造成错误 info hash。
- 新增 BitTorrent v2（BTMH）及 hybrid 混合种子支持。
- 磁力链接中自动包含并正确转义 Tracker。
- 支持 Unicode/特殊字符文件路径与一次拖入多个种子。
- 直接运行 EXE 时，自动搜索并转换 EXE 所在目录第一层的全部 `.torrent` 文件。
- 改用 Windows 原生 Unicode 剪贴板，不再需要 `bencodepy`、`pyperclip` 等运行依赖。
- 右键菜单仅作用于 `.torrent` 文件，并改为当前用户安装，无需管理员权限。
- 加入 12 项自动化回归测试与 GitHub Actions Windows EXE 构建。
