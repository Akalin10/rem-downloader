from __future__ import annotations

import ctypes
import os
import re
import shutil
import sys
import unicodedata
from rem_portrait import rows as portrait_rows, WIDTH as PORTRAIT_WIDTH

ANSI = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
COLORS = {'blue': '75;190;245', 'cyan': '36;210;242', 'text': '195;220;235',
          'muted': '112;148;167', 'pink': '232;169;209', 'green': '29;220;156',
          'red': '255;100;110', 'yellow': '245;196;94'}
ART = [
    '        . * .  /\\  . * .',
    '      .--~--~--~--~--.',
    '     / //////|/////  \\',
    '    / ////// |/////  |',
    '    |/////// |///| <>|',
    '    |/////   |/ o|  /',
    '    |///|   .   /| /',
    '     \\ |`--___--\'|/',
    '       / / >o< \\ \\',
    '      /_/|  :  |\\_\\',
]


def cells(value):
    return sum(0 if unicodedata.combining(ch) else
               2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
               for ch in ANSI.sub('', str(value)))


def shorten(value, width):
    
    text = ANSI.sub('', str(value)).replace('\x1b', '').replace('\r', ' ').replace('\n', ' ')
    text = ''.join(c for c in text if c >= ' ')
    if cells(text) <= width:
        return text
    out = ''
    for ch in text:
        if cells(out + ch) > max(0, width - 1):
            break
        out += ch
    return out + '…' if width else ''


class Terminal:
    def __init__(self, color=None, width=None):
        self.interactive = sys.stdout.isatty()
        self.color = self.interactive and not os.environ.get('NO_COLOR') if color is None else color
        self.fixed_width = width
        self.character = True
        if os.name == 'nt' and self.interactive:
            try:
                kernel = ctypes.windll.kernel32
                handle = kernel.GetStdHandle(-11)
                mode = ctypes.c_ulong()
                if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                    self.color = bool(kernel.SetConsoleMode(handle, mode.value | 4)) and self.color
            except (AttributeError, OSError):
                self.color = False

    @property
    def width(self):
        return max(24, min(112, self.fixed_width or shutil.get_terminal_size((90, 30)).columns - 1))

    def ink(self, value, tone='text', bold=False):
        if not self.color:
            return str(value)
        return f'\x1b[{"1;" if bold else ""}38;2;{COLORS[tone]};48;2;4;14;22m{value}\x1b[0m\x1b[48;2;4;14;22m'

    def clear(self):
        from rem_screen import ACTIVE_SCREEN
        if ACTIVE_SCREEN:
            ACTIVE_SCREEN.clear()
            return
        if self.interactive and self.color:
            print('\x1b[0m\x1b[48;2;4;14;22m\x1b[2J\x1b[H', end='')

    def box(self, title, lines, tone='cyan', width=None):
        w = (min(self.width, width) if width else self.width) - 4
        title = shorten(f' {title} ', w - 2)
        print(self.ink('╭─' + title + '─' * max(0, w - cells(title) + 1) + '╮', tone))
        for line in lines:
            if isinstance(line, tuple):
                text, tint = line
            else:
                text, tint = line, 'text'
            text = shorten(text, w)
            print(self.ink('│ ', tone) + self.ink(text, tint) + ' ' * (w - cells(text)) + self.ink(' │', tone))
        print(self.ink('╰' + '─' * (w + 2) + '╯', tone))

    def header(self, title='Main Menu', subtitle='何をしますか？ / 请选择功能', character=None):
        self.clear()
        print(self.ink('  ✿  REM TERMINAL', 'blue', True) + self.ink('   /   RE:ZERO', 'muted'))
        print()
        if (self.character if character is None else character) and self.width >= 76:
            left = [('', 'text'), ('', 'text'), ('', 'text'), ('████  █████ █   █', 'blue'),
                    ('█   █ █     ██ ██', 'blue'), ('████  ████  █ █ █', 'blue'),
                    ('█  █  █     █   █', 'blue'), ('█   █ █████ █   █', 'blue'),
                    ('Rem Terminal Assistant', 'blue'), ('レムにお任せください。', 'pink'),
                    ('', 'text'), (title if title != 'Main Menu' else '', 'text'),
                    (subtitle if title != 'Main Menu' else '', 'muted')]
            w = min(self.width, 84) - 4
            caption = ' ✿  REM / TERMINAL ASSISTANT  ✿ '
            print(self.ink('╭─' + caption + '─' * (w - cells(caption) + 1) + '╮', 'cyan'))
            portrait_width = 32
            for index, art in enumerate(portrait_rows(self.color, portrait_width)):
                text, tone = left[index] if index < len(left) else ('', 'muted')
                text = shorten(text, w - portrait_width - 4)
                print(self.ink('│ ', 'cyan') + art + self.ink('    ' + text, tone)
                      + ' ' * (w - portrait_width - 4 - cells(text)) + self.ink(' │', 'cyan'))
            print(self.ink('╰' + '─' * (w + 2) + '╯', 'cyan'))
        else:
            self.box(title, [(subtitle, 'muted')])

    def menu(self, title, rows, footer='[00] 返回'):
        lines = []
        for code, label, description in rows:
            name = f' {code}  ›  {label}'
            if description and self.width >= 76:
                lines.append((name + ' ' * max(1, 27 - cells(name)) + description, 'blue'))
            else:
                lines.append((name, 'blue'))
            if description and self.width < 76:
                lines.append((f'       {description}', 'muted'))
        self.box(title, lines, width=84)
        print(self.ink('  ' + footer, 'cyan'))

    def note(self, message, tone='cyan'):
        print(self.ink('  › ' + message, tone))

    def ask(self, prompt):
        from rem_screen import ACTIVE_SCREEN
        styled = self.ink('  ✿ ' + prompt + ' › ', 'cyan')
        return ACTIVE_SCREEN.ask(styled) if ACTIVE_SCREEN else input(styled)

    def progress(self, percent, speed='', eta='', total=''):
        percent = max(0, min(100, percent))
        width = max(8, min(28, self.width - 45))
        done = round(percent * width / 100)
        bar = '█' * done + '░' * (width - done)
        text = f'  {bar} {percent:5.1f}%'
        detail = '  '.join(x for x in (total, speed, 'ETA ' + eta if eta else '') if x)
        if cells(text + '  ' + detail) > self.width:
            detail = '  '.join(x for x in (speed, 'ETA ' + eta if eta else '') if x)
        text = shorten(text + '  ' + detail, self.width)
        if self.interactive and self.color:
            print('\r\x1b[2K' + self.ink(text, 'blue'), end='', flush=True)
        else:
            print(text)

    def result(self, success, lines):
        print()
        self.box('✓  下载完成 / お疲れ様でした。' if success else '×  任务未完成',
                 lines, 'green' if success else 'red')

    def reset(self):
        if self.color:
            print('\x1b[0m', end='', flush=True)


UI = Terminal()
