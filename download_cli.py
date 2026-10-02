from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tempfile
import re
import platform
import getpass
from rem_screen import Canvas
from rem_dashboard import layout, terminal_columns, quality_line
from datetime import datetime
from urllib.parse import urlparse
from rem_ui import UI, shorten

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'download_settings.json'
HISTORY = ROOT / 'download_history.json'
CURRENT_TASK = {}
SYSTEM_CACHE = {}
DEFAULTS = {
    'output': str(ROOT / 'downloads'),
    'cookies': str(ROOT / 'Cookies' / 'youtube_cookies.txt'),
    'bilibili_cookies': str(ROOT / 'Cookies' / 'bilibili_cookies.txt'),
    'backend': 'installed',
    'ffmpeg': '',
    'character': 'on',
    'command': 'off',
}


def load_settings():
    try:
        values = json.loads(SETTINGS.read_text(encoding='utf-8'))
        if not isinstance(values, dict):
            raise ValueError('配置必须是对象')
        for key, old_name, new_name in (('cookies', 'cookies.txt', 'youtube_cookies.txt'),
                                       ('bilibili_cookies', 'B_cookies.txt', 'bilibili_cookies.txt')):
            previous = values.get(key)
            target = ROOT / 'Cookies' / new_name
            if isinstance(previous, str) and previous and target.is_file():
                if Path(previous).resolve() == (ROOT / old_name).resolve():
                    values[key] = str(target)
        return {key: values.get(key, value) if isinstance(values.get(key, value), str)
                else value for key, value in DEFAULTS.items()}
    except FileNotFoundError:
        return DEFAULTS.copy()
    except (OSError, ValueError) as exc:
        print(f'配置读取失败，使用默认设置：{exc}')
        return DEFAULTS.copy()


def save_settings(settings):
    temporary = SETTINGS.with_suffix('.tmp')
    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(SETTINGS)


def choose(prompt, choices, default=None):
    while True:
        answer = UI.ask(prompt).strip() or default
        if answer and answer.isdigit():
            answer = str(int(answer))
        if answer in choices:
            return answer
        UI.note('请输入菜单中列出的编号。', 'yellow')


def url_input():
    while True:
        value = UI.ask('视频网址（留空返回）').strip()
        if not value:
            return None
        
        if value.startswith('[') and '](' in value and value.endswith(')'):
            value = value.split('](', 1)[1][:-1]
        value = value.strip('"\'')
        parsed = urlparse(value)
        if parsed.scheme in ('http', 'https') and parsed.netloc:
            return value
        print('请输入完整的 http:// 或 https:// 网址。')


def backend_command(settings):
    if settings['backend'] == 'source':
        entry = ROOT / 'yt-dlp-master' / 'yt_dlp' / '__main__.py'
        if not entry.is_file():
            raise ValueError(f'未找到本地源码入口：{entry}')
        return [sys.executable, str(entry)]
    executable = shutil.which('yt-dlp')
    if not executable:
        raise ValueError('PATH 中未找到 yt-dlp，请在设置中切换到本地源码模式。')
    return [executable]


def ffmpeg_available(settings):
    location = settings['ffmpeg']
    if location:
        path = Path(location).expanduser()
        return (path / 'ffmpeg.exe').is_file() if path.is_dir() else path.is_file()
    return bool(shutil.which('ffmpeg'))


def cookies_for_url(settings, url):
    host = (urlparse(url).hostname or '').lower()
    if host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com'):
        return settings.get('cookies', '')
    if host in ('bilibili.com', 'b23.tv') or host.endswith('.bilibili.com'):
        return settings.get('bilibili_cookies', DEFAULTS['bilibili_cookies'])
    if host == 'douyin.com' or host.endswith('.douyin.com'):
        return str(ROOT / 'Cookies' / 'douyin_cookies.txt')
    try:
        platforms = json.loads((ROOT / 'cookie_platforms.json').read_text(encoding='utf-8'))
        for entry in platforms:
            if re.match(entry['pattern'], url):
                name = entry['platform']
                if re.fullmatch(r'[a-z0-9_]+', name):
                    return str(ROOT / 'Cookies' / f'{name}_cookies.txt')
    except (OSError, ValueError, KeyError, re.error):
        pass
    return ''


def common_args(settings, url=''):
    args = ['--no-playlist', '--encoding', 'utf-8', '--no-cookies', '--no-cookies-from-browser']
    cookie = cookies_for_url(settings, url)
    if cookie_available(cookie):
        args.remove('--no-cookies')
        args += ['--cookies', cookie]
    if settings['ffmpeg']:
        args += ['--ffmpeg-location', settings['ffmpeg']]
    return args


