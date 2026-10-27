"""Versioned, uncalibrated likelihood rules over public action history."""
from collections import Counter
from .__main__ import score, RANKS

VERSION = 'public-actions-v1'
POST_LABELS = ['强成牌', '普通成牌', '听牌', '弱牌']
PRE_LABELS = ['强牌', '可玩牌', '其他']


def draw_flags(cards):
    counts = Counter(c[1] for c in cards)
    flush = max(counts.values(), default=0) >= 4
    ranks = {RANKS.index(c[0])+2 for c in cards}
    if 14 in ranks: ranks.add(1)
    straight = any(len(ranks & set(range(n,n+5))) == 4 for n in range(1,11))
    return flush, straight


def bucket(hole, board):
    ranks = sorted([RANKS.index(c[0])+2 for c in hole], reverse=True)
    if not board:
        if ranks[0] == ranks[1] and ranks[0] >= 10 or ranks[0] == 14 and ranks[1] >= 12:
            return 0
        suited = hole[0][1] == hole[1][1]
        if (ranks[0] == ranks[1] or ranks[1] >= 10 or
                suited and (ranks[0] == 14 or ranks[0]-ranks[1] == 1)):
            return 1
        return 2
    value = score(hole+board)
    overpair = ranks[0] == ranks[1] and ranks[0] > max(RANKS.index(c[0])+2 for c in board)
    if value[0] >= 2 or overpair: return 0
    if value[0] == 1: return 1
    if len(board)<5 and any(draw_flags(hole+board)): return 2
    return 3


def contexts(events, button, count):
    board=[]; bets=[0]*count; current=0; pot=0
    result=[]
    for e in events:
        kind=e['kind']
        if kind == 'deal':
            board=list(e['cards']); bets=[0]*count; current=0
        elif kind in ('blind','action'):
            i=e['seat']; paid=e.get('paid',0)
            if kind=='action':
                amount=max(0,e.get('bet',bets[i])-current) if e['action']=='raise' else paid
                result.append(dict(seat=i,action=e['action'],board=board[:],
                                   ratio=amount/pot if pot else 1,
                                   late=i in (button,(button-1)%count)))
            bets[i]=e.get('bet',bets[i]); current=max(current,bets[i]); pot+=paid
    return result


def weight(hole, actions):
    value=1.
    for a in actions:
        action=a['action']
        if action not in ('raise','call'): continue
        b=bucket(hole,a['board'])
        if not a['board']:
            weights=[4,2,1] if action=='raise' else [2,3,1]
            multiplier=weights[b]
            if action=='raise' and a['late'] and b>0: multiplier*=1.5
        else:
            multiplier=([4,2,2,1] if action=='raise' else [3,3,2,1])[b]
            if action=='raise':
                if a['ratio']<.5: multiplier=(multiplier+1)/2
                elif a['ratio']>1 and b<3: multiplier*=1.5
        value*=multiplier
    return value
