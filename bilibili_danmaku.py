from __future__ import annotations

import http.cookiejar
import json
import math
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener
from urllib.error import HTTPError, URLError


def read_varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError('弹幕数据被截断')
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise ValueError('无效的弹幕整数')


def protobuf_fields(data):
    offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        field, wire = tag >> 3, tag & 7
        if field == 0:
            raise ValueError('无效的弹幕字段')
        if wire == 0:
            value, offset = read_varint(data, offset)
        elif wire in (1, 2, 5):
            length = 8 if wire == 1 else 4
            if wire == 2:
                length, offset = read_varint(data, offset)
            if offset + length > len(data):
                raise ValueError('弹幕数据被截断')
            value = data[offset:offset + length]
            offset += length
        else:
            raise ValueError('不支持的弹幕数据字段')
        yield field, wire, value


def parse_segment(data):
    result = []
    for field, wire, value in protobuf_fields(data):
        if field == 2 and wire == 0 and value == 1:
            raise ValueError('视频弹幕已关闭')
        if field != 1 or wire != 2:
            continue
        item = {}
        for number, kind, content in protobuf_fields(value):
            if number in (1, 2, 3, 4, 5, 8, 11) and kind == 0:
                item[number] = content
            elif number in (7, 12) and kind == 2:
                item[number] = content.decode('utf-8', errors='replace')
        if 7 in item:
            result.append({'id': str(item.get(12, item.get(1, '0'))),
                           'time': item.get(2, 0) / 1000,
                           'mode': item.get(3, 1), 'size': item.get(4, 25),
                           'color': item.get(5, 0xffffff), 'text': item[7],
                           'ctime': item.get(8, 0), 'pool': item.get(11, 0)})
    return result


class BilibiliClient:
    def __init__(self, cookies=''):
        jar = http.cookiejar.MozillaCookieJar()
        if cookies:
            try:
                jar.load(str(Path(cookies).expanduser()), ignore_discard=True)
            except (OSError, http.cookiejar.LoadError) as exc:
                raise ValueError('无法读取 Cookies，请使用 Netscape 格式文件') from exc
        self.opener = build_opener(HTTPCookieProcessor(jar))

    def request(self, url):
        for attempt in range(3):
            try:
                request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                                               'Referer': 'https://www.bilibili.com/'})
                with self.opener.open(request, timeout=20) as response:
                    return response.read(), response.geturl()
            except HTTPError as exc:
                if exc.code in (401, 403, 412, 429):
                    raise ValueError(f'B站拒绝请求（HTTP {exc.code}），请检查 Cookies 或稍后重试') from exc
                if attempt == 2:
                    raise ValueError(f'B站接口请求失败（HTTP {exc.code}）') from exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt == 2:
                    raise ValueError('B站接口连接失败，请检查网络后重试') from exc
            time.sleep(attempt + 1)

    def json_api(self, path, params):
        raw, _ = self.request('https://api.bilibili.com' + path + '?' + urlencode(params))
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise ValueError('B站返回了无效数据') from exc
        if not isinstance(payload, dict):
            raise ValueError('B站返回了无效数据')
        if payload.get('code') != 0:
            raise ValueError(f'B站接口错误 {payload.get("code")}：{payload.get("message", "未知错误")}')
        if not isinstance(payload.get('data'), dict):
            raise ValueError('B站未返回有效的视频信息')
        return payload['data']

    def video(self, url):
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in (
                'www.bilibili.com', 'bilibili.com', 'm.bilibili.com', 'b23.tv'):
            raise ValueError('请使用 B站 BV/av 视频网址或 b23.tv 短链接')
        if parsed.hostname == 'b23.tv':
            _, url = self.request(url)
            parsed = urlparse(url)
            if parsed.hostname not in ('www.bilibili.com', 'bilibili.com', 'm.bilibili.com'):
                raise ValueError('短链接未指向 B站视频')
        match = re.search(r'/(BV[0-9A-Za-z]{10}|av[0-9]+)(?:/|$)', parsed.path, re.I)
        if not match:
            raise ValueError('目前支持 BV/av 投稿视频；番剧 ep/ss 链接请使用对应 BV 地址')
        identifier = match[1]
        params = {'bvid': 'BV' + identifier[2:]} if identifier[:2].lower() == 'bv' else {'aid': identifier[2:]}
        try:
            self.request('https://www.bilibili.com/')
        except ValueError:
            pass
        try:
            data = self.json_api('/x/web-interface/view', params)
        except ValueError as api_error:
            try:
                raw, _ = self.request('https://www.bilibili.com/video/' + identifier)
                html = raw.decode('utf-8', errors='replace')
                initial = re.search(r'window\.__INITIAL_STATE__\s*=\s*', html)
                if not initial:
                    raise ValueError('页面未包含视频信息')
                state, _ = json.JSONDecoder().raw_decode(html[initial.end():])
                data = state.get('videoData')
                if not isinstance(data, dict):
                    raise ValueError('页面未包含有效的视频信息')
            except (ValueError, AttributeError):
                raise api_error
        if (not isinstance(data.get('pages'), list) or not data['pages'] or
                not isinstance(data.get('title'), str) or not data.get('bvid') or not data.get('aid')):
            raise ValueError('视频信息不完整，无法获取全时长弹幕')
        if any(not isinstance(part, dict) or not part.get('cid') or
               not isinstance(part.get('duration'), (int, float)) or part['duration'] < 0
               for part in data['pages']):
            raise ValueError('视频分P时长或标识缺失，无法获取全时长弹幕')
        try:
            page = int(parse_qs(parsed.query).get('p', ['1'])[0])
        except ValueError:
            page = 1
        if not 1 <= page <= len(data['pages']):
            raise ValueError('视频分P编号不存在')
        data['selected_page'] = page
        return data

    def download(self, video, page, output, progress=None):
        destination = Path(output).expanduser()
        destination.mkdir(parents=True, exist_ok=True)
        title = video['title'] + (f' P{page["page"]} {page["part"]}' if len(video['pages']) > 1 else '')
        title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:100] or 'Bilibili'
        stem = f'{title} [{video["bvid"]}] [{page["cid"]}].danmaku'
        count = max(1, math.ceil(page['duration'] / 360))
        messages = []
        for index in range(1, count + 1):
            if progress:
                progress(index - 1, count, len(messages))
            url = 'https://api.bilibili.com/x/v2/dm/web/seg.so?' + urlencode(
                {'type': 1, 'oid': page['cid'], 'pid': video['aid'], 'segment_index': index})
            raw, _ = self.request(url)
            try:
                parsed = parse_segment(raw)
            except ValueError as exc:
                raise ValueError(f'第 {index}/{count} 段数据无效：{exc}，未导出未完成弹幕') from exc
            messages.extend(parsed)
            if progress:
                progress(index, count, len(messages))
            if index < count:
                time.sleep(0.2)
        return messages, destination / 'ASS' / (stem + '.ass')