def cookie_available(path):
    try:
        content = Path(path).read_text(encoding='utf-8-sig', errors='replace') if path else ''
        return any(line.strip() and (not line.startswith('#') or line.startswith('#HttpOnly_'))
                   for line in content.splitlines())
    except OSError:
        return False


def prepare_cookie_files():
    folder = ROOT / 'Cookies'
    folder.mkdir(exist_ok=True)
    platforms = json.loads((ROOT / 'cookie_platforms.json').read_text(encoding='utf-8'))
    for name in {entry['platform'] for entry in platforms}:
        if re.fullmatch(r'[a-z0-9_]+', name):
            path = folder / f'{name}_cookies.txt'
            if not path.exists():
                path.touch()


def video_format(height, merge):
    limit = f'[height={height}]' if height else ''
    return f'bv{limit}+ba/b{limit}' if merge else f'b{limit}'


def build_command(settings, url, options, download=True):
    command = backend_command(settings) + common_args(settings, url)
    host = (urlparse(url).hostname or '').lower()
    if host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com'):
        command += ['--no-plugin-dirs', '--extractor-args', 'youtube:player_client=default,web_safari']
        node = shutil.which('node')
        if node:
            command += ['--no-js-runtimes', '--js-runtimes', f'node:{node}']
        if download:
            command += ['--http-chunk-size', '1M']
    if download:
        command += ['--concurrent-fragments', '4', '--socket-timeout', '20',
                    '--retries', '5', '--fragment-retries', '5',
                    '--newline', '--progress', '-P', settings['output'],
                    '-o', '%(title)s [%(id)s] [%(height|audio)s].%(ext)s',
                    '--print', 'before_dl:REM_META:{"title":%(title)j,"resolution":%(resolution)j,"format":%(format)j,"vcodec":%(vcodec)j,"acodec":%(acodec)j}',
                    '--print', 'after_move:REM_FILE:%(filepath)j',
                    '--progress-template', 'download:REM_PROGRESS:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s|%(progress._total_bytes_str)s|%(progress._downloaded_bytes_str)s']
    return command + options + ['--', url]


