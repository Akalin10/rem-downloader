import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from bilibili_danmaku import BilibiliClient, ass_time, parse_segment, write_ass, write_xml


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def field(number, value):
    if isinstance(value, str):
        value = value.encode()
    if isinstance(value, bytes):
        return varint(number * 8 + 2) + varint(len(value)) + value
    return varint(number * 8) + varint(value)


def segment(text='哈哈哈', mode=1):
    message = b''.join(field(k, v) for k, v in [(1, 123), (2, 1500), (3, mode),
                      (4, 25), (5, 0xff0000), (7, text), (12, '123')])
    return field(1, message)


class DanmakuTests(unittest.TestCase):
    def test_binary_length_byte_must_not_be_mistaken_for_json(self):
        raw = next(segment('x' * n) for n in range(200)
                   if segment('x' * n).lstrip().startswith(b'{'))
        with tempfile.TemporaryDirectory() as directory:
            client = BilibiliClient()
            with patch.object(client, 'request', return_value=(raw, '')):
                items, _ = client.download({'title': 'test', 'bvid': 'BV1fwYF62Eak',
                                           'aid': 1, 'pages': [{}]},
                                          {'cid': 2, 'duration': 60}, directory)
            self.assertEqual(len(items), 1)

    def test_video_page_fallback_and_selected_part(self):
        import json
        client = BilibiliClient()
        video = {'title': 'test', 'bvid': 'BV17x411w7KC', 'aid': 170001,
                 'pages': [{'page': 1, 'part': 'one', 'cid': 1, 'duration': 400},
                           {'page': 2, 'part': 'two', 'cid': 2, 'duration': 200}]}
        html = ('<script>window.__INITIAL_STATE__=' + json.dumps({'videoData': video}) + ';x()</script>').encode()
        with patch.object(client, 'json_api', side_effect=ValueError('API refused')), \
                patch.object(client, 'request', side_effect=[(b'', ''), (html, '')]):
            result = client.video('https://www.bilibili.com/video/BV17x411w7KC?p=2')
        self.assertEqual(result['selected_page'], 2)

    def test_menu_dispatches_danmaku_without_video_download(self):
        import download_cli as cli
        with patch.object(cli, 'main_menu'), patch.object(cli, 'choose', side_effect=['9', '0']), \
                patch.object(cli, 'url_input', return_value='https://www.bilibili.com/video/BV1xx411c7mD'), \
                patch.object(cli, 'download_danmaku') as action, patch.object(cli, 'custom_download') as other:
            cli.interactive_loop(cli.DEFAULTS)
        action.assert_called_once()
        other.assert_not_called()

    def test_cli_exports_ass_and_keeps_dashboard_task_state(self):
        import contextlib
        import io
        import download_cli as cli
        with tempfile.TemporaryDirectory() as directory:
            video = {'title': 'test', 'pages': [{'page': 1, 'cid': 2, 'duration': 5}], 'selected_page': 1}
            xml = Path(directory) / 'test.danmaku.xml'
            messages = parse_segment(segment() * 2)
            with patch('bilibili_danmaku.BilibiliClient') as factory, patch.object(cli, 'choose', return_value='1'), \
                    patch.object(cli.sys.stdin, 'isatty', return_value=False), contextlib.redirect_stdout(io.StringIO()) as output:
                factory.return_value.video.return_value = video
                factory.return_value.download.return_value = messages, xml
                cli.download_danmaku(dict(cli.DEFAULTS, output=directory, cookies=''), 'https://www.bilibili.com/video/BV1xx411c7mD')
            self.assertEqual(cli.CURRENT_TASK['status'], '完成')
            self.assertEqual(xml.with_suffix('.ass').read_text(encoding='utf-8-sig').count('Dialogue:'), 2)
            self.assertIn('不去重', output.getvalue())

    def test_protobuf_unknown_fields_and_duplicates(self):
        items = parse_segment(segment() + segment() + field(20, b'unknown'))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['time'], 1.5)
        self.assertEqual(items[0]['color'], 0xff0000)
        self.assertEqual(items[0]['id'], '123')

    def test_truncated_response_and_closed_comments_fail(self):
        for data in (b'\x0a\x80', b'\x0a\xff\x7f', field(2, 1)):
            with self.assertRaises(ValueError):
                parse_segment(data)

    def test_all_segments_downloaded_without_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            client = BilibiliClient()
            urls, progress = [], []
            def request(url):
                urls.append(url)
                return segment(), url
            with patch.object(client, 'request', side_effect=request), patch('bilibili_danmaku.time.sleep'):
                messages, xml = client.download({'title': '../test', 'bvid': 'BV1xx411c7mD',
                    'aid': 170001, 'pages': [{}]}, {'page': 1, 'cid': 42, 'duration': 721},
                    directory, lambda *values: progress.append(values))
            self.assertEqual(len(messages), 3)
            self.assertEqual(len(ET.parse(xml).findall('d')), 3)
            self.assertEqual(len(list(Path(directory).rglob('*.bin'))), 3)
            self.assertTrue(urls[-1].endswith('segment_index=3'))
            self.assertEqual(progress[-1], (3, 3, 3))
            self.assertEqual(xml.parent, Path(directory))

    def test_failed_segment_does_not_export_complete_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            client = BilibiliClient()
            with patch.object(client, 'request', side_effect=[(segment(), ''), ValueError('failed')]), \
                    patch('bilibili_danmaku.time.sleep'):
                with self.assertRaises(ValueError):
                    client.download({'title': 'test', 'bvid': 'BV1xx411c7mD', 'aid': 1, 'pages': [{}]},
                                    {'page': 1, 'cid': 2, 'duration': 400}, directory)
            self.assertEqual(len(list(Path(directory).rglob('*.bin'))), 1)
            self.assertFalse(list(Path(directory).glob('*.xml')))

    def test_ass_animation_modes_colors_and_injection_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            items = [parse_segment(segment('hello {\\pos(0,0)}', mode))[0] for mode in (1, 4, 5, 6)]
            target = Path(directory) / 'test.ass'
            self.assertEqual(write_ass(items, target), 0)
            text = target.read_text(encoding='utf-8-sig')
            self.assertEqual(text.count('Dialogue:'), 4)
            self.assertIn('\\move(1920,', text)
            self.assertIn('\\an2\\pos(960,', text)
            self.assertIn('\\an8\\pos(960,', text)
            self.assertIn('\\c&H0000FF&', text)
            self.assertNotIn('{\\pos(0,0)}', text)

    def test_dense_comments_are_not_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            items = parse_segment(segment() * 120)
            target = Path(directory) / 'dense.ass'
            write_ass(items, target)
            self.assertEqual(target.read_text(encoding='utf-8-sig').count('Dialogue:'), 120)
            xml = target.with_suffix('.xml')
            write_xml(items, xml, 1)
            self.assertEqual(len(ET.parse(xml).findall('d')), 120)

    def test_special_comments_preserved_as_readable_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            item = parse_segment(segment('[0,0,1,5,"特殊弹幕"]', 7))[0]
            target = Path(directory) / 'special.ass'
            self.assertEqual(write_ass([item], target), 1)
            self.assertIn('特殊弹幕', target.read_text(encoding='utf-8-sig'))

    def test_url_validation_and_time_rounding(self):
        for url in ('https://evil.example/BV1xx411c7mD', 'file:///tmp/video',
                    'https://www.bilibili.com@evil.example/video/BV1xx411c7mD'):
            with self.assertRaises(ValueError):
                BilibiliClient().video(url)
        self.assertEqual(ass_time(59.999), '0:01:00.00')


if __name__ == '__main__':
    unittest.main()
