import contextlib
import io
from pathlib import Path
import shutil
import os
import ctypes
from rem_ui import Terminal, cells, shorten


def terminal_columns():

    if os.name == 'nt':
        class Coord(ctypes.Structure):
            _fields_ = [('X', ctypes.c_short), ('Y', ctypes.c_short)]
        class Rect(ctypes.Structure):
            _fields_ = [('Left', ctypes.c_short), ('Top', ctypes.c_short),
                        ('Right', ctypes.c_short), ('Bottom', ctypes.c_short)]
        class BufferInfo(ctypes.Structure):
            _fields_ = [('size', Coord), ('cursor', Coord), ('attributes', ctypes.c_ushort),
                        ('window', Rect), ('maximum', Coord)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetStdHandle.argtypes = [ctypes.c_ulong]
        kernel.GetStdHandle.restype = ctypes.c_void_p
        kernel.GetConsoleScreenBufferInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(BufferInfo)]
        kernel.GetConsoleScreenBufferInfo.restype = ctypes.c_int
        info = BufferInfo()
        
        for code in (-11, -10, -12):
            handle = kernel.GetStdHandle(code & 0xffffffff)
            if kernel.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
                return info.window.Right - info.window.Left + 1
    for fd in (1, 0, 2):
        try:
            return os.get_terminal_size(fd).columns
        except OSError:
            pass
    
    return 196


def capture(draw):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        draw()
    return stream.getvalue().splitlines()


def combine(left, right, width, gap=2):
    result = []
    for index in range(max(len(left), len(right))):
        first = left[index] if index < len(left) else ''
        second = right[index] if index < len(right) else ''
        result.append(first + ' ' * max(0, width - cells(first) + gap) + second)
    return result


def bar(percent, width=18):
    done = round(max(0, min(100, percent)) * width / 100)
    return '█' * done + '░' * (width - done)


def render_dashboard(width, color, system, settings, task, height=None):
    half = (width - 2) // 2
    small = Terminal(color=color, width=half)
    full = Terminal(color=color, width=width)
    for ui in (small, full):
        ui.interactive = False
    destination = Path(settings['output']).expanduser()
    while not destination.exists() and destination.parent != destination:
        destination = destination.parent
    try:
        disk = shutil.disk_usage(destination)
        used = (disk.total - disk.free) / disk.total * 100
        disk_line = f'{(disk.total - disk.free) / 2**30:.1f} / {disk.total / 2**30:.1f} GiB'
        disk_bar = f'{bar(used, 17)} {used:.0f}%'
    except OSError:
        disk_line, disk_bar = '读取失败', ''
    status = task['status'] if task.get('status') in ('下载中', '解析中') else '准备就绪 / Ready'
    left = capture(lambda: small.box('✿ System Info / 系统信息', [
        f'OS       : {system.get("os", "未知")}',
        f'User     : {system.get("user", "未知")}',
        f'Terminal : {system.get("terminal", "终端")}',
        f'Python   : {system.get("python", "未知")}',
        f'yt-dlp   : {system.get("yt-dlp", "未检测")}',
        f'FFmpeg   : {system.get("ffmpeg", "未检测")}',
        f'Path     : {settings["output"]}',
        (f'● Status : {status}', 'green'), '',
        ('─' * (half - 4), 'muted'),
        f'Disk     : {destination.anchor or destination}',
        disk_line, (disk_bar, 'blue')]))
    right = capture(lambda: small.box('✿ Rem Message / 今日一言', [
        ('「レムは、いつでも', 'pink'),
        ('  あなたのそばにいます。」', 'pink'), '',
        '慢慢来，雷姆会一直陪着你。',
        ('                 — レム', 'pink')], 'pink'))
    status_lines = [
        '',
        ('応援  ' + bar(100, 15) + ' 100%', 'pink'),
        '',
        ('癒し  ' + bar(100, 15) + ' 100%', 'blue'),
        '',
        ('元気  ' + bar(90, 15) + '  90%', 'green'),
    ]
    status_lines += [''] * max(0, len(left) - len(right) - len(status_lines) - 2)
    right += capture(lambda: small.box('✿ Rem Status / 蕾姆状态', status_lines))
    panels = combine(left, right, half)
    percent = task.get('percent', 0)
    queued = task.get('queue', [])
    task_lines = [
        (f'▶ {task.get("status", "空闲 / Idle")}', 'green'),
        task.get('title', '选择左侧下载功能，开始新的任务。'),
        (f'{bar(percent, max(12, width - 17))} {percent:.1f}%', 'blue'),
        f'已下载 : {task.get("downloaded", "—")} / {task.get("total", "—")}',
        f'速度   : {task.get("speed", "—")}    ETA : {task.get("eta", "—")}',
        f'画质   : {task.get("resolution", "—")}',
        f'格式   : {task.get("format", "—")}',
        f'保存   : {task.get("path", settings["output"])}',
        ('─' * (width - 4), 'muted'),
        f'队列 / Queue ({len(queued)})',
    ]
    task_lines += [f'[{i + 1}] {title}' for i, title in enumerate(queued[:3])] or [('暂无等待任务 · 当前为单任务下载', 'muted')]
    if task.get('notice'):
        task_lines += [(shorten(task['notice'], width - 4), 'yellow')]
    if height is not None:
        task_lines += [''] * max(0, height - len(panels) - len(task_lines) - 2)
    panels += capture(lambda: full.box('✿ Current Task / 下载任务', task_lines))
    return panels


