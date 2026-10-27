"""Public-information analysis. Never reads a save or receives private state."""
import hashlib
import itertools
import json
import math
import random
from collections import Counter, defaultdict
from .__main__ import score, RANKS
from .ranges import bucket, contexts, weight, POST_LABELS, PRE_LABELS

NAMES = ['高牌','一对','两对','三条','顺子','同花','葫芦','四条','同花顺']
DECK = [r+s for r in RANKS for s in 'shdc']


def public_snapshot(view, seat=0):
    events=[]
    allowed={'blind':('seat','paid','bet'), 'action':('seat','action','paid','bet','all_in'),
             'deal':('cards',), 'round_end':()}
    for e in view.get('events',[]):
        if e.get('kind') not in allowed: continue
        item={'kind':e['kind']}
        for k in allowed[e['kind']]:
            if k in e: item[k]=list(e[k]) if k=='cards' else e[k]
        events.append(item)
    return dict(seat=seat,hand=view.get('hand',0),board=list(view['board']),
                hole=list(view['players'][seat].get('hole',[])),
                players=[{**{k:p[k] for k in ('stack','bet','total','folded')},
                          'name':p.get('name',str(i))} for i,p in enumerate(view['players'])],
                turn=view['turn'],done=view['done'],button=view['button'],events=events,
                history_complete=view.get('history_complete',False),
                legal=dict(view.get('legal',{})) if view['turn']==seat else {})


def eligible_pots(totals, live):
    previous=0
    for level in sorted(set(totals)-{0}):
        contributors=[i for i,t in enumerate(totals) if t>=level]
        yield (level-previous)*len(contributors),[i for i in live if totals[i]>=level],len(contributors)
        previous=level


def describe(hole,board):
    if not board:
        a,b=hole; pair=a[0]==b[0]; distance=abs(RANKS.index(a[0])-RANKS.index(b[0]))
        return ('口袋对子 '+a[0] if pair else ('同花' if a[1]==b[1] else '不同花')+'起手牌')+(' · 相邻牌' if distance==1 else ''),[],[]
    hand=max(itertools.combinations(hole+board,5),key=score); value=score(hand)
    rank=lambda r:'10' if r==10 else RANKS[r-2]
    detail=NAMES[value[0]]
    if value[0] in (1,3,7): detail+=' '+rank(value[1])
    if value[0]==2: detail+=' '+rank(value[1])+' 与 '+rank(value[2])
    if value[0]==6: detail+=' '+rank(value[1])+' 带 '+rank(value[2])
    if value[0] in (0,4,8): detail+=' · '+rank(value[1])+' 高'
    if value[0] in (1,2,3) and len(value)>2: detail+=' · 踢脚 '+ ' / '.join(rank(r) for r in value[2 if value[0]!=2 else 3:])
    used=[c for c in hand if c in hole]
    if len(board)==5 and score(board)==value:
        detail+='（公共牌即可组成）'
    return detail,list(hand),used


def range_tables(v, board, events, live):
    deck=[c for c in DECK if c not in v['hole']+board]
    actions=contexts(events,v['button'],len(v['players'])) if v['history_complete'] else []
    tables={}; summaries=[]
    for i in live:
        if i==v['seat']: continue
        history=[a for a in actions if a['seat']==i]
        weights={h:weight(list(h),history) for h in itertools.combinations(deck,2)}
        scale=max(weights.values()); weights={h:w/scale for h,w in weights.items()}
        tables[i]=weights
        groups=defaultdict(lambda:dict(weight=0.,example=None,example_weight=-1.))
        ahead=equal=0.; leading=[]
        threats=defaultdict(lambda: dict(weight=0.,combos=0,families=defaultdict(float),examples=[]))
        hero_score=score(v['hole']+board) if len(board)>=3 else None
        labels=POST_LABELS if board else PRE_LABELS
        for h,w in weights.items():
            group=groups[labels[bucket(list(h),board)]]; group['weight']+=w
            if w>group['example_weight']: group['example']=list(h); group['example_weight']=w
            if hero_score is not None:
                theirs=score(list(h)+board)
                ahead+=w*(theirs>hero_score); equal+=w*(theirs==hero_score)
                if theirs>hero_score:
                    leading.append((w,list(h)))
                    threat=threats[NAMES[theirs[0]]]
                    threat['weight']+=w; threat['combos']+=1
                    ranks=sorted((c[0] for c in h),key=RANKS.index,reverse=True)
                    family='＋'.join('10' if r=='T' else r for r in ranks)
                    threat['families'][family]+=w
                    threat['examples'].append((w,list(h)))
        total=sum(g['weight'] for g in groups.values())
        grouped_threats=[]
        for label, group in sorted(threats.items(),key=lambda item:-item[1]['weight']):
            families=sorted(group['families'],key=lambda family:-group['families'][family])
            grouped_threats.append(dict(label=label,prob=group['weight']/total,combos=group['combos'],
                                       families=families,example=max(group['examples'],key=lambda item:item[0])[1]))
        summaries.append(dict(threats=grouped_threats,leading=[dict(hole=h,description=describe(h,board)[0]) for _,h in sorted(leading,key=lambda x:-x[0])[:2]],ahead=ahead/total,equal=equal/total,seat=i,name=v['players'][i]['name'],
            groups=[dict(label=k,prob=g['weight']/total,example=g['example'],description=describe(g['example'],board)[0]) for k,g in sorted(groups.items(),key=lambda x:-x[1]['weight'])],
            evidence=[('翻牌前' if not a['board'] else {3:'翻牌',4:'转牌',5:'河牌'}[len(a['board'])])+{'raise':'下注／加注','call':'跟注','check':'过牌','fold':'弃牌'}.get(a['action'],a['action']) for a in history]))
    return tables,summaries


