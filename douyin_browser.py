import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse


def douyin_url(url):
    host = (urlparse(url).hostname or '').lower()
    return host == 'douyin.com' or host.endswith('.douyin.com') or host == 'iesdouyin.com' or host.endswith('.iesdouyin.com')


def resolve(url, timeout=180):
    if not douyin_url(url):
        raise ValueError('浏览器兜底仅支持抖音链接')
    from playwright.sync_api import sync_playwright
    profile = Path(__file__).with_name('browser_profiles') / 'douyin'
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as browser:
        context = None
        for channel in ('chrome', 'msedge'):
            try:
                context = browser.chromium.launch_persistent_context(str(profile), channel=channel,
                    headless=False, viewport=None, args=['--autoplay-policy=no-user-gesture-required'])
                break
            except Exception:
                pass
        if context is None:
            raise ValueError('无法启动 Chrome 或 Edge，请关闭此前的抖音兜底窗口后重试')
        try:
            page = context.pages[0] if context.pages else context.new_page()
            candidates = []
            def response_received(response):
                if response.status not in (200, 206):
                    return
                media = response.headers.get('content-type', '').lower()
                if media.startswith('video/') and urlparse(response.url).scheme == 'https':
                    candidates.append({'url': response.url,
                                       'referer': response.request.headers.get('referer', 'https://www.douyin.com/'),
                                       'user_agent': response.request.headers.get('user-agent', '')})
            page.on('response', response_received)
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=45000)
            except Exception:
                pass
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if page.is_closed():
                    raise ValueError('浏览器窗口已关闭，未获取视频地址')
                page.wait_for_timeout(500)
                details = page.evaluate('''() => {
                    const video = document.querySelector('video');
                    if (!video) return null;
                    video.muted = true;
                    video.play().catch(() => {});
                    return {url: video.currentSrc, width: video.videoWidth, height: video.videoHeight};
                }''')
                if candidates and details and details['width'] and details['height']:
                    result = next((item for item in reversed(candidates) if item['url'] == details['url']), None)
                    if result is None and len(candidates) == 1:
                        result = candidates[0]
                    if result:
                        result.update(width=details['width'], height=details['height'], title=page.title())
                        return result
            raise ValueError('等待播放超时，请在浏览器完成登录或验证，并播放目标视频后重试')
        finally:
            context.close()


def media_command(original, media):
    if urlparse(media.get('url', '')).scheme != 'https':
        raise ValueError('未获取有效的 HTTPS 视频地址')
    command = list(original)
    if '-f' in command:
        index = command.index('-f')
        expected = re.search(r'\[height=(\d+)\]', command[index + 1])
        if expected and int(expected[1]) != media.get('height'):
            raise ValueError(f'浏览器当前画质为 {media.get("height", "未知")}p，不符合所选 {expected[1]}p；请调整播放器画质后重试')
        command[index + 1] = 'best'
    if '--cookies' in command:
        index = command.index('--cookies')
        del command[index:index + 2]
    command[-1] = media['url']
    index = command.index('--')
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', media.get('title') or 'Douyin')[:100]
    command[index:index] = ['--no-cookies', '--no-plugin-dirs', '--referer', media['referer'],
                            '--user-agent', media['user_agent']]
    if '-o' in command:
        command[command.index('-o') + 1] = title.replace('%', '%%') + '.%(ext)s'
    return command


if __name__ == '__main__':
    try:
        print(json.dumps(resolve(sys.argv[1]), ensure_ascii=False))
    except ValueError as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': '浏览器未能获取视频，请确认已完成验证并播放目标视频；需要安装 Playwright 和 Chrome/Edge。'}, ensure_ascii=False))
        sys.exit(1)
