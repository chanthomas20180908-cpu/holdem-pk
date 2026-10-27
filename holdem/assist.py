"""Public-information analysis. Never reads a save or receives private state."""
import hashlib
import itertools
import json
import math
import random
from collections import Counter, defaultdict
from .__main__ import score, RANKS
from .ranges import bucket, contexts, weight, VERSION, POST_LABELS, PRE_LABELS

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
        hero_score=score(v['hole']+board) if len(board)>=3 else None
        labels=POST_LABELS if board else PRE_LABELS
        for h,w in weights.items():
            group=groups[labels[bucket(list(h),board)]]; group['weight']+=w
            if w>group['example_weight']: group['example']=list(h); group['example_weight']=w
            if hero_score is not None:
                theirs=score(list(h)+board)
                ahead+=w*(theirs>hero_score); equal+=w*(theirs==hero_score)
                if theirs>hero_score: leading.append((w,list(h)))
        total=sum(g['weight'] for g in groups.values())
        summaries.append(dict(leading=[dict(hole=h,description=describe(h,board)[0]) for _,h in sorted(leading,key=lambda x:-x[0])[:2]],ahead=ahead/total,equal=equal/total,seat=i,name=v['players'][i]['name'],
            groups=[dict(label=k,prob=g['weight']/total,example=g['example'],description=describe(g['example'],board)[0]) for k,g in sorted(groups.items(),key=lambda x:-x[1]['weight'])],
            evidence=[('翻牌前' if not a['board'] else {3:'翻牌',4:'转牌',5:'河牌'}[len(a['board'])])+{'raise':'下注／加注','call':'跟注','check':'过牌','fold':'弃牌'}.get(a['action'],a['action']) for a in history]))
    return tables,summaries


def simulate(v, board, live, tables, samples, seed, scenarios=()):
    rng=random.Random(seed); hero=v['seat']; opponents=[i for i in live if i!=hero]
    deck=[c for c in DECK if c not in v['hole']+board]
    missing=5-len(board); records=[]; sw=sw2=0.; wins=ties=equity=0.; uniform=0.
    groups=defaultdict(lambda:[0.,0.,0.,0])
    for _ in range(samples):
        drawn=rng.sample(deck,missing+2*len(opponents)); final=board+drawn[:missing]
        vals={hero:score(v['hole']+final)}; w=1.
        for n,i in enumerate(opponents):
            h=tuple(sorted(drawn[missing+2*n:missing+2*n+2],key=DECK.index))
            w*=tables[i].get(h,0.)
            vals[i]=score(list(h)+final)
        best=max(vals.values()); winners=[i for i in live if vals[i]==best]
        share=1/len(winners) if hero in winners else 0.
        sw+=w; sw2+=w*w; uniform+=share
        equity+=w*share; wins+=w*(share==1); ties+=w*(0<share<1)
        payouts=[]
        for scenario in scenarios:
            money=0.
            for amount,eligible,count in scenario['pots']:
                if hero not in eligible: continue
                if count==1: money+=amount; continue
                top=max(vals[i] for i in eligible); ws=[i for i in eligible if vals[i]==top]
                if hero in ws: money+=amount/len(ws)
            payouts.append(money-scenario['call'])
        records.append((w,share,payouts))
        if missing:
            group=groups[drawn[0]]; group[0]+=w; group[1]+=w*share; group[2]+=w*w; group[3]+=1
    if not sw: raise ValueError('范围权重退化，无法计算')
    eq=equity/sw; ess=sw*sw/sw2
    se=math.sqrt(sum(w*w*(x-eq)**2 for w,x,_ in records))/sw
    estimates=[]
    for n,s in enumerate(scenarios):
        ev=sum(w*ps[n] for w,_,ps in records)/sw
        err=1.96*math.sqrt(sum(w*w*(ps[n]-ev)**2 for w,_,ps in records))/sw
        estimates.append(dict(**s,ev=ev,error=err))
    return dict(equity=eq,win=wins/sw,tie=ties/sw,loss=1-(wins+ties)/sw,
                uniform=uniform/samples,ess=ess,error=1.96*se,groups=dict(groups),estimates=estimates)


