# Rem Downloader

基于 yt-dlp 的中文终端下载器，采用雷姆主题真彩色字符画和固定屏幕 TUI。菜单、下载进度和设置原地刷新；退出时恢复终端状态。

## 运行

需要 Python 3.10+ 和已安装的 yt-dlp。合并独立音视频及音频转码还需要 FFmpeg，并将其加入 PATH。

```powershell
python -m pip install yt-dlp
python download_cli.py
```

Windows 下也可双击 `run.cmd`。推荐使用 Windows Terminal 和支持中文及四分格字符的等宽字体；宽窗口会显示右侧仪表盘。

创建带专属图标的桌面快捷方式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\create_shortcut.ps1
```

图标保存在 `assets/rem-downloader.ico`，包含多种尺寸；PNG 原图也包含在项目内。移动项目后请重新运行脚本以更新快捷方式。

## 功能

- 下载视频、音频，查看格式或按格式 ID 下载。
- 指定画质严格匹配，最高可用模式自动选择最佳格式。
- 实时进度、历史记录、Cookies 和 FFmpeg 路径设置。
- Alternate Screen Buffer，原地更新，支持 Ctrl+C 取消和断点续传。

详细操作见 [使用说明](使用说明.md)。正常运行只使用 Python 标准库，头像数据已包含在 `rem_portrait_rgb.json` 中，不需要原始图片或 Pillow。

## 开发检查

```powershell
python -m unittest test_cli test_screen
python download_cli.py --check
```

可选的 `preview_theme.py` 用于生成离线预览，需要 Pillow。

## 上传内容

`.gitignore` 排除了 Cookies、设置、下载视频、历史、日志、缓存和临时预览。`yt-dlp-master` 为可选的本地源码后端，不随本项目上传；默认使用已安装的 yt-dlp。

角色图像为主题素材；本项目与原作及 yt-dlp 项目没有官方关联。
