"""Current-round action forecasts from a PUBLIC snapshot; never touches saves.

The live engine's betting transitions are reused on separate in-memory states.
Opponent responses receive their own sampled hand, never another sampled hand
or the runout. Continuations after a raise are chosen over public-path groups.
"""
import math
import random
from collections import defaultdict
from typing import NamedTuple

from .__main__ import act, legal, score
from .ranges import features, response_probabilities, VERSION

MODEL_VERSION = VERSION+'-responses-v1'
STREETS = {0: 'preflop', 3: 'flop', 4: 'turn', 5: 'river'}


class Outcome(NamedTuple):
    net: float
    paid: int
    refund: int
    direct: bool
    showdown: bool
    tie: bool
    pots: tuple
    excluded: tuple


def betting_state(v):
    """Recover public reopen/pending state without any hidden card fields."""
    current, minimum, acted = 0, 10, []
    for event in v['events']:
        if event['kind'] == 'deal':
            current, minimum, acted = 0, 10, []
        elif event['kind'] == 'blind':
            current = max(current, event['bet'])
        elif event['kind'] == 'action':
            if event['action'] == 'raise':
                delta = event['bet']-current
                if delta >= minimum:
                    minimum, acted = delta, []
                current = max(current, event['bet'])
            if event['seat'] not in acted:
                acted.append(event['seat'])
    actual = max(p['bet'] for p in v['players'])
    approximate = not v['history_complete'] or current != actual
    if approximate:
        acted = [i for i, p in enumerate(v['players']) if actual > 0 and p['bet'] == actual]
    hero = v['seat']
    options = v['legal']
    if options.get('raise_to_min') is not None:
        minimum = options['raise_to_min']-actual
        acted = [i for i in acted if i != hero]
    elif hero not in acted:
        acted.append(hero)
    players = [{k: p[k] for k in ('name', 'stack', 'bet', 'total', 'folded')} for p in v['players']]
    pending = [i for i, p in enumerate(players) if not p['folded'] and p['stack'] > 0
               and (i not in acted or p['bet'] < actual)]
    if hero not in pending:
        pending.append(hero)
    return dict(hand=v['hand'], button=v['button'], board=list(v['board']),
                street=STREETS[len(v['board'])], players=players, turn=hero,
                current=actual, min_raise=minimum, acted=acted, pending=pending,
                done=False, round_closed=False, events=[], log=[]), approximate


def clone(s):
    return dict(s, players=[dict(p) for p in s['players']], acted=s['acted'][:],
                pending=s['pending'][:], events=s['events'][:], log=s['log'][:])


def outcome(s, v, values):
    """Cash at showdown, including exact odd-chip order and unmatched refunds."""
    hero = v['seat']
    players = s['players']
    live = [i for i, p in enumerate(players) if not p['folded']]
    previous, refund, pools = 0, 0, []
    for level in sorted({p['total'] for p in players if p['total']}):
        contributors = [i for i, p in enumerate(players) if p['total'] >= level]
        amount = (level-previous)*len(contributors)
        previous = level
        if len(contributors) == 1:
            if contributors[0] == hero:
                refund += amount
            continue
        eligible = live if len(live) == 1 else [i for i in live if players[i]['total'] >= level]
        if not eligible:
            raise ValueError('模拟底池缺少有资格玩家')
        if pools and pools[-1][1] == eligible:
            pools[-1][0] += amount
        else:
            pools.append([amount, eligible])
    own, excluded = [], []
    cash = refund
    for n, (amount, eligible) in enumerate(pools):
        label = '主池' if n == 0 else f'边池 {n}'
        if hero not in eligible:
            excluded.append(label)
            continue
        best = max(values[i] for i in eligible)
        winners = [i for i in eligible if values[i] == best]
        direct = len(eligible) == 1
        sole = not direct and winners == [hero]
        tie = hero in winners and len(winners) > 1
        if hero in winners:
            order = sorted(winners, key=lambda i: (i-v['button']-1) % len(players))
            cash += amount//len(order)+(order.index(hero) < amount % len(order))
        own.append((label, amount, direct, sole, tie))
    any_sole = any(p[3] for p in own)
    direct = bool(own) and all(p[2] for p in own)
    tied = not any_sole and not direct and any(p[4] for p in own)
    paid = players[hero]['total']-v['players'][hero]['total']
    return Outcome(cash-paid, paid, refund, direct, any_sole, tied, tuple(own), tuple(excluded))


