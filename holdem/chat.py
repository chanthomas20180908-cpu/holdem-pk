"""Color-independent advanced table for chat; consumes filtered views only."""
from .display import STREETS, cards, details, render as plain
from .terminal import cell_width, join_blocks, wrap

PLAYER_ICONS = ('🧑', '🪨', '🦊', '🌊', '🧭', '⚡')
ACTION_ICONS = {'弃牌': '❌', '过牌': '✅', '跟注': '🤝', '下注': '🪙', '加注到': '⬆', '全押': '🔥'}


def operations(line):
    name, choices = line.split('：', 1)
    tagged = []
    for choice in choices.split(' · '):
        icon = next((icon for action, icon in ACTION_ICONS.items() if choice.startswith(action)), '')
        tagged.append(icon + ' ' + choice if icon else choice)
    return '🎮 ' + name + '：' + ' · '.join(tagged)


SUIT_NAMES = {'s': '黑桃', 'h': '红桃', 'd': '方块', 'c': '梅花'}


def frame(title, lines, width, kind='normal'):
    tl, tr, bl, br, h, v = {
        'normal': ('┌', '┐', '└', '┘', '─', '│'),
        'self': ('╔', '╗', '╚', '╝', '═', '║'),
        'acting': ('┏', '┓', '┗', '┛', '━', '┃'),
    }[kind]
    title_lines = wrap(title, width - 6)
    title = title_lines[0]
    out = [tl + h + ' ' + title + ' ' + h * (width - cell_width(title) - 5) + tr]
    for line in title_lines[1:] + lines:
        for part in wrap(line, width - 4):
            out.append(v + ' ' + part + ' ' * (width - 4 - cell_width(part)) + ' ' + v)
    return out + [bl + h * (width - 2) + br]


def card_blocks(values, available):
    """Six-column cards, with explicit suit names and atomic card faces."""
    blocks = []
    for value in values:
        face = cards([value]) if value else '·'
        label = SUIT_NAMES[value[1]] if value else '未发'
        blocks.append(['┌────┐', '│' + face + ' ' * (4 - cell_width(face)) + '│',
                       '│' + label + '│', '└────┘'])
    per_row = max(1, (available + 3) // 9)
    out = []
    for offset in range(0, len(blocks), per_row):
        group = blocks[offset:offset + per_row]
        for row in range(4):
            out.append((' / ' if row == 1 else '   ').join(block[row] for block in group))
        if offset + per_row < len(blocks):
            out.append('/')
    return out


def render(v, seat=0, *, width=120):
    if width < 40:
        return '窗口不足 40 列，使用纯文本牌桌。\n' + plain(v, seat)
    players = v['players']
    positions = v.get('positions', {'button': v['button']})
    stages = ' → '.join('〔' + name + '〕' if stage == v['street'] else name
                        for stage, name in STREETS.items())
    out = ['━' * width, '🎲 HOLD’EM / 对话高级牌桌',
           *wrap(f'第 {v["hand"]} 手 · {"已结束" if v["done"] else "进行中"} · 盲注 5 / 10 · 庄位：{players[v["button"]]["name"]}', width),
           *wrap(stages, width), '']

    def player(i, size):
        p = players[i]
        acting = not v['done'] and v['turn'] == i
        sitting_out = p['stack'] == 0 and p['total'] == 0 and not p.get('hole')
        status = ('💤 坐出' if sitting_out else '❌ 已弃牌' if p['folded'] else
                  '🏁 本手结束' if v['done'] else '🔥 全押' if p['stack'] == 0 else
                  '🟢 正在行动' if acting else '⌛ 等待')
        pos = ' / '.join(label for key, label in [('button', '庄位'), ('small_blind', '小盲'),
                                                ('big_blind', '大盲')] if positions.get(key) == i)
        title = f'{PLAYER_ICONS[i % len(PLAYER_ICONS)]} {i} · {p["name"]}' + ('（你）' if i == 0 and p['name'] != '你' else '')
        if i == seat and seat != 0:
            title += '〔观察视角〕'
        if pos:
            title += '〔' + pos + '〕'
        if acting:
            title = '▶ ' + title
        lines = [status, '', f'💰 剩余筹码  {p["stack"]}',
                 f'🪙 本轮下注  {p["bet"]}', f'📥 本手投入  {p["total"]}']
        if p.get('hole'):
            lines += ['', '🃏 ' + ('你的底牌' if i == 0 else '可见底牌'),
                      *card_blocks(p['hole'], size - 4)]
        elif not p['folded'] and not sitting_out:
            lines += ['🔒 底牌  [隐藏] / [隐藏]']
        return frame(title, lines, size, 'self' if i == 0 else 'acting' if acting else 'normal')

    def center(size):
        lines = card_blocks(list(v['board']) + [None] * (5 - len(v['board'])), size - 4)
        lines += ['', f'💰 底池  {v["pot"]}']
        if v['done']:
            lines += ['🏁 本手结束 · 等待确认下一手']
        else:
            lines += [f'🟢 当前行动：{players[v["turn"]]["name"]}']
            if v['turn'] == 0:
                lines += [f'🤝 跟注需付  {v["legal"]["call"]}']
        return frame('🃏 公共牌 · 翻牌 / 转牌 / 河牌', lines, size)

    order = [(seat + n) % len(players) for n in range(len(players))]
    if width >= 120 and len(players) == 6:
        side = (width - 50) // 2
        middle = width - 4 - 2 * side
        out += join_blocks([[' ' * side], player(order[3], middle), [' ' * side]]) + ['']
        out += join_blocks([player(order[2], side), center(middle), player(order[4], side)]) + ['']
        out += join_blocks([player(order[1], side), player(order[0], middle), player(order[5], side)])
    else:
        out += center(width) + ['']
        columns = 2 if width >= 80 else 1
        size = (width - (columns - 1) * 2) // columns
        ordered = order[1:] + order[:1]
        for offset in range(0, len(ordered), columns):
            out += join_blocks([player(i, size) for i in ordered[offset:offset + columns]]) + ['']
    history = details(v)
    if not v['done']:
        # Move the existing authoritative legal options above the full history.
        out += ['', *wrap(operations(history[-1]), width)]
        history = history[:-2]
    for line in history:
        if line == '本手行动':
            line = '📜 ' + line
        elif line == '本手结算':
            line = '🏆 ' + line
        elif line in STREETS.values():
            line = '🃏 ' + line
        else:
            for i in sorted(range(len(players)), key=lambda n: -len(players[n]['name'])):
                name = players[i]['name']
                if line.startswith('  ' + name):
                    line = '  ' + PLAYER_ICONS[i % len(PLAYER_ICONS)] + ' ' + line[2:]
                    break
        out.extend(wrap(line, width))
    out.append('━' * width)
    return '\n'.join(out)