def scenario(v, totals, live, paid, label):
    """Freeze contributions and eligibility for one explicitly forced response."""
    hero = v['seat']
    pots = list(eligible_pots(totals, live))
    # Match settlement: adjacent contribution levels with the same eligibility
    # are one pot. Single-contributor levels are refunds, never victories.
    contested = []
    for amount, eligible, count in pots:
        if count == 1:
            continue
        if contested and contested[-1]['eligible'] == eligible:
            contested[-1]['amount'] += amount
        else:
            contested.append(dict(amount=amount, eligible=eligible))
    for n, pot in enumerate(contested):
        pot['label'] = '主池' if n == 0 else f'边池 {n}'
    own = [p for p in contested if hero in p['eligible']]
    contest = sum(p['amount'] for p in own)
    refund = sum(a for a, e, n in pots if hero in e and n == 1)
    return dict(label=label, pots=pots, pot_results=own, call=paid,
                contestable=contest, refund=refund,
                excluded_pots=[p for p in contested if hero not in p['eligible']],
                threshold=max(0, paid-refund)/contest if contest else None)


def simulate(v, board, live, tables, samples, seed, scenarios=()):
    rng = random.Random(seed)
    hero = v['seat']
    opponents = [i for i in live if i != hero]
    deck = [c for c in DECK if c not in v['hole']+board]
    missing = 5-len(board)
    records = []
    sw = sw2 = wins = ties = equity = uniform = 0.
    groups = defaultdict(lambda: [0., 0., 0., 0])
    # Cache by eligible set: changing an amount cannot change card outcomes.
    eligible_sets = {tuple(p['eligible']) for s in scenarios for p in s['pot_results']}
    outcomes = {e: [0., 0.] for e in eligible_sets}
    scenario_outcomes = [[0., 0.] for _ in scenarios]
    for _ in range(samples):
        drawn = rng.sample(deck, missing+2*len(opponents))
        final = board+drawn[:missing]
        vals = {hero: score(v['hole']+final)}
        w = 1.
        for n, i in enumerate(opponents):
            h = tuple(sorted(drawn[missing+2*n:missing+2*n+2], key=DECK.index))
            w *= tables[i].get(h, 0.)
            vals[i] = score(list(h)+final)
        best = max(vals.values())
        winners = [i for i in live if vals[i] == best]
        share = 1/len(winners) if hero in winners else 0.
        sw += w
        sw2 += w*w
        uniform += share
        equity += w*share
        wins += w*(share == 1)
        ties += w*(0 < share < 1)
        shares = {}
        winners_by_set = {}
        for eligible in eligible_sets:
            top = max(vals[i] for i in eligible)
            ws = [i for i in eligible if vals[i] == top]
            part = 1/len(ws) if hero in ws else 0.
            shares[eligible] = part
            winners_by_set[eligible] = sorted(ws, key=lambda i: (i-v['button']-1) % len(v['players']))
            if len(eligible) > 1:
                outcomes[eligible][0] += w*(part == 1)
                outcomes[eligible][1] += w*(0 < part < 1)
        payouts = []
        for n, s in enumerate(scenarios):
            parts = [shares[tuple(p['eligible'])] for p in s['pot_results']]
            money = s['refund']
            for p, part in zip(s['pot_results'], parts):
                if part:
                    ws = winners_by_set[tuple(p['eligible'])]
                    money += p['amount']//len(ws) + (ws.index(hero) < p['amount'] % len(ws))
            # Disjoint outcomes across pots: any sole win, otherwise any split,
            # otherwise no contested pot won. Direct pickups are kept separate.
            showdown = [part for p, part in zip(s['pot_results'], parts) if len(p['eligible']) > 1]
            sole = any(part == 1 for part in showdown)
            split = not sole and any(0 < part < 1 for part in showdown)
            scenario_outcomes[n][0] += w*sole
            scenario_outcomes[n][1] += w*split
            payouts.append(money-s['call'])
        records.append((w, share, payouts))
        if missing:
            group = groups[drawn[0]]
            group[0] += w
            group[1] += w*share
            group[2] += w*w
            group[3] += 1
    if not sw:
        raise ValueError('范围权重退化，无法计算')
    eq = equity/sw
    ess = sw*sw/sw2
    se = math.sqrt(sum(w*w*(x-eq)**2 for w, x, _ in records))/sw
    estimates = []
    for n, s in enumerate(scenarios):
        ev = sum(w*ps[n] for w, _, ps in records)/sw
        err = 1.96*math.sqrt(sum(w*w*(ps[n]-ev)**2 for w, _, ps in records))/sw
        pots = []
        for p in s['pot_results']:
            direct = len(p['eligible']) == 1
            win, tie = outcomes[tuple(p['eligible'])]
            pots.append(dict(**p, direct=direct, win=None if direct else win/sw,
                             tie=None if direct else tie/sw,
                             loss=None if direct else max(0., 1-(win+tie)/sw)))
        direct = bool(pots) and all(p['direct'] for p in pots)
        win, tie = scenario_outcomes[n]
        estimates.append(dict(s, pot_results=pots, ev=ev, error=err, direct=direct,
                              win=None if direct or not pots else win/sw,
                              tie=None if direct or not pots else tie/sw,
                              loss=None if direct or not pots else max(0., 1-(win+tie)/sw)))
    return dict(equity=eq, win=wins/sw, tie=ties/sw, loss=max(0., 1-(wins+ties)/sw),
                uniform=uniform/samples, ess=ess, error=1.96*se, groups=dict(groups), estimates=estimates)


