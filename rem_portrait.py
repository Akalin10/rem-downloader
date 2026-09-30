"""Small native pixel sprite, rendered as true-color terminal half blocks."""
import json
from pathlib import Path
from functools import lru_cache

WIDTH, HEIGHT = 40, 46
PALETTE = {
    '.': (4, 14, 22), 'o': (22, 39, 63), 'h': (49, 99, 160),
    'b': (77, 157, 224), 'l': (118, 198, 249), 'a': (180, 229, 255),
    's': (255, 224, 211), 't': (232, 181, 180), 'c': (247, 161, 185),
    'w': (241, 245, 255), 'g': (171, 192, 220), 'p': (229, 141, 194),
    'r': (146, 70, 124), 'k': (12, 24, 40),
}


def sprite():
    grid = [['.'] * WIDTH for _ in range(HEIGHT)]

    def pixel(x, y, color):
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            grid[y][x] = color

    def rect(x0, y0, x1, y1, color):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                pixel(x, y, color)

    def ellipse(cx, cy, rx, ry, color):
        for y in range(max(0, int(cy - ry)), min(HEIGHT, int(cy + ry) + 1)):
            for x in range(max(0, int(cx - rx)), min(WIDTH, int(cx + rx) + 1)):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                    pixel(x, y, color)

    def poly(points, color):
        for y in range(HEIGHT):
            for x in range(WIDTH):
                inside = False
                previous = points[-1]
                for current in points:
                    x1, y1 = previous
                    x2, y2 = current
                    if (y1 > y + 0.5) != (y2 > y + 0.5):
                        cross = (x2 - x1) * (y + 0.5 - y1) / (y2 - y1) + x1
                        if x + 0.5 < cross:
                            inside = not inside
                    previous = current
                if inside:
                    pixel(x, y, color)

    # Silhouette and maid bodice.
    poly([(10, 41), (11, 36), (16, 32), (24, 32), (30, 36), (32, 41)], 'o')
    poly([(12, 41), (13, 36), (18, 33), (24, 33), (29, 37), (30, 41)], 'w')
    poly([(16, 41), (16, 36), (20, 35), (25, 36), (26, 41)], 'k')
    rect(18, 30, 23, 35, 't')
    rect(19, 30, 23, 34, 's')
    # Short blue bob and face.
    ellipse(20, 19, 16, 17, 'o')
    ellipse(20, 18, 15, 16, 'h')
    ellipse(19, 16, 14, 14, 'b')
    ellipse(20, 21, 10, 11, 't')
    ellipse(20, 20, 10, 11, 's')
    ellipse(29, 23, 2, 3, 't')
    # Exposed eye, lashes, iris and highlights.
    poly([(23, 20), (24, 18), (28, 18), (30, 20), (29, 24), (24, 24)], 'o')
    ellipse(26, 21, 3, 3, 'w')
    ellipse(27, 21, 2, 3, 'h')
    rect(26, 21, 28, 23, 'b')
    rect(27, 21, 27, 22, 'o')
    pixel(26, 19, 'w')
    pixel(28, 23, 'a')
    rect(24, 18, 28, 18, 'o')
    pixel(29, 17, 'o')
    rect(24, 16, 27, 16, 't')
    rect(27, 25, 29, 25, 'c')
    rect(15, 25, 17, 25, 'c')
    pixel(22, 25, 't')
    rect(21, 28, 23, 28, 't')
    pixel(22, 29, 'w')
    # Layered bangs cover the other eye. Separate strands carry highlights.
    poly([(9, 7), (27, 5), (23, 13), (20, 21), (18, 28), (16, 26), (11, 29), (7, 25)], 'b')
    poly([(11, 7), (17, 6), (12, 24), (9, 28), (8, 23)], 'l')
    poly([(17, 6), (21, 5), (16, 23), (12, 28)], 'l')
    poly([(22, 6), (25, 6), (20, 22), (18, 25)], 'l')
    poly([(13, 8), (14, 8), (11, 21), (10, 22)], 'a')
    poly([(19, 8), (20, 8), (16, 22), (15, 23)], 'a')
    poly([(25, 7), (30, 9), (32, 19), (30, 24), (29, 15), (25, 12)], 'l')
    poly([(31, 12), (34, 17), (33, 29), (29, 33), (30, 27)], 'b')
    rect(32, 19, 32, 27, 'l')
    poly([(5, 16), (7, 11), (7, 26), (11, 32), (7, 30), (4, 25)], 'h')
    rect(6, 18, 6, 25, 'b')
    # Curved black headband with white lace clusters.
    poly([(8, 8), (10, 4), (17, 1), (24, 1), (30, 4), (33, 9), (30, 8), (26, 5), (17, 4), (11, 7)], 'k')
    for x, y in [(10, 5), (14, 3), (18, 2), (22, 2), (26, 3), (30, 5)]:
        ellipse(x, y, 2, 2, 'g')
        rect(x - 1, y - 1, x + 1, y + 1, 'w')
        pixel(x, y + 2, 'w')
        pixel(x, y, 'a')
    # Pink crossed hairpins and side flower ribbon.
    for i in range(5):
        pixel(30 + i, 12 + i, 'p')
        pixel(34 - i, 12 + i, 'p')
    for x, y in [(34, 9), (36, 11), (34, 13), (32, 11)]:
        ellipse(x, y, 1, 1, 'p')
    pixel(34, 11, 'w')
    poly([(34, 15), (36, 17), (35, 27), (33, 29)], 'r')
    rect(35, 18, 35, 25, 'p')
    # Frilled white collar, black bow and apron accents.
    poly([(16, 33), (20, 35), (18, 38), (14, 35)], 'w')
    poly([(24, 33), (20, 35), (23, 38), (27, 35)], 'w')
    poly([(17, 35), (20, 36), (17, 38)], 'o')
    poly([(23, 35), (20, 36), (24, 38)], 'o')
    pixel(20, 36, 'p')
    rect(13, 38, 14, 41, 'g')
    rect(27, 38, 28, 41, 'g')
    pixel(20, 39, 'w')
    # A pair of small petals outside the silhouette.
    pixel(2, 9, 'p')
    pixel(1, 10, 'p')
    pixel(3, 10, 'p')
    pixel(2, 11, 'p')
    pixel(37, 30, 'p')
    pixel(36, 31, 'p')
    pixel(38, 31, 'p')
    pixel(37, 32, 'p')
    return grid


