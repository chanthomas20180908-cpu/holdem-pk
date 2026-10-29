"""Public evidence and persistent Agent-authored coaching; no model calls."""
import hashlib
import itertools
import json
from datetime import datetime
from pathlib import Path
from .__main__ import view, score, RANKS


def context(visible, seat):
    from .assist import public_snapshot, describe
    x=public_snapshot(visible,seat)
    x['street']=visible['street']
    x['pot']=visible['pot']
    x['position']=visible.get('positions',{})
    call=x['legal'].get('call',0)
    x['call_equity_threshold']=call/(x['pot']+call) if call else 0
    x['effective_stacks']={str(i):min(x['players'][seat]['stack'],p['stack']) for i,p in enumerate(x['players']) if i!=seat and not p['folded']}
    x['made_hand']=describe(x['hole'],x['board'])[0] if len(x['hole'])==2 else None
    x['snapshot_id']=hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return x


def directory(state):
    return state.parent/'coach'/hashlib.sha256(str(state.resolve()).encode()).hexdigest()[:16]


def reports(state):
    folder=directory(state)
    return [json.loads(p.read_text()) for p in sorted(folder.glob('*.json'))] if folder.exists() else []


def render(r):
    lines=['### 本手复盘' if r['snapshot']['done'] else '### 教练建议','']
    for key,label in [('recommendation','建议'),('reason','为什么'),('alternative','备选'),('plan','下一步'),('lesson','下次记住'),('self_review','教练自检')]:
        if r.get(key): lines.extend([f'**{label}**：'+r[key],''])
    return '\n'.join(lines).rstrip()


def panel(visible,state,seat):
    x=context(visible,seat)
    found=[r for r in reports(state) if r['snapshot']['snapshot_id']==x['snapshot_id']]
    return render(found[-1]) if found else '### 教练分析\n\n等待当前 Agent 根据公开上下文生成'+('本手复盘。' if x['done'] else '策略建议。')


def run(s,state,args):
    x=context(view(s,args.seat),args.seat)
    if args.operation in ('context','review-context'):
        out=dict(snapshot=x)
        if args.operation=='review-context':
            out['reports']=[r for r in reports(state) if r['snapshot']['hand']==x['hand'] and r['snapshot']['seat']==args.seat]
            out['settlement']= {k:view(s,args.seat).get(k) for k in ('awards','refunds','pots','hand_start_stacks')}
            if s['done']:
                out['public_showdown']=[dict(seat=i,hole=p['hole']) for i,p in enumerate(view(s,args.seat)['players']) if i!=args.seat and 'hole' in p]
        return json.dumps(out,ensure_ascii=False,indent=2)
    if not args.input: raise ValueError('需要 --input JSON 文件')
    r=json.loads(Path(args.input).read_text())
    if r.get('snapshot_id')!=x['snapshot_id']: raise ValueError('报告快照已过期')
    if args.operation=='equity':
        if len([p for p in x['players'] if not p['folded']])!=2: raise ValueError('首版权益核验仅支持单挑明确范围')
        known=x['hole']+x['board']; hands=r.get('range',[])
        if not hands: raise ValueError('候选范围不能为空')
        win=tie=total=0
        for h in hands:
            if len(h)!=2 or len(set(known+h))!=len(known)+2 or any(c not in [a+b for a in RANKS for b in 'shdc'] for c in h): raise ValueError('候选范围牌码冲突或无效')
            deck=[a+b for a in RANKS for b in 'shdc' if a+b not in known+h]
            if len(x['board'])<3: raise ValueError('首版精确核验支持翻牌后')
            for extra in itertools.combinations(deck,5-len(x['board'])):
                a=score(x['hole']+x['board']+list(extra));b=score(h+x['board']+list(extra))
                win+=a>b;tie+=a==b;total+=1
        return json.dumps(dict(assumed_range=hands,win=win/total,tie=tie/total,equity=(win+tie/2)/total),ensure_ascii=False)
    for key in ('recommendation','reason','plan'):
        if not isinstance(r.get(key),str) or not r[key].strip(): raise ValueError('缺少教练内容：'+key)
    if not x['done']:
        action=r.get('action'); legal=x['legal']
        if action not in ('fold','check','call','raise') or not legal: raise ValueError('没有合法决策资格')
        if action=='check' and not legal['check']: raise ValueError('不能过牌')
        if action=='raise':
            target=r.get('target');lo=legal.get('raise_to_min');hi=legal.get('raise_to_max')
            if hi is None or not isinstance(target,int) or target>hi or (target<lo and target!=hi): raise ValueError('加注金额不合法')
    elif not all(r.get(k) for k in ('lesson','self_review')): raise ValueError('复盘需要学习点和教练自检')
    r['snapshot']=x;r['created_at']=datetime.now().astimezone().isoformat()
    folder=directory(state);folder.mkdir(parents=True,exist_ok=True)
    name='教练报告_'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'
    (folder/name).write_text(json.dumps(r,ensure_ascii=False,indent=2))
    return render(r)