def ass_time(seconds):
    ticks = max(0, round(seconds * 100))
    return f'{ticks // 360000}:{ticks // 6000 % 60:02}:{ticks // 100 % 60:02}.{ticks % 100:02}'


def write_ass(messages, path, font_size=36, opacity=85, duration=8):
    if not 12 <= font_size <= 96 or not 10 <= opacity <= 100 or not 3 <= duration <= 20:
        raise ValueError('弹幕样式参数超出范围')
    alpha = round(255 * (100 - opacity) / 100)
    header = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n'
              'WrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n'
              'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
              'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, '
              'Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
              f'Style: Danmaku,Microsoft YaHei,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,'
              '0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1\n\n[Events]\n'
              'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    tracks = max(1, (1080 - font_size * 2) // (font_size + 6))
    lanes = {1: 0, 4: 0, 5: 0, 6: 0}
    special = 0
    with Path(path).open('w', encoding='utf-8-sig', newline='\n') as stream:
        stream.write(header)
        for message in sorted(messages, key=lambda m: m['time']):
            mode = message['mode']
            text = message['text']
            if mode not in (1, 2, 3, 4, 5, 6):
                special += 1
                if mode == 7:
                    try:
                        advanced = json.loads(text)
                        if isinstance(advanced, list) and len(advanced) > 4:
                            text = str(advanced[4])
                    except ValueError:
                        pass
                mode = 1
            mode = mode if mode in (4, 5, 6) else 1
            text = ''.join(ch if ord(ch) >= 32 else ' ' for ch in text)
            text = text.replace('\\', '∖').replace('{', '｛').replace('}', '｝')
            lane = lanes[mode] % tracks
            lanes[mode] += 1
            y = font_size + lane * (font_size + 6)
            width = max(font_size, math.ceil(sum(1 if unicodedata.east_asian_width(ch) in ('W', 'F')
                                                else 0.6 for ch in text) * font_size))
            color = int(message['color']) & 0xffffff
            color = f'{color & 255:02X}{(color >> 8) & 255:02X}{color >> 16:02X}'
            if mode == 4:
                motion = f'\\an2\\pos(960,{1080 - y})'
            elif mode == 5:
                motion = f'\\an8\\pos(960,{y})'
            elif mode == 6:
                motion = f'\\an7\\move({-width},{y},1920,{y})'
            else:
                motion = f'\\an7\\move(1920,{y},{-width},{y})'
            tags = f'{{{motion}\\c&H{color}&\\alpha&H{alpha:02X}&}}'
            start = message['time']
            stream.write(f'Dialogue: 0,{ass_time(start)},{ass_time(start + duration)},Danmaku,,0,0,0,,{tags}{text}\n')
    return special
