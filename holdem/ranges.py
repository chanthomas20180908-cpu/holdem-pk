"""Versioned, uncalibrated likelihood rules over public action history."""
from collections import Counter
from functools import lru_cache
import math
from .__main__ import score, RANKS

VERSION = 'public-actions-v2'
POST_LABELS = ['高牌', '公共牌对子', '弱对子', '顶对', '超对', '弱两对', '强两对', '三条', '顺子', '同花', '葫芦', '四条', '同花顺', '听牌']
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
    return POST_LABELS.index(features(tuple(hole), tuple(board))['label'])


@lru_cache(maxsize=16384)
def features(hole, board):
    """Board-relative rating, using ONLY this seat's cards and public board.

    A versioned rule score, not calibrated equity. Keeping this interface small
    prevents the response policy from seeing another seat's sampled hand.
    """
    ranks = sorted([RANKS.index(c[0])+2 for c in hole], reverse=True)
    if not board:
        high, low = ranks
        pair, suited = high == low, hole[0][1] == hole[1][1]
        strength = (.48+.035*(high-2) if pair else
                    .12+.025*(high-2)+.018*(low-2)+.045*suited+.035*(high-low == 1))
        return dict(label=PRE_LABELS[bucket(list(hole), [])], strength=min(.98, strength), draw=False)
    value = score(list(hole)+list(board))
    category = value[0]
    bc = Counter(RANKS.index(c[0])+2 for c in board)
    paired = {r for r, n in bc.items() if n >= 2}
    board_high = max(bc)
    flush_draw = straight_draw = False
    if len(board) < 5:
        suits = Counter(c[1] for c in hole+board)
        flush_draw = any(n >= 4 and any(c[1] == suit for c in hole) for suit,n in suits.items())
        public_ranks = set(bc)
        own_ranks = set(ranks)
        if 14 in public_ranks:
            public_ranks.add(1)
        if 14 in own_ranks:
            own_ranks.add(1)
        all_ranks = public_ranks | own_ranks
        straight_draw = any(len(all_ranks & set(range(k,k+5))) == 4
                            and bool((own_ranks-public_ranks) & set(range(k,k+5))) for k in range(1,11))
    draw = flush_draw or straight_draw
    if category >= 4:
        label = ['顺子', '同花', '葫芦', '四条', '同花顺'][category-4]
        strength = [.91, .95, .98, .995, 1.][category-4]
        if len(board) == 5 and score(list(board)) == value:
            strength = .5  # Playing a strong board is not a private monster.
    elif category == 3:
        label = '三条'
        strength = .88 if bc[value[1]] < 3 else .35+.015*ranks[0]
    elif category == 2:
        private_pairs = [r for r in value[1:3] if r not in paired]
        if paired:
            rank = max(private_pairs, default=0)
            if not rank:
                strength = .3+.015*ranks[0]
            else:
                strength = .78 if rank >= board_high else .56 if rank >= sorted(bc)[-2] else .34
                strength += .003*value[3]
            label = '强两对' if strength >= .7 else '弱两对'
        else:
            label, strength = '强两对', .86
    elif category == 1:
        rank = value[1]
        if rank in paired:
            label, strength = '公共牌对子', .14+.012*value[2]
        elif ranks[0] == ranks[1] and rank > board_high:
            label, strength = '超对', .83
        elif rank == board_high:
            label, strength = '顶对', .71+.004*value[2]
        else:
            label, strength = '弱对子', .48 if rank >= sorted(bc)[-2] else .33
    else:
        label, strength = '高牌', .07+.012*ranks[0]
    if draw and category < 4:
        strength = min(.9, strength+.12*flush_draw+.09*straight_draw)
        if category == 0:
            label = '听牌'
    return dict(label=label, strength=strength, draw=draw)


def response_probabilities(hole, board, *, call, pot, opponents, late=False, can_raise=True, pressure=0):
    """Uncalibrated, normalized current-round fold/call/raise likelihoods."""
    if len(board) == 5 and score(list(board)) == (8, 14):
        return dict(fold=0., call=1., raise_=0.)
    f = features(tuple(hole), tuple(board))
    strength = f['strength']
    price = call/max(1, pot+call)
    size = min(2., call/max(1, pot))
    multi = max(0, opponents-1)
    fold_logit = 4*(.45+1.6*price+.15*size+.04*multi+.025*pressure-strength)-3*strength**4
    call_logit = 1+2*strength-2*price
    raise_logit = 12*(strength-.78)-.4-2*price-.15*multi+.25*late
    fold = math.exp(fold_logit) if call else 0.
    calling = math.exp(call_logit)
    raising = (math.exp(raise_logit)+(.15 if f['draw'] else .025)*(1+late)) if can_raise else 0.
    total = fold+calling+raising
    return dict(fold=fold/total, call=calling/total, raise_=raising/total)


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
            f = features(tuple(hole), tuple(a['board']))
            strength = f['strength']
            ratio = a['ratio']
            if action == 'raise':
                multiplier = .25+8*strength**4+.4*f['draw']
                if ratio < .5:
                    multiplier = (1+multiplier)/2
                elif ratio > 1:
                    multiplier *= .35+1.5*strength
            else:
                multiplier = .35+3*strength**2+.7*f['draw']
                if ratio > .5:
                    multiplier *= .4+strength
        value*=multiplier
    return value
