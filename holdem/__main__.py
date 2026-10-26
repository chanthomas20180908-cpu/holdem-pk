"""Local poker tools. No model client or third-party dependencies."""
import argparse
import itertools
import json
import random
from collections import Counter
from pathlib import Path

STATE = Path('.holdem/state.json')
RANKS = '23456789TJQKA'


def score(cards):
    def five(hand):
        counts = Counter(RANKS.index(c[0]) + 2 for c in hand)
        groups = sorted(((n, r) for r, n in counts.items()), reverse=True)
        ranks = sorted(counts, reverse=True)
        flush = len({c[1] for c in hand}) == 1
        straight = 5 if ranks == [14, 5, 4, 3, 2] else (ranks[0] if len(ranks) == 5 and ranks[0] - ranks[-1] == 4 else 0)
        if flush and straight: return (8, straight)
        if groups[0][0] == 4: return (7, groups[0][1], groups[1][1])
        if [g[0] for g in groups] == [3, 2]: return (6, groups[0][1], groups[1][1])
        if flush: return (5, *ranks)
        if straight: return (4, straight)
        if groups[0][0] == 3: return (3, groups[0][1], *sorted((r for r in ranks if r != groups[0][1]), reverse=True))
        pairs = sorted((r for n, r in groups if n == 2), reverse=True)
        if len(pairs) == 2: return (2, *pairs, next(r for r in ranks if r not in pairs))
        if pairs: return (1, pairs[0], *[r for r in ranks if r != pairs[0]])
        return (0, *ranks)
    return max(map(five, itertools.combinations(cards, 5)))


def record(s, kind, **fields):
    s.setdefault('events', []).append(dict(kind=kind, street=s.get('street', 'preflop'),
        pot=sum(p.get('total', 0) for p in s['players']), **fields))


def pay(s, i, amount):
    p = s['players'][i]
    amount = min(amount, p['stack'])
    p['stack'] -= amount
    p['bet'] += amount
    p['total'] += amount


def active(s):
    return [i for i, p in enumerate(s['players']) if not p['folded']]


def actionable(s):
    return [i for i in active(s) if s['players'][i]['stack'] > 0]


def next_seat(s, after, seats):
    count = len(s['players'])
    return next((after + d) % count for d in range(1, count + 1) if (after + d) % count in seats)


def start_hand(s):
    if sum(p['stack'] > 0 for p in s['players']) < 2:
        raise ValueError('不足两名有筹码玩家，请 new 开始新场次')
    s.setdefault('initial_stacks', [1000] * len(s['players']))
    s['hand_start_stacks'] = [p['stack'] for p in s['players']]
    s['hand'] += 1
    seats = [i for i, p in enumerate(s['players']) if p['stack'] > 0]
    s['button'] = next_seat(s, s['button'], seats)
    deck = [r + suit for r in RANKS for suit in 'shdc']
    random.SystemRandom().shuffle(deck)
    s.update(deck=deck, board=[], street='preflop', current=10, min_raise=10, log=[], events=[], history_complete=True, done=False, acted=[])
    for p in s['players']:
        p.update(hole=[deck.pop(), deck.pop()] if p['stack'] else [], folded=p['stack'] == 0, bet=0, total=0)
    sb = s['button'] if len(seats) == 2 else next_seat(s, s['button'], seats)
    bb = next_seat(s, sb, seats)
    s['positions'] = {'button': s['button'], 'small_blind': sb, 'big_blind': bb}
    for i, amount, label in [(sb, 5, '小盲'), (bb, 10, '大盲')]:
        pay(s, i, amount)
        record(s, 'blind', seat=i, label=label, paid=s['players'][i]['bet'], bet=s['players'][i]['bet'])
    s['pending'] = actionable(s)
    s['turn'] = next_seat(s, bb, s['pending']) if s['pending'] else None
    advance(s, bb)


