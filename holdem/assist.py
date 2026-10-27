"""Read-only advice over an explicit public-information snapshot."""
import random
import itertools
import math
from .__main__ import score, RANKS

NAMES = ['高牌', '一对', '两对', '三条', '顺子', '同花', '葫芦', '四条', '同花顺']


def public_snapshot(view, seat=0):
    """Copy only allowed fields; never forward opponents' hole cards or events."""
    return dict(seat=seat, board=list(view['board']),
                hole=list(view['players'][seat].get('hole', [])),
                players=[{k: p[k] for k in ('stack', 'bet', 'total', 'folded')}
                         for p in view['players']],
                turn=view['turn'], done=view['done'], button=view['button'],
                legal=dict(view.get('legal', {})) if view['turn'] == seat else {})


def eligible_pots(totals, live):
    previous = 0
    for level in sorted(set(totals) - {0}):
        contributors = [i for i, total in enumerate(totals) if total >= level]
        amount = (level - previous) * len(contributors)
        yield amount, [i for i in live if totals[i] >= level], len(contributors)
        previous = level


def analyze(v, samples=2000, seed=None):
    if not 100 <= samples <= 100000:
        raise ValueError('模拟次数必须在 100–100000 之间')
    seat = v['seat']; hero = v['players'][seat]
    if v['done'] or hero['folded'] or len(v['hole']) != 2:
        return dict(inactive=True, reason='本手已结束或你已弃牌／未入局，辅助分析停止。')
    known = v['hole'] + v['board']
    if len(known) != len(set(known)) or len(v['board']) not in (0, 3, 4, 5):
        raise ValueError('可见牌面无效')
    deck = [r+s for r in RANKS for s in 'shdc' if r+s not in known]
    opponents = [i for i,p in enumerate(v['players']) if i != seat and not p['folded']]
    live = [seat] + opponents
    rng = random.Random(seed)
    wins = ties = 0; equity = 0.; categories = [0]*9; expected = 0.
    examples = [None]*9
    options = v['legal']; call = options.get('call', 0)
    totals = [p['total'] for p in v['players']]; totals[seat] += call
    pots = list(eligible_pots(totals, live))
    contestable = sum(amount for amount, eligible, count in pots if seat in eligible and count > 1)
    refund = sum(amount for amount, eligible, count in pots if seat in eligible and count == 1)
    net_call = max(0, call-refund)
    for _ in range(samples):
        drawn = rng.sample(deck, 5-len(v['board'])+2*len(opponents))
        missing = 5-len(v['board']); board = v['board']+drawn[:missing]
        values = {seat: score(v['hole']+board)}
        for n,i in enumerate(opponents):
            values[i] = score(drawn[missing+2*n:missing+2*n+2]+board)
        best = max(values.values()); winners = [i for i in live if values[i] == best]
        if seat in winners:
            wins += len(winners) == 1; ties += len(winners) > 1
            equity += 1/len(winners)
        category = values[seat][0]
        categories[category] += 1
        if examples[category] is None:
            hand = next(list(h) for h in itertools.combinations(v['hole']+board, 5)
                        if score(h) == values[seat])
            examples[category] = dict(hand=hand, runout=board[len(v['board']):])
        for amount, eligible, count in pots:
            if seat not in eligible or count == 1: continue
            top = max(values[i] for i in eligible)
            winning = [i for i in eligible if values[i] == top]
            if seat in winning: expected += amount/len(winning)
    eq = equity/samples
    result = dict(inactive=False, samples=samples, win=wins/samples, tie=ties/samples,
                  loss=1-(wins+ties)/samples, equity=eq,
                  categories=[x/samples for x in categories], examples=examples,
                  current=NAMES[score(known)[0]] if len(known)>=5 else '起手牌（尚未发翻牌）',
                  margin=1.96*math.sqrt(.25/samples), call=call,
                  contestable=contestable, threshold=net_call/contestable if contestable else None,
                  call_ev=expected/samples-net_call)
    if v['turn'] != seat:
        result['advice']='等待你行动后更新建议。'
    elif hero['stack'] == 0:
        result['advice']='你已全押，等待结算。'
    else:
        # Conservative, explicit heuristics; uncertainty favours the free action.
        result['advice']='过牌' if options.get('check') else ('跟注 '+str(call) if result['call_ev'] >= 0 else '弃牌')
        result['reason']='按分池资格估算的跟注净收益为 '+f'{result["call_ev"]:+.1f}'+'；假设此后无额外下注。'
        minimum, cap = options.get('raise_to_min'), options.get('raise_to_max')
        if minimum is not None and cap >= minimum and eq > max(.65, 1/len(live)+.2):
            pot = sum(p['total'] for p in v['players'])
            current = hero['bet']+call
            target = min(cap, max(minimum, current+max(10, (pot+call)//2)))
            result['advice']=('下注到 ' if options.get('check') and hero['bet']==0 else '加注到 ')+str(target)+'（启发式）'
            result['reason']='随机范围下权益较高；金额参考半池及合法下限，未估算对手弃牌率或加注收益。'
    return result


def render_analysis(a):
    from .display import pad, cards
    line = '─' * 58
    lines = ['', '辅助分析 · 用户视角', line]
    if a['inactive']:
        return '\n'.join(lines + [a['reason']])
    pct = lambda x: f'{x:.1%}'
    row = lambda label, value: '  ' + pad(label, 18) + str(value)
    lines += ['【行动建议】', row('推荐动作', a['advice'])]
    if 'reason' in a:
        lines += [row('依据', a['reason']), '', '【跟注评估】',
                  row('本次跟注', a['call']),
                  row('跟注后可争夺池', a['contestable']),
                  row('所需加权权益', pct(a['threshold']) if a['threshold'] is not None else '不适用'),
                  row('估算跟注净收益', f'{a["call_ev"]:+.1f}'),
                  '  多边池分别计算预期分得金额；整体摊牌权益不能直接与加权门槛比较。']
    lines += ['', '【胜率与权益】', row('当前牌型', a['current']),
              row('独赢', pct(a['win'])), row('平局', pct(a['tie'])),
              row('落败', pct(a['loss'])), row('摊牌权益', pct(a['equity'])),
              '  摊牌权益包含平局时分得的份额。', '', '【到河牌的最终牌型】']
    lines += ['  示例来自独立模拟，不代表真实后续发牌；每类展示一种组合。']
    for name, probability, example in zip(NAMES, a['categories'], a['examples']):
        lines.append(row(name, pct(probability)))
        if example is None:
            lines.append('    本轮未采样到示例，不代表绝无可能。')
        else:
            lines.append('    五张牌示例：' + cards(example['hand']))
            lines.append('    需补公共牌：' + (cards(example['runout']) if example['runout'] else '无（当前已到河牌）'))
    lines += ['', '【计算口径】', row('对手范围', '未弃牌对手均匀随机手牌'),
              row('模拟次数', a['samples']),
              row('抽样误差', f'单项比例约 95% 上限 ±{pct(a["margin"])}'),
              '  仅使用自己的底牌与桌面公开信息，未知牌独立模拟。',
              '  误差不包含对手范围假设造成的偏差。',
              '  跟注评估假设之后无额外下注；加注为启发式建议。', line]
    return '\n'.join(lines)