def read_history():
    try:
        data = json.loads(HISTORY.read_text(encoding='utf-8'))
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def record_task(metadata, path, code, elapsed):
    rows = read_history()
    rows.append({'time': datetime.now().isoformat(timespec='seconds'),
                 'title': metadata.get('title', Path(path).name if path else '下载任务'),
                 'resolution': metadata.get('resolution', '未知'), 'path': path,
                 'status': '完成' if code == 0 else '取消' if code == 130 else '失败',
                 'elapsed': round(elapsed, 1)})
    tmp = HISTORY.with_suffix('.tmp')
    tmp.write_text(json.dumps(rows[-200:], ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(HISTORY)


def failure_advice(log):
    if 'bgutil' in log or '4416' in log:
        return '本地 PO Token 插件服务不可用；请重启使用新版程序，YouTube 下载已隔离第三方插件。'
    if 'ffmpeg' in log.lower() and ('not found' in log.lower() or 'not installed' in log.lower()):
        return '音频转码需要 FFmpeg，请在设置中配置有效路径，或选择最佳原始音频。'
    if 'Requested format is not available' in log:
        return '未获取到指定清晰度；查看可用格式后重选，程序不会自动降级。'
    if 'not a bot' in log or 'Sign in' in log:
        return 'YouTube 要求登录验证，请检查 Cookies 文件是否有效。'
    if '403' in log:
        return '服务器拒绝访问；检查 Cookies 和 yt-dlp 版本后重试。'
    if 'timed out' in log or 'Unable to download' in log:
        return '检查网络连接后重试，已有分片会保留用于续传。'
    return '查看上方错误详情，检查网络、Cookies 与 FFmpeg 配置。'


def query_formats(command):
    query = [arg for arg in command if arg != '-F']
    position = query.index('--')
    query[position:position] = ['--dump-single-json', '--quiet']
    sys.stdout.flush()
    for attempt in range(2):
        try:
            result = subprocess.run(query, capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            UI.result(False, ['格式查询失败或超时，请稍后重试。'])
            return None
        if result.returncode == 0:
            break
        if attempt or '--cookies' not in query:
            UI.result(False, [shorten(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else '格式查询失败', 76)])
            return None
        index = query.index('--cookies')
        del query[index:index + 2]
        position = query.index('--')
        query[position:position] = ['--no-cookies']
    try:
        data = json.loads(result.stdout)
    except ValueError:
        UI.result(False, ['下载器未返回有效的格式数据。'])
        return None
    return data


def show_formats(command):
    UI.header('Formats', '正在查询可用格式', character=False)
    UI.box('格式查询', ['正在解析视频，请稍候…'])
    data = query_formats(command)
    if data is None:
        return 1
    formats = [f for f in data.get('formats', []) if f.get('ext') != 'mhtml']
    page = 0
    pages = max(1, (len(formats) + 9) // 10)
    while True:
        UI.header('Formats', '可用格式 / ' + shorten(data.get('title', ''), 55), character=False)
        lines = ['ID          格式  分辨率 / 帧率 / 编码']
        for f in formats[page * 10:(page + 1) * 10]:
            resolution = '仅音频' if f.get('vcodec') == 'none' else f.get('resolution', '未知')
            codec = f.get('acodec') if f.get('vcodec') == 'none' else f.get('vcodec')
            lines.append(f'{f.get("format_id", "?"):<11} {f.get("ext", "?"):<5} {resolution}  {f.get("fps") or "—"}fps  {codec or "—"}')
        UI.box(f'可用格式 [{page + 1}/{pages}]', lines, width=84)
        if not sys.stdin.isatty():
            return 0
        action = choose('1 下一页 / 2 上一页 / 0 返回', {'0', '1', '2'}, '0')
        if action == '0':
            return 0
        page = (page + (1 if action == '1' else -1)) % pages


def run_command(command, browser_retry=False, cookie_retry=False):
    if '-F' in command:
        return show_formats(command)
    def refresh_download():
        from rem_screen import ACTIVE_SCREEN
        if not ACTIVE_SCREEN:
            return
        UI.header('Downloading', 'レムがダウンロード中… / 正在下载')
        UI.box('↓ Downloading / 下载任务', [
            f'任务名称 : {CURRENT_TASK.get("title", "正在解析视频信息…")}',
            quality_line(CURRENT_TASK),
            f'格式     : {CURRENT_TASK.get("format", "—")}',
            ('Ctrl+C 取消 · 支持断点续传', 'muted')], width=84)
        if CURRENT_TASK.get('notice'):
            UI.note(shorten(CURRENT_TASK['notice'], 76), 'muted')
        ACTIVE_SCREEN.flush()
    downloading = any('REM_FILE:' in arg for arg in command)
    if load_settings()['command'] == 'on':
        UI.box('Command / 执行命令', [subprocess.list2cmdline(command)])
    if downloading:
        CURRENT_TASK.clear()
        CURRENT_TASK.update(status='解析中', title='正在获取视频信息…', percent=0)
        UI.header('Downloading', 'レムがダウンロード中… / 正在获取视频信息')
        UI.note('正在解析视频与可用格式，请稍候…')
    started = time.monotonic()
    metadata, saved, logs = {}, '', []
    process = None
    last_progress = 0.0
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace')
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue
            if line.startswith('REM_META:'):
                try:
                    metadata = json.loads(line.split(':', 1)[1])
                    CURRENT_TASK.update(metadata, status='下载中')
                    from rem_screen import ACTIVE_SCREEN
                    if ACTIVE_SCREEN:
                        refresh_download()
                        continue
                    UI.box('↓  Downloading / 下载任务', [
                        f'任务名称 : {metadata.get("title", "未知")}',
                        quality_line(metadata),
                        f'视频编码 : {metadata.get("vcodec", "未知")}',
                        f'音频编码 : {metadata.get("acodec", "未知")}',
                        f'格式     : {metadata.get("format", "未知")}',
                        ('Ctrl+C 取消 · 支持断点续传', 'muted')])
                except (ValueError, AttributeError):
                    UI.note(line, 'yellow')
            elif line.startswith('REM_FILE:'):
                try:
                    saved = json.loads(line.split(':', 1)[1])
                except ValueError:
                    saved = line.split(':', 1)[1]
                source = Path(saved)
                if source.is_file() and '-P' in command:
                    root = Path(command[command.index('-P') + 1]).expanduser().resolve()
                    if source.resolve().is_relative_to(root):
                        folder = root / (source.suffix[1:].upper() or 'OTHER')
                        folder.mkdir(parents=True, exist_ok=True)
                        target = folder / source.name
                        if source.resolve() != target.resolve():
                            number = 2
                            while target.exists():
                                target = folder / f'{source.stem} ({number}){source.suffix}'
                                number += 1
                            shutil.move(str(source), str(target))
                        saved = str(target)
                CURRENT_TASK['path'] = saved
            elif line.startswith('REM_PROGRESS:'):
                values = line.split(':', 1)[1].split('|')
                match = re.search(r'(\d+(?:\.\d+)?)%', values[0])
                now = time.monotonic()
                if match and (now - last_progress > 0.12 or float(match[1]) >= 100):
                    padded = values[1:] + ['', '', '']
                    CURRENT_TASK.update(percent=float(match[1]), speed=padded[0], eta=padded[1], total=padded[2])
                    if len(values) > 4:
                        CURRENT_TASK['downloaded'] = values[4]
                    from rem_screen import ACTIVE_SCREEN
                    if ACTIVE_SCREEN:
                        refresh_download()
                        last_progress = now
                        continue
                    if UI.interactive and UI.color and terminal_columns() >= 166:
                        if now - last_progress >= 0.5 or float(match[1]) >= 100:
                            main_menu(load_settings())
                            UI.note('下载中 · Ctrl+C 取消', 'blue')
                            last_progress = now
                    else:
                        UI.progress(float(match[1]), *padded[:3])
                        last_progress = now
            else:
                logs.append(line)
                if downloading:
                    CURRENT_TASK['notice'] = line
                logs = logs[-30:]
                if downloading:
                    from rem_screen import ACTIVE_SCREEN
                    if ACTIVE_SCREEN:
                        refresh_download()
                    else:
                        print()
                        UI.note(shorten(line, UI.width - 5), 'yellow' if line.startswith('WARNING') else 'muted')
                else:
                    print(line)
        code = process.wait()
    except KeyboardInterrupt:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        code = 130
        logs.append('已取消；保留的 .part 文件可在下次下载时续传。')
    except OSError as exc:
        code = 1
        logs.append(f'无法启动下载器：{exc}')
    elapsed = time.monotonic() - started
    if code not in (0, 130) and '--cookies' in command and not saved and not cookie_retry:
        UI.note('Cookie 尝试失败，改用无 Cookie 重试一次。', 'yellow')
        retry = list(command)
        index = retry.index('--cookies')
        del retry[index:index + 2]
        position = retry.index('--') if '--' in retry else len(retry) - 1
        retry[position:position] = ['--no-cookies']
        return run_command(retry, browser_retry=browser_retry, cookie_retry=True)
    if downloading and code not in (0, 130) and not saved and not browser_retry:
        from douyin_browser import douyin_url, media_command
        if douyin_url(command[-1]):
            CURRENT_TASK.update(status='解析中', notice='请在浏览器完成验证并播放视频')
            UI.header('Douyin Browser', '浏览器播放获取地址 / 抖音下载兜底')
            UI.box('浏览器验证', ['请完成登录或验证码，并播放目标视频。',
                                    '获取地址后自动继续下载；Ctrl+C 可取消。'])
            UI.note('普通下载失败，打开抖音浏览器。请完成登录/验证码并播放视频，最长等待 3 分钟。', 'yellow')
            sys.stdout.flush()
            worker = None
            try:
                worker = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'douyin_browser.py'), command[-1]],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True, encoding='utf-8', errors='replace')
                result, _ = worker.communicate(timeout=240)
                media = json.loads(result)
                if worker.returncode or media.get('error'):
                    raise ValueError(media.get('error', '浏览器未能获取视频'))
                return run_command(media_command(command, media), browser_retry=True)
            except KeyboardInterrupt:
                if worker is not None:
                    worker.kill()
                    worker.communicate()
                code = 130
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                if worker is not None and worker.poll() is None:
                    worker.kill()
                    worker.communicate()
                logs.append('浏览器兜底失败：' + str(exc))
    if downloading:
        CURRENT_TASK.update(status='完成' if code == 0 else '已取消' if code == 130 else '失败',
                            path=saved or load_settings()['output'])
        if code == 0:
            CURRENT_TASK.update(percent=100, speed='—', eta='—', notice='')
            if saved and Path(saved).is_file():
                size_label = f'{Path(saved).stat().st_size / (1024 * 1024):.2f} MiB'
                CURRENT_TASK.update(downloaded=size_label, total=size_label)
        from rem_screen import ACTIVE_SCREEN
        if ACTIVE_SCREEN:
            UI.header('Completed' if code == 0 else 'Task Failed', '下载完成' if code == 0 else '任务未完成 / 检查错误详情')
        if code == 0:
            size = ''
            if saved and Path(saved).is_file():
                size = f'{Path(saved).stat().st_size / (1024 * 1024):.2f} MiB'
            UI.result(True, [f'文件名   : {Path(saved).name if saved else "已保存"}',
                             quality_line(metadata),
                             f'文件大小 : {size or "未知"}', f'任务耗时 : {elapsed:.1f} 秒',
                             f'保存路径 : {saved}', ('[Enter] 返回菜单', 'cyan')])
        else:
            errors = [line for line in logs if 'ERROR' in line]
            log_path = ROOT / 'last_download_error.log'
            try:
                log_path.write_text('\n'.join(logs), encoding='utf-8')
            except OSError:
                log_path = None
            UI.result(False, [f'返回码 : {code}',
                              f'原因   : {(errors or logs or ["未知错误"])[-1]}',
                              ('建议   : ' + failure_advice('\n'.join(logs)), 'yellow'),
                              f'完整详情 : {log_path or "请查看终端输出"}',
                              ('[R] 重试    [B / Enter] 返回', 'cyan')])
        try:
            record_task(metadata, saved, code, elapsed)
        except OSError as exc:
            UI.note(f'历史记录保存失败：{exc}', 'yellow')
        if sys.stdin.isatty():
            action = UI.ask('Enter 返回 / R 重试' if code else 'Enter 返回 / O 打开文件夹').strip().lower()
            if action == 'r' and code:
                return run_command(command)
            if action == 'o' and saved and os.name == 'nt':
                os.startfile(str(Path(saved).parent))
    elif code:
        UI.note(f'操作未完成（返回码 {code}）。', 'red')
    else:
        UI.note('操作完成。', 'green')
    return code


def download_video(settings, url):
    UI.header('Video Quality', '正在查询可用画质')
    UI.box('视频画质', ['正在解析视频，请稍候…'])
    data = query_formats(build_command(settings, url, ['-F'], download=False))
    if data is None:
        UI.ask('Enter 返回')
        return
    merge = ffmpeg_available(settings)
    heights = sorted({int(f['height']) for f in data.get('formats', [])
                      if isinstance(f.get('height'), (int, float)) and f['height'] > 0
                      and f.get('vcodec') not in (None, 'none') and f.get('ext') != 'mhtml'
                      and (merge or f.get('acodec') not in (None, 'none'))}, reverse=True)
    if not heights:
        UI.result(False, ['未获取到可下载的视频画质。'])
        UI.ask('Enter 返回')
        return
    choices = {'1': None, **{str(i): height for i, height in enumerate(heights, 2)}}
    default = next((key for key, height in choices.items() if height == 1080), '1')
    UI.header('Video Quality', '下载视频 / 严格匹配分辨率')
    UI.menu('视频画质', [('01', '最高可用', '')] +
            [(f'{i:02}', f'{height}p', '') for i, height in enumerate(heights, 2)])
    choice = choose(f'选择 [默认 {default}]：', set(choices) | {'0'}, default)
    if choice == '0':
        return
    height = choices[choice]
    if not merge:
        print('未找到 FFmpeg：只能选择自带音轨且符合指定分辨率的格式；不可用时会报错。')
    else:
        print('将严格选择指定清晰度的最佳视频与最佳源音频，不自动降级。')
    print('若报 Requested format is not available，表示当前未获取到指定清晰度；可用“查看可用格式”检查。')
    run_command(build_command(settings, url, ['-f', video_format(height, merge)]))


def download_audio(settings, url):
    UI.header('Audio', '音频下载 / 保留原音质或转码')
    UI.menu('音频格式', [('01', '最佳原始音频', '保留源编码，不转码'),
                         ('02', 'MP3', '兼容常用播放器'), ('03', 'M4A / AAC', '高效音频编码')])
    choice = choose('选择 [默认 1]：', {'0', '1', '2', '3'}, '1')
    if choice == '0':
        return
    options = ['-f', 'ba/b']
    if choice != '1':
        if not ffmpeg_available(settings):
            print('转码需要 FFmpeg。请在设置中配置 FFmpeg 路径，或选择原始音频。')
            return
        UI.menu('转码码率', [('01', '320 kbps', ''), ('02', '256 kbps', ''),
                             ('03', '192 kbps', ''), ('04', '128 kbps', '')], '提高转码码率不会改善源音质')
        bitrate = choose('选择 [默认 1]：', {'1', '2', '3', '4'}, '1')
        options += ['-x', '--audio-format', 'mp3' if choice == '2' else 'm4a',
                    '--audio-quality', {'1': '320K', '2': '256K', '3': '192K', '4': '128K'}[bitrate]]
        print('转码码率不会提升原始音频质量。')
    elif not ffmpeg_available(settings):
        options = ['-f', 'ba']
    else:
        options += ['-x']
    run_command(build_command(settings, url, options))


def custom_download(settings, url):
    UI.header('Formats', '查看可用格式 / 精确选择格式 ID')
    print('先显示格式列表。按视频和音频的 ID 精确选择，例如 137+140 或 18。')
    if run_command(build_command(settings, url, ['-F'], download=False)):
        return
    fmt = UI.ask('格式 ID / yt-dlp 格式表达式（留空返回）').strip()
    if not fmt:
        return
    if '+' in fmt and not ffmpeg_available(settings):
        print('合并多个格式需要 FFmpeg，请先在设置中配置。')
        return
    run_command(build_command(settings, url, ['-f', fmt]))


def edit_settings(settings):
    while True:
        UI.header('Settings', '設定・カスタマイズ / 修改后自动保存')
        UI.menu('设置 / Settings', [
            ('01', '默认下载路径', settings['output']),
            ('02', 'YouTube Cookies', settings['cookies'] or '不使用'),
            ('03', '下载器后端', '本地源码' if settings['backend'] == 'source' else '已安装 yt-dlp'),
            ('04', 'FFmpeg 路径', settings['ffmpeg'] or '从 PATH 自动查找'),
            ('05', '角色装饰', 'ON' if settings['character'] == 'on' else 'OFF'),
            ('06', '显示执行命令', 'ON' if settings['command'] == 'on' else 'OFF'),
            ('07', 'B站 Cookies', settings.get('bilibili_cookies', '') or '不使用')])
        choice = choose('选择', {'0', '1', '2', '3', '4', '5', '6', '7'})
        if choice == '0':
            return
        updated = settings.copy()
        if choice in ('5', '6'):
            key = 'character' if choice == '5' else 'command'
            updated[key] = 'off' if settings[key] == 'on' else 'on'
        elif choice == '3':
            value = choose('1 已安装版本  2 本地源码：', {'1', '2'})
            updated['backend'] = 'installed' if value == '1' else 'source'
        else:
            key = {'1': 'output', '2': 'cookies', '4': 'ffmpeg', '7': 'bilibili_cookies'}[choice]
            value = UI.ask('输入路径（保存目录留空不变，其他留空清除）').strip().strip('"')
            if key == 'output' and not value:
                continue
            if value:
                path = Path(os.path.expandvars(value)).expanduser()
                if not path.is_absolute():
                    path = ROOT / path
                if key in ('cookies', 'bilibili_cookies') and not path.is_file():
                    print('文件不存在，设置未更改。')
                    continue
                if key == 'ffmpeg' and not (path.is_file() or (path / 'ffmpeg.exe').is_file()):
                    print('未找到 FFmpeg 文件，设置未更改。')
                    continue
                value = str(path)
            updated[key] = value
        save_settings(updated)
        settings.update(updated)
        UI.character = settings['character'] == 'on'
        UI.note('设置已保存。', 'green')


def show_history():
    UI.header('History', '履歴 / 最近下载任务', character=False)
    rows = read_history()
    if not rows:
        UI.box('历史记录', [('还没有下载记录。', 'muted')])
        return
    for row in reversed(rows[-8:]):
        UI.box(f'{row.get("status", "未知")} / {row.get("time", "")}',
               [str(row.get('title', '未知')), quality_line(row),
                f'路径 : {row.get("path", "") or "未保存"}'],
               'green' if row.get('status') == '完成' else 'yellow')


def show_about():
    UI.header('About Rem Terminal', 'レムにお任せください。')
    UI.box('✿  About Rem Terminal  ✿', [
        'Project  : Rem Downloader', 'Version  : 1.0.0',
        'Theme    : Rem / Re:Zero', 'Engine   : yt-dlp',
        f'Python   : {sys.version.split()[0]}', 'Interface: ANSI terminal / Python standard library'])


def download_danmaku(settings, url):
    from bilibili_danmaku import BilibiliClient, write_ass
    UI.header('Bilibili Danmaku', 'B站弹幕 / PotPlayer ASS')
    cookie_path = cookies_for_url(settings, url)
    using_cookie = cookie_available(cookie_path)
    client = BilibiliClient(cookie_path if using_cookie else '')
    def request(action):
        nonlocal client, using_cookie
        try:
            return action(client)
        except (ValueError, OSError):
            if not using_cookie:
                raise
            using_cookie = False
            client = BilibiliClient('')
            UI.note('Cookie 尝试失败，改用无 Cookie 重试。', 'yellow')
            return action(client)
    CURRENT_TASK.clear()
    CURRENT_TASK.update(status='解析中', title='正在获取B站视频信息', percent=0, format='ASS')
    sys.stdout.flush()
    try:
        video = request(lambda current: current.video(url))
        page = video['pages'][video['selected_page'] - 1]
        if len(video['pages']) > 1:
            UI.box('视频分P', [f'{part["page"]:02}  {part["part"]}' for part in video['pages']])
            selection = choose(f'选择分P [默认 {page["page"]} / 0返回]',
                               {'0'} | {str(part['page']) for part in video['pages']}, str(page['page']))
            if selection == '0':
                CURRENT_TASK.update(status='已取消')
                return
            page = video['pages'][int(selection) - 1]
        UI.menu('弹幕样式', [('01', '默认密集', '36px / 85% 不透明 / 滚动8秒'),
                              ('02', '自定义', '字号 / 不透明度 / 滚动时间')])
        style = choose('选择 [默认 1 / 0返回]', {'0', '1', '2'}, '1')
        if style == '0':
            CURRENT_TASK.update(status='已取消')
            return
        font_size, opacity, duration = 36, 85, 8
        if style == '2':
            def number(prompt, low, high, default):
                while True:
                    value = UI.ask(f'{prompt} [{low}–{high}，默认{default}]').strip() or str(default)
                    if value.isdigit() and low <= int(value) <= high:
                        return int(value)
                    UI.note('请输入范围内的整数。', 'yellow')
            font_size = number('字号', 12, 96, 36)
            opacity = number('不透明度 %', 10, 100, 85)
            duration = number('显示时间 秒', 3, 20, 8)
        title = video['title'] + (f' P{page["page"]}' if len(video['pages']) > 1 else '')
        def progress(done, total, count):
            CURRENT_TASK.update(status='下载中', title=title, percent=100 * done / total,
                                downloaded=f'{count} 条', total=f'{total} 段', format='ASS',
                                resolution='1920x1080 弹幕画布', notice='保留重复弹幕 · 不限制密度')
            UI.header('Bilibili Danmaku', '分段获取弹幕 / Ctrl+C 取消')
            UI.box('弹幕下载', [f'视频 : {title}', f'分段 : {done} / {total}',
                                f'弹幕 : {count} 条', '获取全部分段后仅导出 ASS。'])
            sys.stdout.flush()
        messages, ass = request(lambda current: current.download(video, page, settings['output'], progress))
        ass_folder = Path(settings['output']).expanduser() / 'ASS'
        ass_folder.mkdir(parents=True, exist_ok=True)
        special = write_ass(messages, ass, font_size, opacity, duration)
        CURRENT_TASK.update(status='完成', percent=100, path=str(ass), downloaded=f'{len(messages)} 条',
                            total=f'{len(messages)} 条', notice='')
        UI.header('Danmaku Completed', '弹幕已保存 / PotPlayer ASS')
        lines = [f'弹幕数量 : {len(messages)} 条', f'ASS : {ass}']
        if not messages:
            lines.append(('接口未返回弹幕，导出的文件为空。', 'yellow'))
        if special:
            lines.append((f'{special} 条特殊弹幕已降级为普通滚动文本。', 'yellow'))
        UI.result(True, lines)
    except KeyboardInterrupt:
        CURRENT_TASK.update(status='已取消', notice='未导出未完成弹幕')
        UI.header('Danmaku Cancelled', '已取消弹幕下载')
        UI.result(False, ['已取消，未导出未完成弹幕。'])
    except (ValueError, OSError) as exc:
        CURRENT_TASK.update(status='失败', notice=str(exc))
        UI.header('Danmaku Failed', '弹幕下载未完成')
        UI.result(False, [str(exc), '未完整获取时不会将结果标记为完成；可稍后重试。'])
    if sys.stdin.isatty():
        UI.ask('Enter 返回')


def change_download_path(settings):
    UI.header('Download Path', '下载路径')
    UI.box('下载路径', [f'当前目录：{settings["output"]}'])
    value = UI.ask('输入新目录（留空返回）').strip().strip('"')
    if not value:
        return
    path = Path(os.path.expandvars(value)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=path):
        pass
    updated = {**settings, 'output': str(path)}
    save_settings(updated)
    settings.update(updated)
    UI.result(True, [f'下载路径已保存：{path}'])
    if sys.stdin.isatty():
        UI.ask('Enter 返回')


def _main_menu(settings):
    UI.header()
    UI.menu('✿  Main Menu  ✿', [
        ('01', '下载视频', ''),
        ('02', '下载音频', ''),
        ('03', '下载弹幕（仅Bilibili）', ''),
        ('04', '下载选项', ''),
        ('05', '下载路径', ''),
        ('06', '历史记录', ''),
        ('07', '关于', '')], '')


def system_info(settings):
    key = (settings['backend'], settings['ffmpeg'])
    if key in SYSTEM_CACHE:
        return SYSTEM_CACHE[key]
    def version(command):
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=4)
            return (result.stdout.strip().splitlines() or ['不可用'])[0] if result.returncode == 0 else '不可用'
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return '未找到'
    info = {'os': platform.platform(), 'user': getpass.getuser(), 'python': platform.python_version(),
            'terminal': 'Windows Terminal' if os.environ.get('WT_SESSION') else
                        (os.environ.get('TERM') if os.environ.get('TERM') not in (None, '', 'dumb') else
                         'Windows Console' if os.name == 'nt' else 'Console')}
    try:
        info['yt-dlp'] = version(backend_command(settings) + ['--version'])
    except ValueError:
        info['yt-dlp'] = '未找到'
    ffmpeg = settings['ffmpeg'] or shutil.which('ffmpeg')
    if ffmpeg:
        path = Path(ffmpeg)
        executable = str(path / 'ffmpeg.exe') if path.is_dir() else str(path)
        info['ffmpeg'] = version([executable, '-version']).replace('ffmpeg version ', '').split(' Copyright')[0]
    else:
        info['ffmpeg'] = '未找到'
    SYSTEM_CACHE[key] = info
    return info