@lru_cache(maxsize=3)
def rgb_sprite(width=WIDTH):
    try:
        data = json.loads(Path(__file__).with_name('rem_portrait_rgb.json').read_text(encoding='utf-8'))
        return data[str(width)]['pixels']
    except (OSError, ValueError, KeyError):
        original = sprite()
        height = round(len(original) * width / WIDTH / 2) * 2
        return [[PALETTE[original[min(len(original) - 1, y * len(original) // height)]
                        [min(WIDTH - 1, x * WIDTH // width)]] for x in range(width)] for y in range(height)]


def rows(color=True, width=WIDTH):
    if color and width == 32:
        try:
            data = json.loads(Path(__file__).with_name('rem_portrait_rgb.json').read_text(encoding='utf-8'))
            return quadrant_rows(data['32_quadrants']['pixels'])
        except (OSError, ValueError, KeyError):
            pass
    grid = rgb_sprite(width)
    result = []
    for y in range(0, len(grid), 2):
        line = ''
        for x in range(len(grid[0])):
            top, bottom = grid[y][x], grid[y + 1][x]
            if color:
                fg = ';'.join(map(str, top))
                bg = ';'.join(map(str, bottom))
                line += f'\x1b[38;2;{fg};48;2;{bg}m▀'
            else:
                bg = list(PALETTE['.'])
                top_empty, bottom_empty = list(top) == bg, list(bottom) == bg
                line += ' ' if top_empty and bottom_empty else '▀' if bottom_empty else '▄' if top_empty else '█'
        result.append(line + ('\x1b[0m' if color else ''))
    return result


QUADRANTS = ' ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█'


def quadrant_rows(grid):
    """Encode four subpixels with two colors, keeping the same terminal footprint."""
    def distance(a, b):
        return sum(weight * (x - y) ** 2 for weight, x, y in zip((0.3, 0.59, 0.11), a, b))
    def average(group):
        return [round(sum(c[i] for c in group) / len(group)) for i in range(3)]
    result = []
    for y in range(0, len(grid), 2):
        line = ''
        for x in range(0, len(grid[0]), 2):
            colors = [grid[y][x], grid[y][x + 1], grid[y + 1][x], grid[y + 1][x + 1]]
            # Exhaustively evaluate all distinct two-color partitions instead of
            # letting one outlier choose the colors for the whole terminal cell.
            best = None
            for candidate in range(1, 8):
                groups = [[color for i, color in enumerate(colors) if bool(candidate & (1 << i)) == foreground]
                          for foreground in (True, False)]
                first, second = map(average, groups)
                error = sum(distance(color, first if candidate & (1 << i) else second)
                            for i, color in enumerate(colors))
                if best is None or error < best[0]:
                    best = error, candidate, first, second
            _, mask, first, second = best
            fg = ';'.join(map(str, first))
            bg = ';'.join(map(str, second))
            line += f'\x1b[38;2;{fg};48;2;{bg}m{QUADRANTS[mask]}'
        result.append(line + '\x1b[0m')
    return result
