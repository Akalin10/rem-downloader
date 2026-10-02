import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import download_cli as cli
from rem_ui import Terminal, cells
from rem_portrait import rows, WIDTH, HEIGHT
from rem_dashboard import layout, terminal_columns


class InterfaceTests(unittest.TestCase):
    def test_failed_anonymous_download_retries_cookie_once(self):
        with tempfile.TemporaryDirectory() as directory:
            cookie = Path(directory) / 'youtube_cookies.txt'
            cookie.write_text('# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tsession\ttest\n', encoding='utf-8')
            settings = dict(cli.DEFAULTS, cookies=str(cookie))
            class Process:
                def __init__(self, code):
                    self.stdout = io.StringIO('ERROR: Sign in\n' if code else '')
                    self.code = code
                def wait(self):
                    return self.code
            with patch.object(cli, 'load_settings', return_value=settings), \
                    patch.object(cli.subprocess, 'Popen', side_effect=[Process(1), Process(1)]) as start, \
                    contextlib.redirect_stdout(io.StringIO()):
                command = ['yt-dlp', '--no-cookies', '-F', '--', 'https://youtu.be/test']
                self.assertEqual(cli.run_command(command), 1)
            self.assertEqual(start.call_count, 2)
            retry = start.call_args_list[1].args[0]
            self.assertNotIn('--no-cookies', retry)
            self.assertEqual(retry[retry.index('--cookies') + 1], str(cookie))

    def test_cookie_templates_are_empty_and_preserve_existing_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cookie_platforms.json').write_text(json.dumps([
                {'platform': 'youtube', 'pattern': 'https://youtube.com/'},
                {'platform': 'vimeo', 'pattern': 'https://vimeo.com/'}]), encoding='utf-8')
            with patch.object(cli, 'ROOT', root):
                cli.prepare_cookie_files()
                cookie = root / 'Cookies' / 'youtube_cookies.txt'
                self.assertFalse(cli.cookie_available(str(cookie)))
                cookie.write_text('existing', encoding='utf-8')
                cli.prepare_cookie_files()
                self.assertEqual(cookie.read_text(), 'existing')
                self.assertEqual(cli.cookies_for_url({}, 'https://vimeo.com/123'), str(root / 'Cookies' / 'vimeo_cookies.txt'))

    def test_youtube_download_isolated_from_plugins_and_uses_fragment_concurrency(self):
        settings = dict(cli.DEFAULTS, cookies='')
        with patch.object(cli, 'backend_command', return_value=['yt-dlp']), \
                patch.object(cli.shutil, 'which', return_value='C:/node.exe'):
            command = cli.build_command(settings, 'https://youtu.be/example', ['-f', 'ba', '-x', '--audio-format', 'mp3'])
            self.assertIn('--no-plugin-dirs', command)
            self.assertEqual(command[command.index('--http-chunk-size') + 1], '1M')
            self.assertEqual(command[command.index('--js-runtimes') + 1], 'node:C:/node.exe')
            self.assertEqual(command[command.index('--concurrent-fragments') + 1], '4')
            other = cli.build_command(settings, 'https://example.com/video', ['-f', 'ba'])
            self.assertNotIn('--no-plugin-dirs', other)
            self.assertNotIn('--js-runtimes', other)
            self.assertNotIn('--http-chunk-size', other)

    def test_finished_audio_is_sorted_by_final_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'audio.mp3'
            source.write_bytes(b'test audio')
            class Process:
                stdout = io.StringIO('REM_FILE:' + json.dumps(str(source)) + '\n')
                def wait(self):
                    return 0
            with patch.object(cli.subprocess, 'Popen', return_value=Process()), \
                    patch.object(cli, 'HISTORY', root / 'history.json'), \
                    patch.object(cli.sys.stdin, 'isatty', return_value=False), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.run_command(['yt-dlp', '-P', directory, 'REM_FILE:']), 0)
            self.assertEqual((root / 'MP3' / 'audio.mp3').read_bytes(), b'test audio')
            self.assertFalse(source.exists())
            self.assertEqual(cli.CURRENT_TASK['path'], str(root / 'MP3' / 'audio.mp3'))

    def test_cookie_files_are_selected_by_site_for_all_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            youtube = Path(directory) / 'cookies.txt'
            bilibili = Path(directory) / 'B_cookies.txt'
            youtube.touch()
            bilibili.touch()
            settings = dict(cli.DEFAULTS, cookies=str(youtube), bilibili_cookies=str(bilibili))
            cases = [('https://youtu.be/abc', str(youtube)),
                     ('https://www.youtube.com/watch?v=abc', str(youtube)),
                     ('https://www.bilibili.com/video/BV1xgb96TEen', str(bilibili)),
                     ('https://b23.tv/abc', str(bilibili)),
                     ('https://youtube.com.evil.example/video', ''),
                     ('https://evil.example/?url=bilibili.com', '')]
            with patch.object(cli, 'backend_command', return_value=['yt-dlp']):
                for url, expected in cases:
                    self.assertEqual(cli.cookies_for_url(settings, url), expected)
                    for options in (['-F'], ['-f', 'best'], ['-x']):
                        command = cli.build_command(settings, url, options)
                        self.assertNotIn('--cookies', command)
                        self.assertIn('--no-cookies', command)
            settings['bilibili_cookies'] = ''
            self.assertEqual(cli.cookies_for_url(settings, 'https://b23.tv/abc'), '')

    def test_home_dashboard_bottom_matches_menu(self):
        from rem_dashboard import capture, compose_page
        from rem_ui import ANSI
        with patch.object(cli, 'UI', Terminal(color=False, width=84)):
            left = capture(lambda: cli._main_menu(cli.DEFAULTS))
        combined = compose_page(left, 195, 49, False, {}, cli.DEFAULTS, {})
        left_bottom = max(i for i, row in enumerate(left) if ANSI.sub('', row).startswith('╰'))
        right_bottom = max(i for i, row in enumerate(combined)
                           if ANSI.sub('', row)[87:].startswith('╰'))
        self.assertEqual(left_bottom, right_bottom)

    def test_terminal_width_ignores_stale_environment(self):
        import os
        with patch('rem_dashboard.os.name', 'posix'), \
                patch.dict(os.environ, {'COLUMNS': '80'}), \
                patch('rem_dashboard.os.get_terminal_size', return_value=os.terminal_size((210, 50))):
            self.assertEqual(terminal_columns(), 210)

    def test_dashboard_wide_and_narrow_layout(self):
        for width in (196, 80):
            ui = Terminal(color=True, width=84)
            ui.interactive = False
            ui.dashboard_width = width
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                layout(ui, lambda: ui.box('菜单', ['下载视频']),
                       {'os': 'Windows', 'user': 'User'}, cli.DEFAULTS,
                       {'status': '下载中', 'title': '测试视频', 'percent': 68.4, 'speed': '8 MiB/s'})
            text = output.getvalue()
            self.assertIn('System Info', text)
            self.assertIn('68.4%', text)
            self.assertIn('Queue (0)', text)
            self.assertTrue(all(cells(line) <= max(84, width) for line in text.splitlines()))

    def test_pixel_portrait_uses_two_color_cells_and_aligns_header(self):
        art = rows(True)
        self.assertEqual(len(art), HEIGHT // 2)
        self.assertTrue(all(cells(line) == WIDTH for line in art))
        self.assertIn('48;2;', art[4])
        compact = rows(True, 32)
        self.assertEqual(len(compact), 18)
        self.assertTrue(all(cells(line) == 32 for line in compact))
        self.assertTrue(any(any(ch in line for ch in '▘▝▖▗▚▞') for line in compact))
        for width in (76, 90, 100):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                Terminal(color=True, width=width).header()
            framed = output.getvalue().splitlines()[2:]
            self.assertEqual(len(set(map(cells, framed))), 1)
            self.assertEqual(cells(framed[0]), min(width, 84))

    def test_unicode_borders_remain_aligned(self):
        for width in (40, 76, 100):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                Terminal(color=True, width=width).box('中文 / Settings', ['中文路径 D:\\下载器\\文件.mp4', 'x' * 140])
            widths = [cells(line) for line in output.getvalue().splitlines()]
            self.assertEqual(len(set(widths)), 1)
            self.assertLessEqual(widths[0], width)

    def test_untrusted_output_cannot_inject_terminal_escape(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            Terminal(color=False, width=60).box('标题', ['\x1b[2J恶意标题\x1b]0;bad\x07'])
        self.assertNotIn('\x1b', output.getvalue())
        self.assertNotIn('\x07', output.getvalue())

    def test_video_does_not_fall_back_to_lower_quality(self):
        self.assertEqual(cli.video_format(1080, True), 'bv[height=1080]+ba/b[height=1080]')

    def test_structured_subprocess_output_and_history(self):
        class Process:
            stdout = io.StringIO('REM_META:{"title":"测试视频", "resolution":"1920x1080"}\n'
                                 'REM_PROGRESS:68.0%|1MiB/s|00:10|30MiB\n'
                                 'REM_FILE:"D:/test.mp4"\n')
            def wait(self):
                return 0
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / 'history.json'
            with patch.object(cli, 'ROOT', Path(directory)), patch.object(cli, 'HISTORY', history), patch.object(cli.subprocess, 'Popen', return_value=Process()), \
                    patch.object(cli.sys.stdin, 'isatty', return_value=False), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.run_command(['yt-dlp', 'REM_FILE:']), 0)
            rows = json.loads(history.read_text(encoding='utf-8'))
            self.assertEqual(rows[0]['resolution'], '1920x1080')
            self.assertEqual(rows[0]['status'], '完成')
            self.assertIn('下载完成', output.getvalue())

    def test_failure_records_failure_and_explains_quality(self):
        class Process:
            stdout = io.StringIO('ERROR: Requested format is not available\n')
            def wait(self):
                return 1
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / 'history.json'
            with patch.object(cli, 'ROOT', Path(directory)), patch.object(cli, 'HISTORY', history), patch.object(cli.subprocess, 'Popen', return_value=Process()), \
                    patch.object(cli.sys.stdin, 'isatty', return_value=False), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.run_command(['yt-dlp', 'REM_FILE:']), 1)
            self.assertEqual(json.loads(history.read_text(encoding='utf-8'))[0]['status'], '失败')
            self.assertIn('不会自动降级', output.getvalue())


if __name__ == '__main__':
    unittest.main()