def main_menu(settings):
    from rem_screen import ACTIVE_SCREEN
    if ACTIVE_SCREEN and ACTIVE_SCREEN.compose:
        _main_menu(settings)
        return
    layout(UI, lambda: _main_menu(settings), system_info(settings), settings, CURRENT_TASK)


def preview(settings):
    main_menu(settings)
    UI.progress(68, '12.4 MiB/s', '00:13', '342 MiB / 503 MiB')
    UI.result(True, ['文件名 : ReZero_1080p.mp4', '实际画质 : 1920x1080',
                     '文件大小 : 31.83 MiB', '[Enter] 返回菜单'])
    UI.result(False, ['原因 : Connection timed out', ('建议 : 检查网络连接后重试。', 'yellow'), '[R] 重试   [B] 返回'])
    show_about()


def diagnose(settings):
    UI.header('Tools', '运行环境检查')
    print(f'Python：{sys.executable}\n保存目录：{settings["output"]}\n'
          f'Cookies：{"已配置" if settings["cookies"] else "未配置"}\n'
          f'FFmpeg：{"可用" if ffmpeg_available(settings) else "未找到"}')
    run_command(backend_command(settings) + ['--version'])


def main():
    prepare_cookie_files()
    parser = argparse.ArgumentParser(description='中文 yt-dlp 交互式下载菜单')
    parser.add_argument('--check', action='store_true', help='检查运行环境后退出')
    parser.add_argument('--preview', action='store_true', help='展示主题预览，不联网或下载')
    parser.add_argument('--no-color', action='store_true', help='禁用终端颜色')
    args = parser.parse_args()
    settings = load_settings()
    UI.character = settings['character'] == 'on'
    if args.no_color:
        UI.color = False
    if args.preview:
        preview(settings)
        return
    if args.check:
        diagnose(settings)
        return
    if sys.stdout.isatty() and sys.stdin.isatty():
        with Canvas() as screen:
            UI.fixed_width = 84
            from rem_dashboard import compose_page
            screen.compose = lambda lines, width, height: compose_page(
                lines, width, height, UI.color, system_info(settings), settings, CURRENT_TASK)
            interactive_loop(settings)
    else:
        interactive_loop(settings)


