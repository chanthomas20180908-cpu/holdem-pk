"""Read-only ANSI table renderer. Accepts filtered views, never raw state."""
import os
import re
import unicodedata

from .display import STREETS, cards, details, render as plain

ANSI = re.compile(r'\x1b\[[0-9;]*m')
CARD = re.compile(r'(?:10|[2-9TJQKA]) [♠♥♦♣]')
SUIT_COLORS = {'♠': '39', '♥': '91', '♦': '94', '♣': '92'}


def cell_width(text):
    return sum(0 if unicodedata.combining(c) else
               2 if unicodedata.east_asian_width(c) in 'WF' else 1
               for c in ANSI.sub('', str(text)))


def paint(text, code, color):
    return f'\033[{code}m{text}\033[0m' if color else text


def use_color(mode, stream):
    if mode != 'auto':
        return mode == 'always'
    return stream.isatty() and os.environ.get('TERM') != 'dumb' and 'NO_COLOR' not in os.environ


def card_colors(text, color):
    return CARD.sub(lambda m: paint(m[0], SUIT_COLORS[m[0][-1]], color), text)


def wrap(text, width):
    """Wrap unstyled content by terminal columns before applying ANSI."""
    lines, line, size = [], '', 0
    for c in re.findall(r'(?:10|[2-9TJQKA]) [♠♥♦♣]|[^\n]|\n', text):
        n = cell_width(c)
        if c == '\n' or size + n > width:
            lines.append(line)
            line, size = '', 0
        if c != '\n':
            line += c
            size += n
    lines.append(line)
    return lines


def box(title, lines, width, color=False, accent='90'):
    inner = width - 4
    title = title + ' '
    out = ['┌─ ' + title + '─' * max(0, width - cell_width(title) - 4) + '┐']
    for line in lines:
        for part in wrap(line, inner):
            out.append('│ ' + card_colors(part, color) + ' ' * (inner - cell_width(part)) + ' │')
    out.append('└' + '─' * (width - 2) + '┘')
    # Color only the frame, preserving independently colored cards.
    out[0], out[-1] = (paint(out[i], accent, color) for i in (0, -1))
    return out


def join_blocks(blocks, gap=2):
    widths = [max(map(cell_width, block)) for block in blocks]
    return [(' ' * gap).join((block[row] if row < len(block) else '') +
                            ' ' * (width - cell_width(block[row]) if row < len(block) else width)
                            for block, width in zip(blocks, widths)).rstrip()
            for row in range(max(map(len, blocks)))]


def render(v, seat=0, *, width=100, color=False):
    if width < 40:
        return '窗口不足 40 列，使用纯文本牌桌。\n' + plain(v, seat)
    players = v['players']
    positions = v.get('positions', {'button': v['button']})

    def player(i, size):
        p = players[i]
        acting = not v['done'] and v['turn'] == i
        sitting_out = p['stack'] == 0 and p['total'] == 0 and not p.get('hole')
        status = ('坐出' if sitting_out else '已弃牌' if p['folded'] else
                  '已结束' if v['done'] else '全押' if p['stack'] == 0 else
                  '▶ 行动中' if acting else '等待')
        pos = ' / '.join(label for key, label in [('button', '庄位'), ('small_blind', '小盲'),
                                                ('big_blind', '大盲')] if positions.get(key) == i)
        name = p['name'] if i != 0 or p['name'] == '你' else p['name'] + '（你）'
        title = f'{i} {name}' + (' · 观察视角' if i == seat and seat != 0 else '')
        hole = ' / '.join('[' + cards([c]) + ']' for c in p['hole']) if p.get('hole') else '[▒▒] / [▒▒]' if not sitting_out else '—'
        return box(title, [status + (' · ' + pos if pos else ''), f'筹码 {p["stack"]}',
                           f'本轮 {p["bet"]} · 本手 {p["total"]}', hole], size, color,
                   '96' if acting else '93' if status == '全押' else '90')

    heading = f'第 {v["hand"]} 手 · {STREETS[v["street"]]} · ' + ('已结束' if v['done'] else '进行中')
    out = [paint('━' * width, '90', color), paint('  HOLD’EM  /  ' + {6: '六人', 8: '八人'}.get(len(players), str(len(players)) + '人') + '牌室', '1;96', color),
           *wrap(f'  {heading}    盲注 5 / 10', width),
           *wrap('模式：' + ('老赌鬼' if v.get('mode', 'standard') == 'gambler' else '标准'), width), '']
    board = [cards([c]) for c in v['board']] + ['·'] * (5 - len(v['board']))

    def center(size):
        # Each visible card has its own small frame; unfilled slots remain explicit.
        card_row = ' / '.join('[' + c + ']' for c in board)
        action = '等待确认下一手' if v['done'] else f'当前行动：{players[v["turn"]]["name"]}'
        return box('公共牌', [card_row, '', f'底池：{v["pot"]}', action], size, color, '96')

    order = [(seat + n) % len(players) for n in range(len(players))]
    if width >= 120 and len(players) == 6:
        size = (width - 4) // 3
        blank = [' ' * size]
        out += join_blocks([blank, player(order[3], size), blank]) + ['']
        out += join_blocks([player(order[2], size), center(size), player(order[4], size)]) + ['']
        out += join_blocks([player(order[1], size), player(order[0], size), player(order[5], size)])
    else:
        out += center(width) + ['']
        columns = 2 if width >= 80 else 1
        size = (width - (columns - 1) * 2) // columns
        # Observer gets the final, clearly separated panel.
        order = order[1:] + order[:1]
        for offset in range(0, len(order), columns):
            out += join_blocks([player(i, size) for i in order[offset:offset + columns]]) + ['']
    for line in details(v):
        # Existing renderer supplies all event/settlement semantics.
        for part in wrap(line, width):
            part = card_colors(part, color)
            if line in STREETS.values() or line in ('本手行动', '本手结算'):
                part = paint(part, '1;96', color)
            else:
                part = re.sub(r'(?<!\w)[+-]\d+', lambda m: paint(m[0], '92' if m[0][0] == '+' else '91', color), part)
            out.append(part)
    out.append(paint('━' * width, '90', color))
    return '\n'.join(out)
