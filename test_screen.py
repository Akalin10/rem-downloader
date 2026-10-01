import io
import os
import re
import sys
import unittest
from unittest.mock import patch
from rem_screen import Canvas


class ScreenTests(unittest.TestCase):
    def test_download_dashboard_bottom_matches_short_left_task_panel(self):
        from rem_dashboard import capture, compose_page
        from rem_ui import Terminal, ANSI
        ui = Terminal(color=True, width=84)
        left = capture(lambda: (ui.header('Downloading', '正在下载'),
                       ui.box('Downloading', ['任务名称 : test', '实际画质 : 1080p',
                                              '格式 : mp4', 'Ctrl+C 取消'])))
        for width, height in ((195, 49), (150, 34), (120, 30)):
            frame = compose_page(left, width, height, True, {}, {'output': '.'},
                                 {'status': '下载中', 'percent': 12.6})
            split = min(84, (width - 3) // 2) + 3
            left_bottom = max(i for i, row in enumerate(frame) if ANSI.sub('', row).startswith('╰'))
            right_bottom = max(i for i, row in enumerate(frame) if ANSI.sub('', row)[split:].startswith('╰'))
            self.assertEqual(left_bottom, right_bottom)

    def test_clipped_right_border_keeps_original_color(self):
        from rem_screen import fit_line
        from rem_ui import Terminal, COLORS
        from rem_dashboard import capture
        for tone in ('cyan', 'green', 'red', 'pink'):
            rows = capture(lambda: Terminal(color=True, width=84).box('Title', ['text'], tone))
            for row, closing in zip(rows, ('╮', '│', '╯')):
                clipped = fit_line(row, 60)
                self.assertTrue(clipped.endswith(f'\x1b[38;2;{COLORS[tone]};48;2;4;14;22m{closing}\x1b[0m'))

    def test_compact_viewports_keep_portrait_dashboard_and_prompt(self):
        from rem_dashboard import compose_page, capture
        from rem_ui import Terminal, ANSI, cells
        ui = Terminal(color=True, width=84)
        left = capture(lambda: (ui.header(), ui.menu('Main Menu',
                       [(str(i), '下载视频', '选择画质') for i in range(8)])))
        left.append('选择 > 4')
        for width, height in ((150, 34), (120, 30), (100, 28), (80, 30)):
            with self.subTest(width=width, height=height):
                frame = compose_page(left, width, height, True, {}, {'output': '.'}, {})
                text = '\n'.join(ANSI.sub('', row) for row in frame)
                self.assertIn('REM', text)
                self.assertIn('System Info', text)
                self.assertIn('Current Task', text)
                self.assertIn('选择 > 4', text)
                self.assertTrue(all(cells(row) <= width for row in frame))
                self.assertLessEqual(len(frame), height)
                if width >= 100:
                    left_borders = [i for i, row in enumerate(frame)
                                    if ANSI.sub('', row).startswith('╰')]
                    right_borders = [i for i, row in enumerate(frame)
                                     if '╯' in ANSI.sub('', row)[(width - 3) // 2 + 3:]]
                    self.assertEqual(left_borders[-1], right_borders[-1])

    def test_resize_repaints_without_input_and_restores_full_page(self):
        from rem_ui import Terminal, ANSI, cells
        output = io.StringIO()
        with patch('rem_portrait.Path', type(__import__('pathlib').Path.cwd())), patch('rem_screen.os.name', 'posix'):
            with Canvas(output=output, dimensions=(196, 50)) as screen:
                Terminal(color=False, width=84).header()
                Terminal(color=False, width=84).menu('Quality', [('01', '1080p', '')])
                screen.paint('选择 > 1080')
                original = screen.previous.copy()
                screen.dimensions = (60, 18)
                deadline = __import__('time').monotonic() + 2
                while screen.last_size != (60, 18) and __import__('time').monotonic() < deadline:
                    screen.stop_resize.wait(0.02)
                self.assertEqual(screen.last_size, (60, 18))
                self.assertTrue(any('选择 > 1080' in ANSI.sub('', row) for row in screen.previous))
                self.assertTrue(all(cells(row) <= 59 for row in screen.previous))
                self.assertTrue(any(ANSI.sub('', row).endswith('╯') for row in screen.previous))
                screen.dimensions = (196, 50)
                screen.paint(screen.active_prompt, reuse=True)
                self.assertEqual(screen.previous, original)
                self.assertGreaterEqual(output.getvalue().count('\x1b[2J'), 4)

    def test_partial_page_is_not_published_before_flush(self):
        output = io.StringIO()
        with patch('rem_screen.os.name', 'posix'):
            with Canvas(output=output, dimensions=(196, 50)) as screen:
                print('Old page')
                screen.flush()
                old_frame = screen.previous.copy()
                screen.clear()
                print('REM header')
                print('New page')
                self.assertEqual(screen.previous, old_frame)
                screen.flush()
                self.assertIn('REM header', screen.previous[0])

    def test_quality_page_keeps_dashboard_and_left_prompt_position(self):
        from rem_dashboard import compose_page
        from rem_ui import ANSI, cells
        output = io.StringIO()
        with patch('rem_dashboard.Path', type(__import__('pathlib').Path.cwd())):
            with Canvas(output=output, dimensions=(196, 50)) as screen:
                screen.compose = lambda lines, width, height: compose_page(
                    lines, width, height, False, {}, {'output': 'D:\\downloads'}, {})
                print('Video Quality')
                print('1080p / Full HD')
                screen.paint('选择画质 > ')
                frame = [ANSI.sub('', row) for row in screen.previous]
                self.assertIn('Video Quality', frame[0])
                self.assertTrue(any('System Info' in row for row in frame))
                self.assertTrue(any('Current Task' in row for row in frame))
                self.assertTrue(all(cells(row) <= 195 for row in frame))
                self.assertIn('\x1b[3;', output.getvalue())
                screen.clear()
                print('Audio Quality')
                screen.paint()
                self.assertTrue(any('System Info' in ANSI.sub('', row) for row in screen.previous))

    def test_pages_use_one_alternate_screen_without_appending_newlines(self):
        output = io.StringIO()
        with patch('rem_screen.os.name', 'posix'):
            with Canvas(output=output, dimensions=(80, 8)) as screen:
                for number in range(30):
                    screen.clear()
                    print('REM header')
                    print('Page', number)
                    screen.flush()
        rendered = output.getvalue()
        self.assertEqual(rendered.count('\x1b[?1049h'), 1)
        self.assertEqual(rendered.count('\x1b[?1049l'), 1)
        self.assertNotIn('\n', rendered)
        self.assertNotIn('\r', rendered)
        self.assertIn('\x1b[?25h', rendered)

    def test_exception_and_ctrl_c_restore_stdout_and_terminal(self):
        for error in (RuntimeError('error'), KeyboardInterrupt()):
            output, original = io.StringIO(), sys.stdout
            with self.assertRaises(type(error)), patch('rem_screen.os.name', 'posix'):
                with Canvas(output=output, dimensions=(80, 8)):
                    raise error
            self.assertIs(sys.stdout, original)
            self.assertTrue(output.getvalue().endswith('\x1b[?1049l'))

    def test_progress_replaces_the_current_row(self):
        screen = Canvas(output=io.StringIO(), dimensions=(40, 8))
        screen.write('REM\n')
        screen.write('\r\x1b[2K10%')
        screen.write('\r\x1b[2K90%')
        self.assertEqual(screen.lines, ['REM'])
        self.assertEqual(screen.current, '90%')

    def test_content_never_targets_rows_beyond_viewport(self):
        output = io.StringIO()
        screen = Canvas(output=output, dimensions=(40, 6))
        screen.write('\n'.join(str(i) for i in range(100)))
        screen.paint('请输入 › ')
        row_numbers = [int(value) for value in re.findall(r'\x1b\[(\d+);\d+H', output.getvalue())]
        self.assertTrue(all(row <= 6 for row in row_numbers))
        self.assertNotIn('\n', output.getvalue())

    @unittest.skipUnless(os.name == 'nt', 'Windows line editor')
    def test_input_is_not_echoed_as_scrollback(self):
        output = io.StringIO()
        screen = Canvas(output=output, dimensions=(80, 8))
        with patch('msvcrt.getwch', side_effect=['5', '\b', '8', '\r']):
            self.assertEqual(screen.ask('菜单 › '), '8')
        self.assertNotIn('\n', output.getvalue())


if __name__ == '__main__':
    unittest.main()
