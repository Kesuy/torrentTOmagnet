# v2.0.2

## 主要更新

- 修复右键菜单图标在部分 Windows 11 / Explorer 环境中不显示的问题：`Icon` 现在直接指向 EXE 文件，不再使用带引号的资源索引字符串。
- 新增 `MultiSelectModel=Player`，选择多个 `.torrent` 文件时仍显示“种子转磁力链接”右键菜单。
- 保留 `MUIVerb` 与 `NeverDefault`，继续避免菜单文字退化成“打开 .torrent 文件”以及被误设为默认打开动作。
- 增加右键菜单图标和多选注册项的自动化回归测试。
