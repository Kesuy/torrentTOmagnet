# torrentTOmagnet

一个无需安装、无需第三方运行库的 Windows `.torrent` 转 Magnet URI 小工具。

> 本项目从原始归档中的 1.0.0 版本继续改进；原始归档署名为 `www.xshare.cc`。

## 功能

- 把一个或多个 `.torrent` 文件拖到 EXE 上，自动生成磁力链接并复制到剪贴板
- 直接双击 EXE 时，自动转换 EXE 所在目录第一层的全部 `.torrent` 文件
- 可为 `.torrent` 文件安装右键菜单，无需管理员权限
- 正确转义 `&`、`#`、`+`、`%`、`?`、`=`、空格、斜杠、中文及 Emoji 等字符
- 优先读取 `name.utf-8`，并兼容 UTF-8、GB18030/GBK、Big5、Shift-JIS、Windows-1252 等名称编码
- 直接使用原始 `info` 字典字节计算哈希，避免重新编码导致错误的 info hash
- 支持 BitTorrent v1、v2（BTMH）和 hybrid 混合种子
- 自动附带并正确转义种子中的 Tracker 地址
- 纯 Python 标准库实现，发布版为单文件 Windows EXE

## 使用方法

1. 从 [Releases](https://github.com/Kesuy/torrentTOmagnet/releases/latest) 下载 `torrentTOmagnet-windows-x64.exe`。
2. 把 EXE 放进保存种子文件的目录后直接双击；程序会自动搜索并转换该目录第一层的全部 `.torrent` 文件。
3. 也可以把一个或多个 `.torrent` 文件拖到 EXE 图标上，只转换指定文件。
4. 转换完成后，磁力链接会显示在窗口中并自动复制到剪贴板。

如果 EXE 目录中没有种子文件，双击后会显示安装或删除 `.torrent` 文件右键菜单的选项。

## 从源码运行

需要 Python 3.10 或更高版本，无第三方运行依赖：

```bash
python tt.py "示例 & 特殊字符.torrent"
```

运行测试：

```bash
python -m unittest discover -v
```

构建 Windows EXE：

```powershell
py -m pip install "pyinstaller>=6.15,<7"
pyinstaller --clean --noconfirm tt.spec
```

输出文件位于 `dist/torrentTOmagnet.exe`。
