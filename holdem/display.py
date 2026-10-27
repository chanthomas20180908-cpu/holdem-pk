"""Pure text rendering of a filtered player view, never the private state."""
import unicodedata

STREETS = dict(preflop='翻牌前', flop='翻牌', turn='转牌', river='河牌')
SUITS = dict(s='♠', h='♥', d='♦', c='♣')


def cards(values):
    return ' / '.join(f'{"10" if c[0] == "T" else c[0]} {SUITS[c[1]]}' for c in values) or '未发'


def pad(value, width):
    text = str(value)
    size = sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in text)
    return text + ' ' * max(0, width - size)


def event_text(e, players):
    name = players[e['seat']]['name'] if 'seat' in e else ''
    kind = e['kind']
    if kind == 'blind': return f'{name}下{e["label"]} {e["paid"]}'
    if kind == 'action':
        action = e['action']
        if action == 'fold': result = f'{name}弃牌'
        elif action == 'check' or (action == 'call' and not e['paid']): result = f'{name}过牌'
        elif action == 'call': result = f'{name}跟注 {e["paid"]}（本轮累计 {e["bet"]}）'
        elif e['opening']: result = f'{name}下注 {e["paid"]}'
        else: result = f'{name}加注到 {e["bet"]}（本次投入 {e["paid"]}）'
        if e['all_in']: result += ' [全押]'
        return result
    if kind == 'round_end': return f'本轮结束：底池 {e["pot"]}'
    if kind == 'deal': return f'发牌：{cards(e["cards"])}'
    if kind == 'refund': return f'未被跟注的 {e["amount"]} 退回{name}'
    return None


def render(v, seat=0):
    players = v['players']
    turn = v['turn']
    line = '═' * 66
    out = [line, f'第 {v["hand"]} 手 · {STREETS[v["street"]]} · ' + ('已结束' if v['done'] else f'当前行动：{players[turn]["name"]}'),
           f'模式：{"老赌鬼" if v.get("mode", "standard") == "gambler" else "标准"}',
           f'盲注 5 / 10    庄位：{players[v["button"]]["name"]}', line,
           f'公共牌    {cards(v["board"])}', f'你的底牌  {cards(players[seat].get("hole", []))}',
           f'底池：{v["pot"]}' + (f'    当前玩家跟注需付：{v["legal"]["call"]}' if not v['done'] else ''), '']
    rows = [['玩家', '位置', '状态', '剩余筹码', '本轮下注', '本手投入']]
    positions = v.get('positions', {'button': v['button']})
    for i, p in enumerate(players):
        pos = '/'.join(label for key, label in [('button','庄位'),('small_blind','小盲'),('big_blind','大盲')] if positions.get(key) == i) or '—'
        status = '已弃牌' if p['folded'] else ('已结束' if v['done'] else ('全押' if p['stack'] == 0 else ('待行动' if i == turn else '等待')))
        rows.append([('→ ' if i == turn else '  ') + p['name'], pos, status, p['stack'], p['bet'], p['total']])
    widths = [max(sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in str(row[i])) for row in rows) for i in range(6)]
    for row in rows:
        out.append(' '.join(pad(x, w) for x, w in zip(row[:-1], widths[:-1])) + ' ' + str(row[-1]))
    out += ['', '本手行动', '─' * 66]
    if not v.get('history_complete'):
        out.append('旧存档：历史明细不完整；以下原始记录不补算金额或阶段。')
        out.extend('  ' + x for x in v.get('log', []))
    street = None
    for e in v.get('events', []):
        if e['kind'] == 'settlement': continue
        if e['street'] != street:
            street = e['street']; out.append(STREETS[street])
        text = event_text(e, players)
        if text:
            suffix = f' · 底池 {e["pot"]}' if e['kind'] in ('action','blind') else ''
            out.append('  ' + text + suffix)
    if v['done']:
        out += ['', '本手结算']
        if 'pots' in v:
            for n, pot in enumerate(v['pots']):
                out.append(f'  {"主池" if n == 0 else "边池 " + str(n)} {pot["amount"]} → ' + ' / '.join(f'{players[i]["name"]} +{pot["shares"].get(i, pot["shares"].get(str(i)))}' for i in pot['winners']))
        else: out.append('  旧存档没有底池分配及退款明细。')
        for i,p in enumerate(players):
            baseline = v.get('hand_start_stacks')
            initial = v.get('initial_stacks')
            hand = f'{p["stack"]-baseline[i]:+d}' if baseline else '未知'
            total = f'{p["stack"]-initial[i]:+d}' if initial else '未知'
            out.append(f'  {p["name"]}：本手 {hand} · 累计 {total} · 筹码 {p["stack"]}')
            if 'hole' in p and not p['folded'] and sum(not q['folded'] for q in players) > 1:
                out.append(f'    摊牌：{cards(p["hole"])}')
        out.append('本手结束，等待确认下一手。')
    else:
        opts = v['legal']; p = players[turn]
        choices = ['弃牌', '过牌' if opts['check'] else f'跟注 {opts["call"]}']
        cap, minimum = opts['raise_to_max'], opts['raise_to_min']
        if cap is not None:
            if cap >= minimum: choices.append(f'{"下注" if p["bet"] == 0 and opts["check"] else "加注到"} {minimum}–{cap}')
            choices.append(f'全押（本次投入 {p["stack"]}，本轮累计 {cap}）')
        elif opts['call'] == p['stack']: choices[-1] += '（全押）'
        out += ['', f'{players[turn]["name"]}的操作：' + ' · '.join(choices)]
    return '\n'.join(out + [line])