def cost_scenarios(v,live):
    seat=v['seat']; call=v['legal'].get('call',0); players=v['players']
    current=max(p['bet'] for p in players)
    pending=[i for i in live if i!=seat and players[i]['stack']>0 and players[i]['bet']<current]
    totals=[p['total'] for p in players]; totals[seat]+=call
    result=[]
    for mode in (['其余未回应者弃牌','其余未回应者跟平'] if pending else ['当前跟注']):
        ts=totals[:]; eligible=live[:]
        if pending:
            if mode.endswith('弃牌'): eligible=[i for i in live if i not in pending]
            else:
                for i in pending: ts[i]+=min(players[i]['stack'],current-players[i]['bet'])
        pots=list(eligible_pots(ts,eligible))
        contest=sum(a for a,e,n in pots if seat in e and n>1)
        refund=sum(a for a,e,n in pots if seat in e and n==1)
        result.append(dict(label=mode,pots=pots,call=call,contestable=contest,
                           threshold=max(0,call-refund)/contest if contest else None))
    return result,pending


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
        result.append(dict(label=label,equity=sim['equity'],delta=sim['equity']-previous,error=sim['error'],ess=sim['ess']))
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
    scenarios,pending=cost_scenarios(v,live)
    if v['turn']!=seat or hero['stack']==0: scenarios=[]; pending=[]
    sim=simulate(v,v['board'],live,tables,samples,seed,scenarios)
    current,hand,used=describe(v['hole'],v['board'])
    result=dict(inactive=False,**sim,samples=samples,current=current,best=hand,used=used,
                ranges=ranges,history_complete=v['history_complete'],paths=own_paths(v,sim,tables),
                timeline=replay(v,samples,seed),detail=detail,board=v['board'],hole=v['hole'],
                live_count=len(live),call=v['legal'].get('call',0),alternative=None)
    estimates=sim['estimates']
    if v['turn']!=seat: advice='等待你行动后更新建议。'
    elif hero['stack']==0: advice='你已全押，等待结算。'
    elif v['legal'].get('check'): advice='过牌'
    elif pending or sim['ess']<100 or any(abs(e['ev'])<=e['error'] for e in estimates):
        advice='条件建议：结果不够稳定，不能确定跟注有利。'
        if pending: advice+=' 还有其他玩家未回应，需分别看弃牌／跟平情景，并考虑重新加注。'
    else: advice=('跟注 '+str(result['call'])) if estimates[0]['ev']>0 else '弃牌'
    result['advice']=advice
    minimum=v['legal'].get('raise_to_min'); cap=v['legal'].get('raise_to_max')
    if v['turn']==seat and minimum is not None and cap>=minimum and sim['equity']>.65:
        target=min(cap,max(minimum,hero['bet']+result['call']+max(10,(sum(p['total'] for p in v['players'])+result['call'])//2)))
        result['alternative']=f'加注到 {target}：仅作启发式备选，未估计弃牌率及加注收益。'
    return result


def render_analysis(a):
    from .display import cards,pad
    line='─'*64; lines=['','辅助分析 · 公开信息推演',line]
    if a['inactive']: return '\n'.join(lines+[a['reason']])
    pct=lambda x:f'{x:.1%}'
    row=lambda k,v:'  '+pad(k,20)+str(v)
    lines+=['【当前局面】',row('我的牌',a['current']),row('在局人数',a['live_count'])]
    if a['best']: lines += [row('最佳五张',cards(a['best'])),row('其中我的底牌',cards(a['used']) if a['used'] else '未使用')]
    lines+=['','【对手可能拿什么】','  以下占比是规则模型权重，不是已知底牌或经校准的真实概率。']
    for opponent in a['ranges']:
        lines.append('  '+opponent['name']+'｜依据：'+(' → '.join(opponent['evidence']) or '没有可用动作证据，保持均匀范围'))
        shown=opponent['groups'] if a['detail'] else [g for n,g in enumerate(opponent['groups']) if n<3 or g['label'] in ('弱牌','其他')]
        for g in shown:
            lines.append('    '+g['label']+' '+pct(g['prob'])+' · 例如 '+cards(g['example'])+' → '+g['description'])
        if a['board']:
            lines.append('    当前领先我的候选权重 '+pct(opponent['ahead'])+'（仅比较现有公共牌，仍可能被后续逆转）')
    if not a['history_complete']: lines.append('  历史不完整：未推测缺失动作，已退回随机范围。')
    lines+=['','【我的关键出路】']
    if not a['board']:
        lines+=['  翻牌前先看起手牌结构和参与人数；发出翻牌后展示具体改善与危险来牌。']
    elif len(a['board'])==5:
        lines+=['  已到河牌，没有后续补牌。上方候选范围说明可能领先你的成牌；不是对手真实持牌。']
        for opponent in a['ranges']:
            lines.append('  '+opponent['name']+'领先我的范围权重：'+pct(opponent['ahead']))
            for candidate in opponent['leading']:
                lines.append('    领先示例：'+cards(candidate['hole'])+' → '+candidate['description'])
    else:
        lines+=['  “改善”指成牌等级提高，不等于获胜；风险按牌面结构与抽样权益标注。',
                '  每组为多张来牌合计，风险例只对应指定来牌；各组互斥，概率可相加。']
        for g in a['paths']['groups']:
            lines.append('  '+g['label']+f'｜下一张 {len(g["items"])} 张 · '+pct(g['prob']))
            # Aggregate category and rank routes, leaving every suit explicit in detail mode.
            bycat=defaultdict(list)
            for item in g['items']: bycat[item['route']].append(item)
            for cat,items in bycat.items():
                byrank=defaultdict(list)
                for item in items: byrank[item['card'][0]].append(item['card'])
                labels=[]
                for rank,values in byrank.items():
                    known_ranks=[c for c in DECK if c[0]==rank and c not in a['hole']+a['board']]
                    labels.append(('10' if rank=='T' else rank)+'（所有剩余花色）' if set(values)==set(known_ranks) else cards(values))
                if len(items)>12:
                    suit_groups=defaultdict(list)
                    for rank,values in byrank.items():
                        suits=tuple(c[1] for c in values)
                        suit_groups[suits].append('10' if rank=='T' else rank)
                    suit_symbols=dict(s='♠',h='♥',d='♦',c='♣')
                    labels=['牌点 '+' / '.join(ranks)+'（均为 '+' / '.join(suit_symbols[s] for s in suits)+'）' for suits,ranks in suit_groups.items()]
                lines.append('    → '+cat+'：'+' / '.join(labels)+f'（共 {len(items)} 张）')
            lines.append('    命中后模型权益：'+(pct(g['equity'])+f'（较当前 {(g["equity"]-a["equity"])*100:+.1f} 个百分点）' if g['equity'] is not None else '有效样本不足 100，无法判断'))
            if g['threat']:
                t=g['threat']
                lines.append('    风险例：来 '+cards([t['card']])+' 时，'+t['opponent']+'若持 '+cards(t['hole'])+' 可成 '+t['description']+'，仍领先我。')
            lines.append('    '+g['items'][0]['reason'])
        lines.append('  到河牌最终牌型（均匀未知牌枚举；不是获胜率）：')
        lines.append('    '+' · '.join(NAMES[i]+' '+pct(p) for i,p in enumerate(a['paths']['distribution']) if p))
        unreachable=[NAMES[i] for i,p in enumerate(a['paths']['distribution']) if not p]
        if unreachable: lines.append('  不可达：'+' / '.join(unreachable))
    lines+=['','【权益为什么变化】',row('当前行为加权权益',pct(a['equity'])),row('随机范围参照',pct(a['uniform'])),
            row('独赢 / 平局 / 落败',' / '.join(pct(a[k]) for k in ('win','tie','loss')))]
    if a['timeline']:
        for step in a['timeline']:
            lines.append('  '+step['label']+' → '+pct(step['equity'])+f'（{step["delta"]*100:+.1f} 个百分点）'+(' · 有效样本不足' if step['ess']<100 else ''))
        lines.append('  按实际事件顺序逐步重算；属于模型内分解，不是客观因果证明。')
    else: lines.append('  尚无上个用户行动点或历史不完整，暂不展示变化归因。')
    lines+=['','【行动建议】',row('建议',a['advice'])]
    if a['alternative']: lines.append('  备选：'+a['alternative'])
    for e in a['estimates']:
        lines.append('  '+e['label']+f'｜跟注 {e["call"]} · 可争夺池 {e["contestable"]}')
        lines.append('    所需分池加权权益 '+(pct(e['threshold']) if e['threshold'] is not None else '不适用')+f' · 估算净收益 {e["ev"]:+.1f} ±{e["error"]:.1f}（约 95% 抽样区间）')
    lines+=['  假设此后无额外下注；未回应者的跟平／弃牌是条件情景，不分配发生概率。',
            '  整体摊牌权益与分池加权门槛口径不同，不能直接比较。',
            '  净收益区间只反映抽样波动，未覆盖范围估计误差。',
            '', '【计算口径】',row('模型版本',VERSION+'（人工规则，未校准）'),
            row('模拟 / 有效样本',f'{a["samples"]} / {a["ess"]:.0f}'),
            row('权益抽样误差',f'约 95% ±{pct(a["error"])}，不含范围假设误差'),
            '  成牌概率按均匀未知牌枚举，不含行为范围的阻断效应；权益按范围加权模拟。']
    if a['ess']<100: lines.append('  有效样本不足，请增加 --samples；不据此给确定盈利建议。')
    if a['detail']:
        lines+=['','【逐张下一公共牌】']
        for x in a['paths']['details']:
            lines.append('  '+cards([x['card']])+' → '+x['category']+'｜'+x['group']+'｜条件权益 '+(pct(x['equity']) if x['equity'] is not None else '有效样本不足 100，无法判断'))
        lines+=['','【范围规则】','  翻牌前：强牌 TT+ / AQ / AK；可玩牌为其他对子、双大牌、同花 A、同花相邻牌。',
                '  加注权重 4/2/1，跟注 2/3/1；庄位及前一位置加注，后两类再乘 1.5。',
                '  翻牌后：强成牌（两对以上／超对）、普通成牌、听牌、弱牌。成牌优先归类。',
                '  下注／加注权重 4/2/2/1，跟注 3/3/2/1，过牌不调整。',
                '  小于半池下注与均匀权重折半；超过一池的非弱牌权重乘 1.5。',
                '  每次公开行为乘入权重；发牌移除冲突组合，保留非零诈唬范围。']
    else: lines.append('  --assist-detail 展开逐张来牌、全部候选类型及权重规则。')
    return '\n'.join(lines+[line])