def download_text(settings, url):
    UI.header('Subtitles / Danmaku', '字幕与弹幕')
    UI.menu('下载字幕 / 弹幕', [('01', 'B站弹幕（ASS）', ''), ('02', '视频字幕', '')])
    choice = choose('请选择', {'0', '1', '2'}, '1')
    if choice == '1':
        download_danmaku(settings, url)
    elif choice == '2':
        convert = ffmpeg_available(settings)
        folder = Path(settings['output']).expanduser() / ('SRT' if convert else 'VTT')
        folder.mkdir(parents=True, exist_ok=True)
        options = ['--skip-download', '--write-subs', '--write-auto-subs', '--sub-langs', 'all,-live_chat',
                   '--sub-format', 'srt/best' if convert else 'vtt/best', '-P', str(folder),
                   '-o', '%(title)s [%(id)s].%(ext)s']
        if convert:
            options += ['--convert-subs', 'srt']
        run_command(build_command(settings, url, options, download=False))
        UI.note('字幕目录：' + str(folder))
        if sys.stdin.isatty():
            UI.ask('Enter 返回')


def download_options(settings):
    UI.header('Download Options', '下载选项')
    UI.menu('下载选项', [('01', '查看可用格式', ''), ('02', '按格式 ID 下载', '')])
    choice = choose('请选择', {'0', '1', '2'}, '1')
    if choice == '0':
        return
    url = url_input()
    if not url:
        return
    if choice == '2':
        custom_download(settings, url)
    else:
        run_command(build_command(settings, url, ['-F'], download=False))
        if sys.stdin.isatty():
            UI.ask('Enter 返回')


def interactive_loop(settings):
    while True:
        main_menu(settings)
        try:
            choice = choose('请选择功能 [01–07]', {'0', '1', '2', '3', '4', '5', '6', '7'})
            if choice == '0':
                return
            if choice == '5':
                change_download_path(settings)
            elif choice == '4':
                download_options(settings)
            elif choice in ('6', '7'):
                show_history() if choice == '6' else show_about()
                if sys.stdin.isatty():
                    UI.ask('Enter 返回')
            else:
                url = url_input()
                if not url:
                    continue
                if choice == '1':
                    download_video(settings, url)
                elif choice == '2':
                    download_audio(settings, url)
                elif choice == '3':
                    download_danmaku(settings, url)
        except (ValueError, OSError) as exc:
            UI.result(False, [f'操作失败：{exc}'])
            if sys.stdin.isatty():
                UI.ask('Enter 返回')
        except (KeyboardInterrupt, EOFError):
            print('\n已退出。')
            return


if __name__ == '__main__':
    try:
        main()
    finally:
        UI.reset()
