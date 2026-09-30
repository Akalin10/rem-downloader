"""Render the actual terminal strings for an offline preview (requires Pillow)."""
import contextlib
import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import download_cli as cli
from rem_ui import Terminal, cells
from rem_portrait import QUADRANTS


def main():
    ui = Terminal(color=True, width=100)
    ui.dashboard_width = 196
    ui.interactive = False
    cli.UI = ui
    output = io.StringIO()
    # Shareable previews must never include the current user's system metadata.
    settings = dict(cli.DEFAULTS, output='Downloads', cookies='')
    cli.SYSTEM_CACHE[(settings['backend'], settings['ffmpeg'])] = {
        'os': 'Windows', 'user': 'RemUser', 'terminal': 'Windows Terminal',
        'python': '3.10+', 'yt-dlp': 'Installed', 'ffmpeg': 'Installed'}
    with contextlib.redirect_stdout(output):
        cli.main_menu(settings)
    lines = output.getvalue().splitlines()
    cell, row, pad = 9, 18, 20
    image = Image.new('RGB', (196 * cell + pad * 2, len(lines) * row + pad * 2), '#040e16')
    draw = ImageDraw.Draw(image)
    latin = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 14)
    cjk = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 14)
    tokens = re.compile(r'(\x1b\[[0-9;]*m)')
    for y, line in enumerate(lines):
        column, color, background = 0, (195, 220, 235), (4, 14, 22)
        for token in tokens.split(line):
            if token.startswith('\x1b['):
                match = re.search(r'38;2;(\d+);(\d+);(\d+)', token)
                if match:
                    color = tuple(map(int, match.groups()))
                bgmatch = re.search(r'48;2;(\d+);(\d+);(\d+)', token)
                if bgmatch:
                    background = tuple(map(int, bgmatch.groups()))
                if token == '\x1b[0m':
                    color, background = (195, 220, 235), (4, 14, 22)
            else:
                for ch in token:
                    width = cells(ch)
                    font = cjk if width == 2 or ord(ch) > 0x2500 else latin
                    if ch in QUADRANTS and ch not in (' ', '█'):
                        mask = QUADRANTS.index(ch)
                        x0, y0 = pad + column * cell, pad + y * row
                        for index in range(4):
                            left = x0 + (index % 2) * cell // 2
                            top = y0 + (index // 2) * row // 2
                            right = x0 + ((index % 2) + 1) * cell // 2 - 1
                            bottom = y0 + ((index // 2) + 1) * row // 2 - 1
                            draw.rectangle((left, top, right, bottom), fill=color if mask & (1 << index) else background)
                    elif ch == '▀':
                        x0, y0 = pad + column * cell, pad + y * row
                        draw.rectangle((x0, y0, x0 + cell - 1, y0 + row // 2 - 1), fill=color)
                        draw.rectangle((x0, y0 + row // 2, x0 + cell - 1, y0 + row - 1), fill=background)
                    elif ch in ('█', '░'):
                        fill = color if ch == '█' else tuple(round(v * 0.25) for v in color)
                        draw.rectangle((pad + column * cell, pad + y * row + 4,
                                        pad + (column + 1) * cell - 1, pad + (y + 1) * row - 2), fill=fill)
                    elif ch != ' ':
                        draw.text((pad + column * cell, pad + y * row), ch, font=font, fill=color)
                    column += width
    target = Path(__file__).with_name('rem-theme-preview.png')
    image.save(target)
    print(target)


if __name__ == '__main__':
    main()
