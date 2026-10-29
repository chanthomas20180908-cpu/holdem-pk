"""Decision replay from public event prefixes only."""
from copy import deepcopy


def review(v, samples, seed, detail):
    from .assist import analyze
    from .predict import betting_state
    from .__main__ import legal
    result = dict(inactive=True, reason='', review=True, decisions=[], detail=detail)
    starts = v.get('hand_start_stacks', [])
    hero = v['seat']
    result['refund'] = v.get('settlement', {}).get('refunds', [0]*len(v['players']))[hero]
    result['net'] = v['players'][hero]['stack']-starts[hero] if len(starts)==len(v['players']) else None
    if not v['history_complete'] or len(starts)!=len(v['players']):
        result['reason'] = '公开记录不完整，无法可靠还原决策。'
        return result
    x=deepcopy(v)
    x.update(done=False,board=[],events=[],turn=None,legal={},settlement={})
    for i,p in enumerate(x['players']):
        p.update(stack=starts[i],bet=0,total=0,folded=starts[i]<=0)
    for event in v['events']:
        if event['kind']=='action' and event['seat']==hero:
            x['turn']=hero
            x['legal']={}
            state,_=betting_state(x)
            state['acted']=[i for i in state['acted'] if i != hero]
            x['legal']=legal(state)
            a=analyze(deepcopy(x),samples,seed,False)
            prediction=a.get('prediction')
            if prediction:
                action=event['action']; target=event.get('bet')
                actual=next((c for c in prediction['actions'] if c['action']==action and (action!='raise' or c['target']==target)),None)
                if actual is None:
                    from .predict import predict_actions
                    from .assist import range_tables
                    live=[i for i,p in enumerate(x['players']) if not p['folded']]
                    tables,_=range_tables(x,x['board'],x['events'],live)
                    choice=dict(action=action,target=target,paid=event['paid'],label=('加注到 '+str(target)) if action=='raise' else action)
                    actual=predict_actions(x,tables,[choice],samples,seed or 0)['best']
                result['decisions'].append(dict(board=list(x['board']),actual=actual,best=prediction['best']))
        if event['kind']=='deal':
            x['board']=list(event['cards'])
            for p in x['players']: p['bet']=0
        elif event['kind'] in ('action','blind'):
            p=x['players'][event['seat']]
            p['stack']-=event['paid'];p['total']+=event['paid'];p['bet']=event['bet']
            if event.get('action')=='fold':p['folded']=True
        x['events'].append(deepcopy(event))
    return result
