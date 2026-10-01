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

设置的下载路径作为根目录。视频和音频完成合并或转码后，按最终扩展名归入 `MP4`、`WEBM`、`MP3`、`M4A` 等子目录；弹幕仅保存到 `ASS`。旧下载文件不会自动迁移。

- 下载视频、音频，查看格式或按格式 ID 下载。
- 指定画质严格匹配，最高可用模式自动选择最佳格式。
- 实时进度、历史记录、Cookies 和 FFmpeg 路径设置。
- B站分段弹幕下载，仅导出 PotPlayer 可加载的滚动 ASS。
- Alternate Screen Buffer，原地更新，支持 Ctrl+C 取消和断点续传。

详细操作见 [使用说明](使用说明.md)。正常运行只使用 Python 标准库，头像数据已包含在 `rem_portrait_rgb.json` 中，不需要原始图片或 Pillow。

## 开发检查

```powershell
python -m unittest test_cli test_screen test_danmaku
python download_cli.py --check
```

可选的 `preview_theme.py` 用于生成离线预览，需要 Pillow。

## 上传内容

`.gitignore` 排除了 Cookies、设置、下载视频、历史、日志、缓存和临时预览。`yt-dlp-master` 为可选的本地源码后端，不随本项目上传；默认使用已安装的 yt-dlp。

角色图像为主题素材；本项目与原作及 yt-dlp 项目没有官方关联。

## B站弹幕

主菜单选择 **09 下载B站弹幕**，粘贴 BV/av 视频链接（支持 b23.tv 短链接）。多分P视频可选择一个分P，按该分P的全时长逐段获取当前接口可见弹幕；遇到失败不会把未完成结果标记为成功。不能保证包含所有历史、已删除弹幕或平台未返回的弹幕。

不做去重、不限制条数、不进行内容过滤。密集弹幕允许重叠；字号、不透明度和显示时间可自定义。普通滚动、反向滚动、顶部和底部弹幕使用对应 ASS 动画；高级、代码及其他特殊弹幕降级为普通滚动文本，不能还原其全部特效。

Cookies 按网址自动选择：YouTube 使用 `cookies.txt`，B站（含 b23.tv）使用 `B_cookies.txt`，其他网站不使用这两份凭据。设置中可分别修改或清空 YouTube 与 B站 Cookies 路径；视频、音频、格式查询和弹幕使用相同规则。页面弹幕统计与接口实际返回数量可能不同，导出文件保留本次接口返回的全部条目。

将下载目录 `ASS` 文件夹中的 `.ass` 拖入 PotPlayer，启用 ASS/SSA 动画并使用字幕定义的原始样式。不会保存 XML 或原始分段文件。B站风控拒绝请求时可稍后重试，或在设置中配置有效的 Netscape 格式 Cookies；这些文件不会上传 GitHub。