def cost_scenarios(v, live):
    seat = v['seat']
    call = v['legal'].get('call', 0)
    players = v['players']
    current = max(p['bet'] for p in players)
    pending = [i for i in live if i != seat and players[i]['stack'] > 0 and players[i]['bet'] < current]
    totals = [p['total'] for p in players]
    totals[seat] += call
    result = []
    for mode in (['其余未回应者弃牌', '其余未回应者跟平'] if pending else ['当前跟注']):
        ts = totals[:]
        eligible = live[:]
        if pending:
            if mode.endswith('弃牌'):
                eligible = [i for i in live if i not in pending]
            else:
                for i in pending:
                    ts[i] += min(players[i]['stack'], current-players[i]['bet'])
        result.append(scenario(v, ts, eligible, call, mode))
    return result, pending


def action_scenarios(v, live, base):
    """Legal concrete choices; no probabilities are assigned to responses."""
    seat = v['seat']
    hero = v['players'][seat]
    legal = v['legal']
    call = legal.get('call', 0)
    checking = legal.get('check', False)
    label = '过牌' if checking else ('全押跟注 ' if call == hero['stack'] else '跟注 ')+str(call)
    choices = [dict(action='check' if checking else 'call', label=label, paid=call,
                    indices=list(range(len(base))), risk='免费留场' if checking else '支付跟注，继续争夺')]
    scenarios = list(base)
    minimum, cap = legal.get('raise_to_min'), legal.get('raise_to_max')
    current = max(p['bet'] for p in v['players'])
    if minimum is not None and cap is not None and cap > current:
        pot_after_call = sum(p['total'] for p in v['players'])+call
        targets = sorted({min(cap, max(minimum, current+math.ceil(pot_after_call/2))),
                          min(cap, max(minimum, current+pot_after_call)), cap})
        for target in targets:
            paid = target-hero['bet']
            all_in = target == cap
            label = ('全押到 ' if all_in else '下注到 ' if current == 0 else '加注到 ')+str(target)
            indices = []
            for fold in (False, True):
                totals = [p['total'] for p in v['players']]
                totals[seat] += paid
                eligible = live[:]
                for i in live:
                    if i == seat or v['players'][i]['stack'] == 0:
                        continue  # An already all-in opponent cannot fold.
                    if fold:
                        eligible.remove(i)
                    else:
                        totals[i] += min(v['players'][i]['stack'], max(0, target-v['players'][i]['bet']))
                indices.append(len(scenarios))
                scenarios.append(scenario(v, totals, eligible, paid,
                                          '可回应者全部弃牌' if fold else '可回应者全部跟平'))
            choices.append(dict(action='raise', label=label, paid=paid, target=target,
                                indices=indices, risk='投入全部筹码' if all_in else '追加投入；可能遭反加'))
    if legal.get('fold', True):
        choices.append(dict(action='fold', label='弃牌', paid=0, indices=[], risk='放弃争夺，不再追加投入'))
    return choices, scenarios


