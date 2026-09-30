from __future__ import annotations

import atexit
import os
import re
import shutil
import signal
import sys
import time
import threading
import unicodedata

SGR = re.compile(r'\x1b\[[0-9;]*m')
ACTIVE_SCREEN = None


def clip_line(line, width):
    result, used, index = [], 0, 0
    while index < len(line):
        match = SGR.match(line, index)
        if match:
            result.append(match[0])
            index = match.end()
            continue
        ch = line[index]
        size = 0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
        if used + size > width:
            break
        if ch >= ' ':
            result.append(ch)
            used += size
        index += 1
    return ''.join(result) + '\x1b[0m'


class Canvas:
    def __init__(self, output=None, dimensions=None):
        self.output = output or sys.stdout
        self.dimensions = dimensions
        self.lines = []
        self.current = ''
        self.previous = []
        self.last_paint = 0
        self.closed = False
        self.signal_handlers = {}
        self.console_mode = None
        self.input_active = False
        self.compose = None
        self.last_size = None
        self.published = []
        self.active_prompt = None
        self.render_lock = threading.RLock()
        self.stop_resize = threading.Event()

    @property
    def encoding(self):
        return self.output.encoding

    def fileno(self):
        return self.output.fileno()

    def isatty(self):
        return self.output.isatty()

    def size(self):
        if self.dimensions:
            return self.dimensions
        try:
            return os.get_terminal_size(self.output.fileno())
        except (OSError, ValueError):
            return shutil.get_terminal_size((196, 50))

    def __enter__(self):
        global ACTIVE_SCREEN
        self.original_stdout = sys.stdout
        if os.name == 'nt':
            import ctypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetStdHandle.restype = ctypes.c_void_p
            kernel.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            kernel.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            handle = kernel.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                self.console_mode = kernel, handle, mode.value
                if not kernel.SetConsoleMode(handle, mode.value | 4):
                    raise OSError('终端不支持 VT 控制序列，请用 Windows Terminal 运行。')
        self.output.write('\x1b[?1049h\x1b[?7l\x1b[?25l\x1b[0m\x1b[2J\x1b[H')
        self.output.flush()
        sys.stdout = self
        ACTIVE_SCREEN = self
        for name in ('SIGTERM', 'SIGHUP'):
            sig = getattr(signal, name, None)
            if sig is not None:
                try:
                    self.signal_handlers[sig] = signal.getsignal(sig)
                    signal.signal(sig, self._terminate)
                except ValueError:
                    pass
        atexit.register(self.close)
        self.resize_thread = threading.Thread(target=self.watch_resize, daemon=True)
        self.resize_thread.start()
        return self

    def watch_resize(self):
        while not self.stop_resize.wait(0.1):
            if self.last_size is not None and tuple(self.size()) != self.last_size:
                self.paint(self.active_prompt, reuse=True)

    def _terminate(self, signum, frame):
        raise SystemExit(128 + signum)

    def __exit__(self, kind, value, traceback):
        self.close()

    def close(self):
        global ACTIVE_SCREEN
        if self.closed:
            return
        self.closed = True
        self.stop_resize.set()
        if hasattr(self, 'resize_thread'):
            self.resize_thread.join(timeout=1)
        sys.stdout = self.original_stdout
        ACTIVE_SCREEN = None
        try:
            self.output.write('\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l')
            self.output.flush()
        finally:
            if self.console_mode:
                kernel, handle, mode = self.console_mode
                kernel.SetConsoleMode(handle, mode)
            for sig, handler in self.signal_handlers.items():
                signal.signal(sig, handler)
            atexit.unregister(self.close)

    def clear(self):
        self.lines.clear()
        self.current = ''

    def write(self, text):
        original_length = len(text)
        if '\x1b[2J' in text:
            self.clear()
            text = text.replace('\x1b[2J', '').replace('\x1b[H', '')
        
        
        text = re.sub(r'\x1b\[[0-9;?]*[A-ln-zA-Z]', '', text)
        for part in re.split(r'([\r\n])', text):
            if part == '\r':
                self.current = ''
            elif part == '\n':
                self.lines.append(self.current)
                self.current = ''
            else:
                self.current += part
        
        if len(self.lines) > 400:
            self.lines = self.lines[-400:]
        
        
        return original_length

    def flush(self):
        self.paint()

    def paint(self, prompt=None, reuse=False):
        with self.render_lock:
            self._paint(prompt, reuse)

    def _paint(self, prompt, reuse):
        if self.closed:
            return
        width, height = self.size()
        dimensions = (width, height)
        resized = dimensions != self.last_size
        if reuse:
            content = self.published.copy()
        else:
            content = self.lines + ([self.current] if self.current else [])
            self.published = content.copy()
            self.active_prompt = prompt
        width, height = max(1, width - 1), max(2, height)
        if prompt is not None:
            content += [prompt]
        if len(content) > height - 1:
            borders = [i for i, line in enumerate(content) if SGR.sub('', line).startswith('╰')]
            if borders and borders[0] >= 18:
                content = content[:3] + content[borders[0]:]
        
        visible = content[-(height - 1):]
        prompt_row = len(visible)
        if self.compose:
            visible = self.compose(visible, width, height - 1)
        frame = []
        for line in visible:
            clean = SGR.sub('', line)
            if width < 84 and clean.startswith(('╭', '│', '╰')):
                closing = {'╭': '╮', '│': '│', '╰': '╯'}[clean[0]]
                line = clip_line(line, width - 1) + closing
            frame.append(clip_line(line, width))
        frame += ['\x1b[0m'] * (height - len(frame))
        commands = ['\x1b[?25l']
        if resized:
            commands.append('\x1b[0m\x1b[2J\x1b[H')
            self.previous = []
        for row, line in enumerate(frame):
            if row >= len(self.previous) or line != self.previous[row]:
                commands.append(f'\x1b[{row + 1};1H\x1b[2K' + line)
        if prompt is not None:
            clean = SGR.sub('', prompt)
            length = sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1 for ch in clean)
            commands.append(f'\x1b[{prompt_row};{min(width, length + 1)}H\x1b[?25h')
        self.output.write(''.join(commands))
        self.output.flush()
        self.previous = frame
        self.last_size = dimensions
        self.last_paint = time.monotonic()

    def ask(self, prompt):
        
        
        answer = []
        self.paint(prompt)
        if os.name == 'nt':
            import msvcrt
            get_key = msvcrt.getwch
            restore = None
        else:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            tty.setraw(fd)
            get_key = lambda: sys.stdin.read(1)
            restore = lambda: termios.tcsetattr(fd, termios.TCSADRAIN, old)
        try:
            while True:
                char = get_key()
                if char in ('\r', '\n'):
                    return ''.join(answer)
                if char == '\x03':
                    raise KeyboardInterrupt
                if char == '\x04' and not answer:
                    raise EOFError
                if char in ('\x00', '\xe0') and os.name == 'nt':
                    get_key()  
                    continue
                if char in ('\b', '\x7f'):
                    if answer:
                        answer.pop()
                elif char >= ' ' and char != '\x7f':
                    answer.append(char)
                self.paint(prompt + ''.join(answer))
        finally:
            self.active_prompt = None
            if restore:
                restore()
            self.output.write('\x1b[?25l')
            self.output.flush()
