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
    return next((after + d) % 4 for d in range(1, 5) if (after + d) % 4 in seats)


def start_hand(s):
    if sum(p['stack'] > 0 for p in s['players']) < 2:
        raise ValueError('不足两名有筹码玩家，请 new 开始新场次')
    s['hand'] += 1
    seats = [i for i, p in enumerate(s['players']) if p['stack'] > 0]
    s['button'] = next_seat(s, s['button'], seats)
    deck = [r + suit for r in RANKS for suit in 'shdc']
    random.SystemRandom().shuffle(deck)
    s.update(deck=deck, board=[], street='preflop', current=10, min_raise=10, log=[], done=False, acted=[])
    for p in s['players']:
        p.update(hole=[deck.pop(), deck.pop()] if p['stack'] else [], folded=p['stack'] == 0, bet=0, total=0)
    sb = s['button'] if len(seats) == 2 else next_seat(s, s['button'], seats)
    bb = next_seat(s, sb, seats)
    pay(s, sb, 5)
    pay(s, bb, 10)
    s['pending'] = actionable(s)
    s['turn'] = next_seat(s, bb, s['pending']) if s['pending'] else None
    advance(s, bb)


def settle(s):
    live = active(s)
    awards = [0] * 4
    previous = 0
    for level in sorted({p['total'] for p in s['players'] if p['total']}):
        contributors = [i for i, p in enumerate(s['players']) if p['total'] >= level]
        pot = (level - previous) * len(contributors)
        eligible = [i for i in live if s['players'][i]['total'] >= level]
        # An unmatched contribution is returned, including a folded contributor.
        if len(contributors) == 1:
            winners = contributors
        elif len(live) == 1:
            winners = live
        else:
            values = {i: score(s['players'][i]['hole'] + s['board']) for i in eligible}
            best = max(values.values())
            winners = [i for i in eligible if values[i] == best]
        order = sorted(winners, key=lambda i: (i - s['button'] - 1) % 4)
        for n, i in enumerate(order):
            awards[i] += pot // len(order) + (n < pot % len(order))
        previous = level
    for i, amount in enumerate(awards): s['players'][i]['stack'] += amount
    s.update(done=True, turn=None, awards=awards)
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
        if s['street'] == 'river':
            settle(s)
            return
        s['street'] = {'preflop': 'flop', 'flop': 'turn', 'turn': 'river'}[s['street']]
        s['deck'].pop()  # burn
        s['board'].extend(s['deck'].pop() for _ in range(3 if s['street'] == 'flop' else 1))
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
    advance(s, seat)


def view(s, seat):
    return dict(hand=s['hand'], button=s['button'], street=s['street'], board=s['board'], pot=sum(p['total'] for p in s['players']) if not s['done'] else 0, turn=s['turn'], done=s['done'], players=[{k: v for k, v in p.items() if k != 'hole' or i == seat or (s['done'] and not p['folded'] and len(active(s)) > 1)} for i, p in enumerate(s['players'])], legal=legal(s), log=s['log'])


def main():
    parser = argparse.ArgumentParser(description='四人德扑工具；座位 0 是用户，1–3 是 Agent 对手')
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('new')
    sub.add_parser('next')
    v = sub.add_parser('view'); v.add_argument('--seat', type=int, choices=range(4), default=0)
    a = sub.add_parser('act'); a.add_argument('--seat', type=int, required=True, choices=range(4)); a.add_argument('action', choices=['fold', 'check', 'call', 'raise']); a.add_argument('--to', type=int)
    args = parser.parse_args()
    try:
        if args.cmd == 'new':
            if STATE.exists(): raise ValueError('已有存档；请换工作目录开始新场次，避免覆盖')
            s = dict(hand=0, button=3, players=[dict(name=n, stack=1000) for n in ['你', '岩石', '猎狐', '浪潮']])
            start_hand(s)
        else:
            s = json.loads(STATE.read_text())
            if args.cmd == 'next':
                if not s['done']: raise ValueError('当前手牌尚未结束')
                start_hand(s)
            elif args.cmd == 'act': act(s, args.seat, args.action, args.to)
        if args.cmd != 'view':
            STATE.parent.mkdir(exist_ok=True)
            temp = STATE.with_suffix('.tmp')
            temp.write_text(json.dumps(s, ensure_ascii=False, indent=2))
            temp.replace(STATE)
        print(json.dumps(view(s, args.seat if args.cmd == 'view' else 0), ensure_ascii=False, indent=2))
    except (ValueError, FileNotFoundError) as e:
        parser.exit(2, f'错误：{e}\n')


if __name__ == '__main__': main()