def response(s, seat, hole, roll, raises, pressure):
    options = legal(s)
    can_raise = raises == 0 and options.get('raise_to_min') is not None
    active = [i for i, p in enumerate(s['players']) if not p['folded']]
    late_seats = [(s['button']-d) % len(s['players']) for d in range(len(s['players']))]
    late_seats = [i for i in late_seats if i in active][:2]
    probs = response_probabilities(hole, tuple(s['board']), call=options['call'],
                                   pot=sum(p['total'] for p in s['players']), opponents=len(active)-1,
                                   late=seat in late_seats, can_raise=can_raise, pressure=pressure)
    if roll < probs['fold']:
        return 'fold', None
    if not can_raise or roll < probs['fold']+probs['call']:
        return ('check' if options['check'] else 'call'), None
    pot = sum(p['total'] for p in s['players'])+options['call']
    target = s['current']+max(s['min_raise'], math.ceil(pot*(.75 if options['call'] else .5)))
    return 'raise', min(options['raise_to_max'], target)


def finish(s, v, hands, rolls, values, visits, raises, pressure, *, stop_for_hero):
    while not s['round_closed']:
        seat = s['turn']
        if seat == v['seat']:
            if stop_for_hero:
                return s, visits, raises
            raise ValueError('模拟意外再次要求用户行动')
        count = visits[seat]
        if count >= len(rolls[seat]):
            raise ValueError('模拟行动次数超出当前轮限制')
        action, target = response(s, seat, hands[seat], rolls[seat][count], raises, pressure+raises)
        visits[seat] += 1
        act(s, seat, action, target, stop_at_round_end=True)
        raises += action == 'raise'
    return outcome(s, v, values)


def simulate_choice(root, v, choice, hands, rolls, values, pressure):
    state = clone(root)
    act(state, v['seat'], choice['action'], choice.get('target'), stop_at_round_end=True)
    finished = finish(state, v, hands, rolls, values, [0]*len(v['players']), 0, pressure, stop_for_hero=True)
    if isinstance(finished, Outcome):
        return finished, None, None, False
    state, visits, raises = finished
    # The key contains only publicly observable actions, not private hands,
    # random numbers or the future board. Policy is chosen after pooling worlds.
    key = tuple((e['seat'], e['action'], e['bet']) for e in state['events'] if e['kind'] == 'action')
    options = legal(state)
    price = options['call']/max(1, sum(p['total'] for p in state['players'])+options['call'])
    fallback_call = features(tuple(v['hole']), tuple(v['board']))['strength'] >= price+.35
    endings = []
    for action in ('call' if not options['check'] else 'check', 'fold'):
        branch = clone(state)
        act(branch, v['seat'], action, stop_at_round_end=True)
        endings.append(finish(branch, v, hands, rolls, values, visits[:], raises, pressure, stop_for_hero=False))
    return endings[0], endings[1], key, fallback_call


def weighted_error(weights, values):
    sw = sum(weights)
    mean = sum(w*x for w, x in zip(weights, values))/sw
    error = 1.96*math.sqrt(sum(w*w*(x-mean)**2 for w, x in zip(weights, values)))/sw
    return mean, error


def continuation_policies(records):
    paths = defaultdict(list)
    for weight, called, folded, key, fallback in records:
        if key is not None:
            paths[key].append((weight, called.net-folded.net, fallback))
    policy, rare = {}, set()
    for key, samples in paths.items():
        weights = [w for w, _, _ in samples]
        ess = sum(weights)**2/sum(w*w for w in weights)
        if ess < 30:
            # A rare public path must not turn into a one-world oracle.
            policy[key] = samples[0][2]
            rare.add(key)
        else:
            mean, error = weighted_error(weights, [d for _, d, _ in samples])
            policy[key] = mean > error
    return policy, rare