def own_paths(v, simulation, tables):
    board=v['board']; hole=v['hole']; deck=[c for c in DECK if c not in hole+board]
    if not board or len(board)==5: return dict(distribution=None,groups=[],details=[])
    counts=Counter(); n=0
    for runout in itertools.combinations(deck,5-len(board)):
        counts[score(hole+board+list(runout))[0]]+=1; n+=1
    current=score(hole+board)[0]; groups=defaultdict(list); details=[]
    for c in deck:
        nextboard=board+[c]; newcat=score(hole+nextboard)[0]
        suits=Counter(x[1] for x in nextboard)
        ranks={RANKS.index(x[0])+2 for x in nextboard}
        if 14 in ranks: ranks.add(1)
        texture=(max(suits.values())>=3 or any(len(ranks&set(range(k,k+5)))>=4 for k in range(1,11)) or len({x[0] for x in nextboard})<len(nextboard))
        stat=simulation['groups'].get(c,[0,0,0,0]); ess=stat[0]**2/stat[2] if stat[2] else 0
        eq=stat[1]/stat[0] if stat[0] and ess>=100 else None
        risk=texture or eq is not None and eq+simulation['error']<simulation['equity']
        improved=newcat>current
        group='改善但有风险' if improved and risk else ('有效改善' if improved else ('危险来牌' if risk else '其他来牌'))
        route=NAMES[newcat]
        if improved:
            route+=('（底牌配对／成三条）' if c[0] in {x[0] for x in hole} else ('（公共牌配对）' if c[0] in {x[0] for x in board} else '（补成新牌型）'))
        item=dict(card=c,category=NAMES[newcat],route=route,group=group,equity=eq,ess=ess,
                  reason=('提高我的成牌等级；' if improved else '未提高我的成牌等级；')+('牌面出现配对／同花／顺子威胁，或模型权益下降。' if risk else '未触发牌面风险规则，仍不保证获胜。'))
        groups[group].append(item); details.append(item)
    grouped=[]
    for label in ('有效改善','改善但有风险','危险来牌','其他来牌'):
        items=groups[label]
        if not items: continue
        stats=[simulation['groups'].get(x['card'],[0,0,0,0]) for x in items]
        sw=sum(x[0] for x in stats); sw2=sum(x[2] for x in stats)
        ess=sw*sw/sw2 if sw2 else 0
        eq=sum(x[1] for x in stats)/sw if sw and ess>=100 else None
        example=items[0]; nextboard=board+[example['card']]
        hero_value=score(hole+nextboard); threat=None
        existing_threat=None
        before_value=score(hole+board)
        for opponent,weights in tables.items():
            for h,w in sorted(weights.items(),key=lambda x:-x[1]):
                if example['card'] in h: continue
                if score(list(h)+nextboard)>hero_value:
                    candidate=dict(card=example['card'],opponent=v['players'][opponent]['name'],
                                   hole=list(h),description=describe(list(h),nextboard)[0])
                    if existing_threat is None: existing_threat=candidate
                    if score(list(h)+board)<=before_value:
                        threat=candidate
                        break
            if threat: break
        threat=threat or existing_threat
        grouped.append(dict(label=label,items=items,prob=len(items)/len(deck),equity=eq,ess=ess,threat=threat))
    return dict(distribution=[counts[k]/n for k in range(9)],groups=grouped,details=details)


def replay(v,samples,seed):
    events=v['events']; hero=v['seat']
    if not v['history_complete']: return []
    hero_actions=[n for n,e in enumerate(events) if e['kind']=='action' and e['seat']==hero]
    if not hero_actions: return []
    start=hero_actions[-1]; board=[]
    live=[i for i,p in enumerate(v['players']) if p['stack']+p['total']>0]
    checkpoints=[]
    for n,e in enumerate(events):
        if n==start: checkpoints.append(('上个用户行动点',board[:],live[:],events[:n]))
        label=None
        if e['kind']=='deal': board=e['cards'][:]; label='公共牌变化'
        elif e['kind']=='action' and e['action']=='fold':
            if e['seat'] in live: live.remove(e['seat'])
            label=v['players'][e['seat']]['name']+'弃牌（人数变化）'
        elif e['kind']=='action' and e['seat']!=hero and e['action'] in ('call','raise'):
            label=v['players'][e['seat']]['name']+'行动（范围更新）'
        if n>=start and label: checkpoints.append((label,board[:],live[:],events[:n+1]))
    result=[]
    for label,board,live,history in checkpoints:
        if hero not in live: continue
        tables,_=range_tables(v,board,history,live)
        sim=simulate(v,board,live,tables,samples,seed)
        previous=result[-1]['equity'] if result else sim['equity']
        previous_win = result[-1]['win'] if result else sim['win']
        result.append(dict(label=label,equity=sim['equity'],delta=sim['equity']-previous,
                           win=sim['win'],win_delta=sim['win']-previous_win,error=sim['error'],ess=sim['ess']))
    return result