def settle(s):
    live = active(s)
    refunds = [0] * len(s['players'])
    pots = []
    previous = 0
    for level in sorted({p['total'] for p in s['players'] if p['total']}):
        contributors = [i for i, p in enumerate(s['players']) if p['total'] >= level]
        amount = (level - previous) * len(contributors)
        eligible = [i for i in live if s['players'][i]['total'] >= level]
        if len(contributors) == 1:
            refunds[contributors[0]] += amount
        elif pots and pots[-1]['eligible'] == eligible:
            pots[-1]['amount'] += amount
        else:
            pots.append(dict(amount=amount, eligible=eligible))
        previous = level
    awards = refunds[:]
    for pot in pots:
        eligible = pot['eligible']
        if len(live) == 1:
            winners = live
        else:
            values = {i: score(s['players'][i]['hole'] + s['board']) for i in eligible}
            best = max(values.values())
            winners = [i for i in eligible if values[i] == best]
        order = sorted(winners, key=lambda i: (i - s['button'] - 1) % len(s['players']))
        shares = {i: pot['amount'] // len(order) + (n < pot['amount'] % len(order)) for n,i in enumerate(order)}
        pot.update(winners=order, shares=shares)
        for i, amount in shares.items(): awards[i] += amount
    for i, amount in enumerate(awards): s['players'][i]['stack'] += amount
    s.update(done=True, turn=None, awards=awards, refunds=refunds, pots=pots)
    for i, amount in enumerate(refunds):
        if amount: record(s, 'refund', seat=i, amount=amount)
    record(s, 'settlement', pots=pots, awards=awards, refunds=refunds)
    s['log'].append('结算：' + ', '.join(f'{s["players"][i]["name"]} +{v}' for i, v in enumerate(awards) if v))


def advance(s, after):
    while True:
        if len(active(s)) == 1:
            settle(s)
            return
        s['pending'] = [i for i in s['pending'] if i in actionable(s)]
        actors = actionable(s)
        if len(actors) <= 1:
            s['pending'] = [i for i in actors if s['players'][i]['bet'] < s['current']]
        if s['pending']:
            s['turn'] = next_seat(s, after, s['pending'])
            return
        record(s, 'round_end')
        if s['street'] == 'river':
            settle(s)
            return
        s['street'] = {'preflop': 'flop', 'flop': 'turn', 'turn': 'river'}[s['street']]
        s['deck'].pop()  # burn
        s['board'].extend(s['deck'].pop() for _ in range(3 if s['street'] == 'flop' else 1))
        record(s, 'deal', cards=s['board'][:])
        for p in s['players']: p['bet'] = 0
        s.update(current=0, min_raise=10, acted=[], pending=actionable(s))
        after = s['button']


def legal(s):
    if s['done']: return {}
    i = s['turn']
    p = s['players'][i]
    call = min(p['stack'], max(0, s['current'] - p['bet']))
    cap = p['bet'] + p['stack']
    can_raise = i not in s['acted'] and len(actionable(s)) > 1 and cap > s['current']
    return dict(fold=True, check=call == 0, call=call, raise_to_min=s['current'] + s['min_raise'] if can_raise else None, raise_to_max=cap if can_raise else None)


def act(s, seat, action, amount=None):
    if s['done'] or seat != s['turn']: raise ValueError('不是该座位行动')
    p = s['players'][seat]
    options = legal(s)
    before_stack, before_current = p['stack'], s['current']
    if action == 'fold': p['folded'] = True
    elif action == 'check':
        if not options['check']: raise ValueError('需跟注，不能过牌')
    elif action == 'call': pay(s, seat, options['call'])
    elif action == 'raise':
        cap = options['raise_to_max']
        if cap is None or amount is None or amount > cap or amount <= s['current']:
            raise ValueError('加注金额不合法或未重新开放加注')
        if amount < options['raise_to_min'] and amount != cap: raise ValueError('低于最小加注，只有全押可例外')
        delta = amount - s['current']
        if delta >= s['min_raise']:
            s['min_raise'] = delta
            s['acted'] = []
        pay(s, seat, amount - p['bet'])
        s['current'] = amount
        s['pending'] = [i for i in actionable(s) if i != seat and s['players'][i]['bet'] < amount]
    else: raise ValueError('未知动作')
    if seat in s['pending']: s['pending'].remove(seat)
    if seat not in s['acted']: s['acted'].append(seat)
    s['log'].append(f'{p["name"]}: {action}' + (f' to {amount}' if amount is not None else ''))
    record(s, 'action', seat=seat, action=action, paid=before_stack-p['stack'],
        bet=p['bet'], opening=before_current == 0, all_in=p['stack'] == 0 and action != 'fold')
    advance(s, seat)


def view(s, seat):
    if not 0 <= seat < len(s['players']): raise ValueError('该座位尚未入桌')
    result = dict(hand=s['hand'], button=s['button'], street=s['street'], board=s['board'], pot=sum(p['total'] for p in s['players']) if not s['done'] else 0, turn=s['turn'], done=s['done'], players=[{k: v for k, v in p.items() if k != 'hole' or i == seat or (s['done'] and not p['folded'] and len(active(s)) > 1)} for i, p in enumerate(s['players'])], legal=legal(s), log=s['log'])
    for key in ['events', 'positions', 'initial_stacks', 'hand_start_stacks', 'awards', 'refunds', 'pots']:
        if key in s: result[key] = s[key]
    result['history_complete'] = s.get('history_complete', False)
    # Awards from a previous hand must never appear in an active hand.
    if not s['done']:
        for key in ['awards', 'refunds', 'pots']: result.pop(key, None)
    return result


def expand(s):
    if not s['done']: raise ValueError('只能在本手结束后扩桌，不改变进行中的牌局')
    if len(s['players']) != 4: raise ValueError('仅支持已有四人桌扩为六人桌')
    s.setdefault('initial_stacks', [1000] * 4)
    s['initial_stacks'].extend([1000, 1000])
    for name in ['指南针', '闪电']:
        s['players'].append(dict(name=name, stack=1000, hole=[], folded=True, bet=0, total=0))
    if 'hand_start_stacks' in s: s['hand_start_stacks'].extend([1000,1000])
    for key in ['awards','refunds']:
        if key in s: s[key].extend([0,0])
    s['log'].append('扩为六人桌：指南针、闪电各买入 1000；从下一手参与')


def main():
    global STATE
    parser = argparse.ArgumentParser(description='多人德扑工具；座位 0 是用户，其余是 Agent 对手')
    parser.add_argument('--state', type=Path, default=STATE, help='存档路径，默认 .holdem/state.json')
    sub = parser.add_subparsers(dest='cmd', required=True)
    n = sub.add_parser('new')
    n.add_argument('--players', type=int, choices=[6, 8], default=6)
    rename = sub.add_parser('rename', help='修改当前桌全部对手昵称，保留牌局进度')
    rename.add_argument('names', nargs='+')
    sub.add_parser('next')
    sub.add_parser('expand', help='已结束的四人桌扩为六人桌')
    t = sub.add_parser('table', help='显示文本牌桌（只读，默认用户视角）')
    t.add_argument('--seat', type=int, choices=range(8), default=0)
    v = sub.add_parser('view'); v.add_argument('--seat', type=int, choices=range(8), default=0)
    a = sub.add_parser('act'); a.add_argument('--seat', type=int, required=True, choices=range(8)); a.add_argument('action', choices=['fold', 'check', 'call', 'raise']); a.add_argument('--to', type=int)
    args = parser.parse_args()
    STATE = args.state
    try:
        if args.cmd == 'new':
            if STATE.exists(): raise ValueError('已有存档；请换工作目录开始新场次，避免覆盖')
            names = ['你', '岩石', '猎狐', '浪潮', '指南针', '闪电', '山猫', '远帆'][:args.players]
            s = dict(hand=0, button=len(names)-1, players=[dict(name=n, stack=1000) for n in names])
            start_hand(s)
        else:
            s = json.loads(STATE.read_text())
            if args.cmd == 'rename':
                names = [name.strip() for name in args.names]
                if len(names) != len(s['players']) - 1:
                    raise ValueError('请按座位顺序提供全部对手昵称')
                if any(not name or not name.isprintable() for name in names):
                    raise ValueError('昵称不能为空或包含控制字符')
                if len(set([s['players'][0]['name']] + names)) != len(s['players']):
                    raise ValueError('昵称不能重复')
                for player, name in zip(s['players'][1:], names):
                    player['name'] = name
            elif args.cmd == 'expand': expand(s)
            elif args.cmd == 'next':
                if not s['done']: raise ValueError('当前手牌尚未结束')
                start_hand(s)
            elif args.cmd == 'act': act(s, args.seat, args.action, args.to)
        if args.cmd not in ('view', 'table'):
            STATE.parent.mkdir(parents=True, exist_ok=True)
            temp = STATE.with_suffix('.tmp')
            temp.write_text(json.dumps(s, ensure_ascii=False, indent=2))
            temp.replace(STATE)
        visible = view(s, args.seat if args.cmd in ('view', 'table') else 0)
        if args.cmd == 'table':
            from .display import render
            print(render(visible, args.seat))
        else:
            print(json.dumps(visible, ensure_ascii=False, indent=2))
    except (ValueError, FileNotFoundError) as e:
        parser.exit(2, f'错误：{e}\n')


if __name__ == '__main__': main()