def layout(ui, draw_left, system, settings, task):
    available = getattr(ui, 'dashboard_width', None) or terminal_columns() - 1
    interactive = ui.interactive
    original_width = ui.fixed_width
    ui.clear()
    ui.interactive = False
    ui.fixed_width = min(ui.width, 84)
    try:
        left = capture(draw_left)
    finally:
        ui.interactive = interactive
        ui.fixed_width = original_width
    left_width = max(map(cells, left), default=84)
    if available >= left_width + 80:
        right_width = min(left_width, available - left_width - 3)
        from rem_ui import ANSI
        last_border = max((index for index, line in enumerate(left)
                           if ANSI.sub('', line).startswith('╰')), default=len(left) - 1)
        right = render_dashboard(right_width, ui.color, system, settings, task,
                                 height=last_border - 1)
        print('\n'.join(combine(left, ['',''] + right, left_width, 3)))
    else:
        print('\n'.join(left))
        print('\n'.join(render_dashboard(min(84, available), ui.color, system, settings, task)))


def compose_page(left, width, height, color, system, settings, task):
    from rem_ui import ANSI
    from rem_screen import clip_line
    left_width = min(84, max(32, (width - 3) // 2)) if width >= 100 else width
    borders = [i for i, line in enumerate(left) if ANSI.sub('', line).startswith('╰')]
    if borders and borders[0] >= 18 and (height < len(left) or left_width < 76):
        from rem_portrait import rgb_sprite
        sprite_width = min(24, max(10, left_width // 3))
        grid = rgb_sprite(sprite_width)
        art_height = min(10, max(3, height - (len(left) - borders[0]) - 4))
        ui = Terminal(color=color, width=left_width)
        def header():
            rows = []
            for y in range(art_height):
                pixels = grid[min(len(grid) - 1, y * len(grid) // art_height)]
                art = ''.join(f'\x1b[48;2;{r};{g};{b}m \x1b[0m' for r, g, b in pixels) if color else '▓' * sprite_width
                caption = ['REM', 'Rem Terminal Assistant', 'レムにお任せください。'][y] if y < 3 else ''
                rows.append(art + ui.ink('  ' + shorten(caption, left_width - sprite_width - 6), 'blue'))
            interior = left_width - 4
            print(ui.ink('╭─ REM ' + '─' * max(0, interior - 5) + '╮'))
            for row in rows:
                print(ui.ink('│ ') + row + ' ' * max(0, interior - cells(row)) + ui.ink(' │'))
            print(ui.ink('╰' + '─' * (interior + 2) + '╯'))
        left = left[:2] + capture(header) + left[borders[0] + 1:]
    left = left[-height:]
    left = [clip_line(line, left_width - 1) + ANSI.sub('', line)[-1]
            if cells(line) > left_width and ANSI.sub('', line).startswith(('╭', '│', '╰'))
            else clip_line(line, left_width) for line in left]
    if width < 100:
        ui = Terminal(color=color, width=width)
        compact = capture(lambda: ui.box('System Info / Current Task', [
            f'Python {system.get("python", "—")} · yt-dlp {system.get("yt-dlp", "—")}',
            f'{task.get("status", "Ready")}  {task.get("percent", 0):.1f}%',
            f'保存 : {task.get("path", settings["output"])}']))
        if len(left) + len(compact) <= height:
            return left[:-1] + compact + left[-1:]
        return left[:max(0, height - len(compact) - 1)] + compact + left[-1:]
    right_width = min(left_width, width - left_width - 3)
    
    last_border = max((index for index, line in enumerate(left)
                       if ANSI.sub('', line).startswith('╰')), default=30)
    if right_width < 70 or height < 31:
        ui = Terminal(color=color, width=right_width)
        right = ['', ''] + capture(lambda: ui.box('System Info / 系统信息', [
            f'Python : {system.get("python", "—")}',
            f'yt-dlp : {system.get("yt-dlp", "—")}',
            f'Path : {settings["output"]}']))
        right += capture(lambda: ui.box('Rem Status / 蕾姆状态', [('応援 100% · 癒し 100% · 元気 90%', 'pink')]))
        right += capture(lambda: ui.box('Current Task / 下载任务', [
            task.get('status', '空闲 / Idle'), task.get('title', '等待下载'),
            (f'{bar(task.get("percent", 0), max(4, right_width - 15))} {task.get("percent", 0):.1f}%', 'blue'),
            f'速度 : {task.get("speed", "—")} ETA : {task.get("eta", "—")}',
            f'保存 : {task.get("path", settings["output"])}']))
    else:
        right = ['', ''] + render_dashboard(right_width, color, system, settings, task,
                                           height=min(last_border - 1, height - 2))
    return combine([clip_line(line, left_width) for line in left], right,
                   left_width, 3)[:height]
