"""Local policies consume one seat's public snapshot, never the game state."""
import random
from .ranges import response_probabilities, features

# Pressure, trapping, shifting, bluff-catching, disruptive, observant, inducing.
RAISE_WEIGHTS = (1.45, .7, 1.3, .65, 1.6, .95, .75)
CALL_WEIGHTS = (.85, 1.3, .95, 1.5, .8, 1., 1.4)


def decide(v, seat, seed):
    p = v['players'][seat]
    legal = v['legal']
    rng = random.Random(seed)
    if v['done'] or v['turn'] != seat or seat == 0:
        raise ValueError('无对手行动资格')
    opponents = sum(not x['folded'] for i, x in enumerate(v['players']) if i != seat)
    late = seat in (v['button'], (v['button']-1) % len(v['players']))
    probs = response_probabilities(p['hole'], v['board'], call=legal['call'], pot=v['pot'],
        opponents=opponents, late=late, can_raise=legal['raise_to_max'] is not None)
    factor = 1.15 if v.get('mode') == 'gambler' else 1.
    weights = [probs['fold'], probs['call']*CALL_WEIGHTS[(seat-1)%7],
               probs['raise_']*RAISE_WEIGHTS[(seat-1)%7]*factor]
    action = rng.choices(['fold', 'call', 'raise'], weights=weights)[0]
    if action == 'call': return ('check' if legal['check'] else 'call'), None
    if action == 'fold': return 'fold', None
    cap, minimum = legal['raise_to_max'], legal['raise_to_min']
    if cap is None: raise ValueError('策略选择了非法加注')
    if not v['board']:
        target = max(minimum, max(x['bet'] for x in v['players'])*3 +
                     10*sum(x['bet'] > 10 for x in v['players']))
    else:
        fraction = rng.choice([.5, .66, .85])
        target = max(minimum, p['bet'] + legal['call'] + round((v['pot']+legal['call'])*fraction))
    if target >= cap*.85 and features(tuple(p['hole']), tuple(v['board']))['strength'] > .85:
        target = cap
    return 'raise', min(cap, target)


def decision_view(state, seat):
    """Explicit whitelist. Caller alone owns state; policy sees no other hole cards."""
    from .__main__ import view
    raw = view(state, seat)
    return {k: raw[k] for k in ('done','turn','players','board','legal','pot','button','mode')}