def analyze(v,samples=2000,seed=None,detail=False):
    if not 100<=samples<=100000: raise ValueError('模拟次数必须在 100–100000 之间')
    seat=v['seat']; hero=v['players'][seat]
    if v['done'] or hero['folded'] or len(v['hole'])!=2:
        return dict(inactive=True,reason='本手已结束或你已弃牌／未入局，辅助分析停止。')
    known=v['hole']+v['board']
    if len(set(known))!=len(known) or any(c not in DECK for c in known) or len(v['board']) not in (0,3,4,5):
        raise ValueError('可见牌面无效')
    if seed is None:
        seed=int.from_bytes(hashlib.sha256(json.dumps([v['hole'],v.get('hand',0),seat]).encode()).digest()[:8],'big')
    live=[i for i,p in enumerate(v['players']) if not p['folded']]
    tables,ranges=range_tables(v,v['board'],v['events'],live)
    can_act = v['turn'] == seat and hero['stack'] > 0
    base, pending = cost_scenarios(v, live) if can_act else ([], [])
    choices, scenarios = action_scenarios(v, live, base) if can_act else ([], [])
    # The headline uses a specified flat-call-to-showdown scenario, too. This
    # keeps a short stack's final chances tied to the pots it can actually win.
    totals = [p['total'] for p in v['players']]
    current_bet = max(p['bet'] for p in v['players'])
    for i in live:
        p = v['players'][i]
        totals[i] += min(p['stack'], max(0, current_bet-p['bet']))
    headline_paid = totals[seat]-hero['total']
    headline = scenario(v, totals, live, headline_paid, '全部跟平至摊牌')
    sim = simulate(v, v['board'], live, tables, samples, seed, scenarios+[headline])
    estimates = sim['estimates'][:len(base)]
    comparisons = []
    for choice in choices:
        comparisons.append(dict(choice, scenarios=[sim['estimates'][i] for i in choice['indices']]))
    current, hand, used = describe(v['hole'], v['board'])
    result = dict(inactive=False, **sim, samples=samples, current=current, best=hand, used=used,
                  ranges=ranges, history_complete=v['history_complete'], paths=own_paths(v, sim, tables),
                  timeline=replay(v, samples, seed), detail=detail, board=v['board'], hole=v['hole'],
                  live_count=len(live), call=v['legal'].get('call', 0), alternative=None,
                  comparisons=comparisons, can_act=can_act, hand_number=v.get('hand', 0),
                  seat=seat, player_names=[p['name'] for p in v['players']],
                  pending=pending, headline=sim['estimates'][-1])
    result['estimates'] = estimates
    if can_act:
        from .predict import predict_actions
        prediction = predict_actions(v, tables, choices, samples, seed)
        best = prediction['best']
        advice = best['label']
        if best['action'] == 'fold':
            continued = [c for c in prediction['actions'] if c['action'] != 'fold']
            reason = ('继续投入的选项预计净收益均不高于零；弃牌避免追加损失。' if all(c['ev'] <= 0 for c in continued)
                      else '继续投入的收益优势不够稳定，优先避免追加损失。')
        else:
            reason = f'综合获胜机会与投入，预计净收益 {best["ev"]:+.1f}，追加筹码亏损概率 {best["loss_risk"]:.1%}。'
        if prediction['confidence'] == '低':
            reason += '低信心推荐；收益接近时优先减少投入。'
        result['prediction'] = prediction
    elif v['turn'] != seat:
        advice, reason = '等待行动', '尚未轮到你，行动比较将在你的回合更新。'
        result['prediction'] = None
    else:
        advice, reason = '等待结算', '你已全押，无法再选择行动。'
        result['prediction'] = None
    result.update(advice=advice, advice_reason=reason)
    return result


def render_analysis(a, *, format='text', width=64):
    """Render decisions separately from numerical analysis."""
    from .assist_panel import render
    return render(a, format=format, width=width)
