# Rem Downloader

基于 yt-dlp 和 FFmpeg 的中文终端下载工具，提供固定屏幕界面、视频及音频下载、格式查询、按格式 ID 下载和 Bilibili 弹幕 ASS 导出。

## 安装与启动

1. 双击 install_dependencies.cmd，联网检测并安装缺失依赖。
2. 双击 run.cmd 启动。

Windows 需提供 PowerShell。系统依赖安装使用 winget，未安装时请从 Microsoft Store 安装或更新“应用安装程序”。安装可能出现系统权限提示。已可用依赖不会强制更新。

安装器检测 Python 3.10+、yt-dlp、FFmpeg、Node.js、Playwright 及 Chrome/Edge，启动器使用安装时选择的 Python。界面本身仅依赖 Python 标准库。

创建桌面快捷方式可运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\create_shortcut.ps1
```