def summarize(choice, records):
    policy, rare = continuation_policies(records)
    weights = [r[0] for r in records]
    sw = sum(weights)
    selected = [called if key is None or policy[key] else folded
                for _, called, folded, key, _ in records]
    nets = [o.net for o in selected]
    ev, error = weighted_error(weights, nets)
    pool_stats = defaultdict(lambda: [0., 0., 0., 0., 0.])
    excluded = defaultdict(float)
    for w, o in zip(weights, selected):
        for label, amount, direct, sole, tie in o.pots:
            stats = pool_stats[label]
            for n, value in enumerate((1, amount, direct, sole, tie)):
                stats[n] += w*value
        for label in o.excluded:
            excluded[label] += w
    pots = [dict(label=label, presence=x[0]/sw, amount=x[1]/x[0], direct=x[2]/x[0],
                 showdown=x[3]/x[0], tie=x[4]/x[0], win=(x[2]+x[3])/x[0])
            for label, x in sorted(pool_stats.items())]
    def probability(predicate):
        return sum(w*predicate(o) for w, o in zip(weights, selected))/sw
    result = dict(action=choice['action'], label=choice['label'], paid=choice['paid'], target=choice.get('target'),
                  ev=ev, error=error, direct=probability(lambda o: o.direct),
                  showdown=probability(lambda o: o.showdown), tie=probability(lambda o: o.tie),
                  win=probability(lambda o: o.direct or o.showdown), loss_risk=probability(lambda o: o.net < 0),
                  refund=sum(w*o.refund for w, o in zip(weights, selected))/sw,
                  extra_paid=sum(w*(o.paid-choice['paid']) for w, o in zip(weights, selected))/sw,
                  reraise=sum(r[0]*(r[3] is not None) for r in records)/sw,
                  rare_path=sum(r[0]*(r[3] in rare) for r in records)/sw,
                  pot_results=pots, excluded_pots=[dict(label=k,prob=w/sw) for k,w in sorted(excluded.items())],
                  split=any(len(o.pots)+len(o.excluded) > 1 for o in selected))
    return result, nets


def select_action(results, nets, weights):
    """Net EV first; statistically indistinguishable actions prefer less spend."""
    leader = max(range(len(results)), key=lambda i: results[i]['ev'])
    nearby = []
    for i, result in enumerate(results):
        difference, error = weighted_error(weights, [a-b for a,b in zip(nets[leader], nets[i])])
        if difference <= error+1e-9:
            nearby.append(i)
    selected = min(nearby, key=lambda i: (results[i]['paid'], results[i]['loss_risk'],
                                         results[i]['action'] != 'check', -results[i]['ev']))
    order = [selected]+sorted((i for i in range(len(results)) if i != selected), key=lambda i: -results[i]['ev'])
    return order


def predict_actions(v, tables, choices, samples, seed):
    from .assist import DECK
    root, approximate = betting_state(v)
    hero = v['seat']
    live = [i for i,p in enumerate(v['players']) if not p['folded']]
    opponents = [i for i in live if i != hero]
    missing = 5-len(v['board'])
    deck = [c for c in DECK if c not in v['hole']+v['board']]
    indices = {c:n for n,c in enumerate(DECK)}
    rng = random.Random(seed ^ 0xA17C10)
    weights = []
    records = [[] for _ in choices]
    pressure = sum(e['kind']=='action' and e.get('action')=='raise' for e in v['events'][-8:])
    target = samples
    ceiling = min(100000, max(samples, 10000))
    while True:
        for _ in range(len(weights), target):
            drawn = rng.sample(deck, missing+2*len(opponents))
            final = v['board']+drawn[:missing]
            hands = {hero: tuple(v['hole'])}
            weight = 1.
            for n,i in enumerate(opponents):
                hand = tuple(sorted(drawn[missing+2*n:missing+2*n+2], key=indices.__getitem__))
                hands[i] = hand
                weight *= tables[i].get(hand, 0.)
            values = {i:score(list(hand)+final) for i,hand in hands.items()}
            rolls = [[rng.random() for _ in range(3)] for _ in v['players']]
            weights.append(weight)
            for c, choice in enumerate(choices):
                if choice['action'] == 'fold':
                    records[c].append((weight, Outcome(0.,0,0,False,False,False,(),()),None,None,False))
                else:
                    called, folded, key, fallback = simulate_choice(root,v,choice,hands,rolls,values,pressure)
                    records[c].append((weight,called,folded,key,fallback))
        sw = sum(weights)
        if not sw:
            if target >= ceiling:
                raise ValueError('响应推演范围权重退化')
            ess = 0.
        else:
            ess = sw*sw/sum(w*w for w in weights)
        if ess >= 100-1e-9 or target >= ceiling:
            break
        target = min(ceiling, target*2)
    results, nets = [], []
    for choice, rows in zip(choices, records):
        result, values = summarize(choice, rows)
        results.append(result)
        nets.append(values)
    order = select_action(results, nets, weights)
    best, backup = results[order[0]], results[order[1]] if len(order)>1 else None
    gap, error = weighted_error(weights,[a-b for a,b in zip(nets[order[0]],nets[order[1]])]) if backup else (1.,0.)
    confidence = '高' if ess >= 1000 and gap > error else '中' if ess >= 100 and gap > error else '低'
    if approximate or best['rare_path'] > .05:
        confidence = '低'
    return dict(model=MODEL_VERSION, samples=target, ess=ess, confidence=confidence,
                approximate=approximate, actions=[results[i] for i in order], best=best, backup=backup)
