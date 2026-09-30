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
