"""Public-information regressions and independent betting/payout checks."""
import copy
import itertools
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from holdem.__main__ import act, legal, score, settle, start_hand, view
from holdem.assist import (analyze, public_snapshot, render_analysis, range_tables,
                           cost_scenarios, action_scenarios)
from holdem.predict import (betting_state, clone, outcome, simulate_choice,
                            continuation_policies, summarize, select_action, Outcome)
from holdem.ranges import features, response_probabilities, weight

FROZEN = Path(__file__).parent/'fixtures'/'河牌顺子威胁_20261027-213656-849524.json'


def frozen():
    return json.loads(FROZEN.read_text())['snapshot']


def heads_up():
    return dict(hand=1, board=['5s','8c','Td','5c','Jd'], players=[
        dict(name='你', stack=1000,bet=0,total=100,folded=False),
        dict(name='对手',stack=1000,bet=0,total=100,folded=False)],
        seat=0,hole=['Js','Qd'],turn=0,done=False,button=0,
        events=[],history_complete=False,
        legal=dict(fold=True,check=True,call=0,raise_to_min=10,raise_to_max=1000))


class ResponseModelTests(unittest.TestCase):
    def test_board_relative_rating_separates_weak_and_strong_two_pair(self):
        board=tuple(heads_up()['board'])
        weak=features(('2s','2h'),board)
        strong=features(('Ah','Jh'),board)
        straight=features(('Qc','9h'),board)
        house=features(('Ts','Th'),board)
        self.assertEqual([weak['label'],strong['label'],straight['label'],house['label']],
                         ['弱两对','强两对','顺子','葫芦'])
        self.assertLess(weak['strength'],strong['strength'])
        self.assertLess(strong['strength'],straight['strength'])
        self.assertLess(straight['strength'],house['strength'])
        action=dict(action='raise',board=list(board),late=False,ratio=.7)
        self.assertLess(weight(['2s','2h'],[action]),weight(['Ah','Jh'],[action]))

    def test_public_board_draw_is_not_a_private_draw(self):
        f=features(('As','Kd'),('5c','6c','7c','8c'))
        self.assertFalse(f['draw'])
        with_club=features(('Ac','Kd'),('5c','6c','7c','8c'))
        self.assertTrue(with_club['draw'])

    def test_completed_monster_is_not_downgraded_by_draw_bonus_cap(self):
        f=features(('Ac','Kc'),('Qc','Jc','Tc','2h'))
        self.assertEqual(f['label'],'同花顺')
        self.assertEqual(f['strength'],1.)

    def test_response_probabilities_normalized_price_and_hand_sensitive(self):
        board=tuple(heads_up()['board'])
        def probs(hand,call,can_raise=True):
            return response_probabilities(hand,board,call=call,pot=500,opponents=2,can_raise=can_raise)
        weak=probs(('2s','2h'),140)
        strong=probs(('Qc','9h'),140)
        dear=probs(('2s','2h'),800)
        for p in (weak,strong,dear,probs(('2s','2h'),0),probs(('Qc','9h'),140,False)):
            self.assertAlmostEqual(sum(p.values()),1)
            self.assertTrue(all(0<=v<=1 for v in p.values()))
        self.assertGreater(dear['fold'],weak['fold'])
        self.assertLess(strong['fold'],weak['fold'])
        self.assertEqual(probs(('2s','2h'),0)['fold'],0)
        self.assertEqual(probs(('Qc','9h'),140,False)['raise_'],0)

    def test_royal_board_is_not_folded_or_raised_as_private_nuts(self):
        p=response_probabilities(('2h','3d'),('Ts','Js','Qs','Ks','As'),
                                 call=100,pot=200,opponents=2,can_raise=True)
        self.assertEqual(p,dict(fold=0.,call=1.,raise_=0.))

    def test_public_reopen_and_pending_recovery_matches_engine(self):
        s=dict(hand=0,button=5,players=[dict(name=str(i),stack=1000) for i in range(6)])
        start_hand(s)
        act(s,3,'raise',30)
        act(s,4,'call')
        # A short all-in does not reopen an already acted player's raise.
        s['players'][5]['stack']=40
        act(s,5,'raise',40)
        act(s,0,'call')
        act(s,1,'fold')
        act(s,2,'call')
        self.assertEqual(s['turn'],3)
        v=public_snapshot(view(s,3),3)
        reconstructed, approximate=betting_state(v)
        self.assertFalse(approximate)
        self.assertEqual(legal(reconstructed),legal(s))
        self.assertEqual(set(reconstructed['pending']),set(s['pending']))
        self.assertEqual(set(reconstructed['acted']),set(s['acted']))
        self.assertIsNone(legal(reconstructed)['raise_to_min'])
        self.assertNotIn('deck',reconstructed)
        self.assertTrue(all('hole' not in p for p in reconstructed['players']))

    def test_memory_only_round_stop_never_deals_or_settles_live_style_state(self):
        v=heads_up()
        state,_=betting_state(v)
        before_board=state['board'][:]
        act(state,0,'check',stop_at_round_end=True)
        act(state,1,'check',stop_at_round_end=True)
        self.assertTrue(state['round_closed'])
        self.assertIsNone(state['turn'])
        self.assertEqual(state['board'],before_board)
        self.assertNotIn('awards',state)
        self.assertEqual(sum(p['stack']+p['total'] for p in state['players']),2200)
        self.assertEqual(v,heads_up())

    def test_preflop_round_stop_does_not_draw_the_flop(self):
        s=dict(hand=0,button=0,players=[dict(name=str(i),stack=1000) for i in range(2)])
        start_hand(s)
        act(s,s['turn'],'call')
        seat=s['turn']
        v=public_snapshot(view(s,seat),seat)
        simulated,_=betting_state(v)
        act(simulated,seat,'check',stop_at_round_end=True)
        self.assertTrue(simulated['round_closed'])
        self.assertEqual(simulated['board'],[])
        self.assertNotIn('deck',simulated)
        act(s,seat,'check')
        self.assertEqual(s['street'],'flop')
        self.assertEqual(len(s['board']),3)

    def test_forecasts_are_legal_for_all_streets_and_nonzero_hero_seats(self):
        import random
        for players in (2,6,8):
            s=dict(hand=0,button=0,players=[dict(name=str(i),stack=200) for i in range(players)])
            with patch('holdem.__main__.random.SystemRandom',return_value=random.Random(17)):
                start_hand(s)
            seen=set()
            while not s['done']:
                seat=s['turn']
                if s['street'] not in seen:
                    seen.add(s['street'])
                    v=public_snapshot(view(s,seat),seat)
                    before=copy.deepcopy(v)
                    a=analyze(v,100,seed=71)
                    self.assertEqual(v,before)
                    self.assertNotIn('不确定',a['advice'])
                    for choice in a['prediction']['actions']:
                        probe=copy.deepcopy(s)
                        act(probe,seat,choice['action'],choice.get('target'),stop_at_round_end=True)
                        self.assertTrue(0<=choice['win']<=1+1e-9)
                    self.assertEqual(a['advice'],a['prediction']['best']['label'])
                act(s,seat,'check' if legal(s)['check'] else 'call')
            self.assertEqual(seen,{'preflop','flop','turn','river'})

    def test_raise_path_and_fallback_do_not_use_sampled_opponent_or_future_values(self):
        v=heads_up()
        root,_=betting_state(v)
        choice=dict(action='raise',target=100,label='下注到 100',paid=100)
        hands={0:tuple(v['hole']),1:('9h','Qc')}
        rolls=[[.5]*3,[.5]*3]
        def force_raise(state,seat,hole,roll,raises,pressure):
            options=legal(state)
            return ('raise',options['raise_to_min']) if raises==0 else ('call',None)
        with patch('holdem.predict.response',side_effect=force_raise):
            first=simulate_choice(root,v,choice,hands,rolls,{0:(2,11,5,12),1:(4,12)},0)
            second=simulate_choice(root,v,choice,hands,rolls,{0:(8,14),1:(0,14)},0)
        self.assertEqual(first[2:],second[2:])
        self.assertNotEqual(first[0].net,second[0].net)
        self.assertEqual(sum(seat!=0 and action=='raise' for seat,action,_ in first[2]),1)
        self.assertNotIn('hole',str(first[2]))
        self.assertEqual(root,betting_state(v)[0])

    def test_public_path_continuation_is_pooled_not_a_per_world_oracle(self):
        key=((0,'raise',10),(1,'raise',30))
        def result(net):
            return Outcome(net,5,0,False,False,False,(),())
        records=[(1.,result(100),result(-5),key,False)]*30
        records += [(1.,result(-120),result(-5),key,False)]*30
        policy,rare=continuation_policies(records)
        self.assertFalse(policy[key])
        self.assertFalse(rare)
        summary,_=summarize(dict(action='raise',label='下注到 5',paid=5),records)
        self.assertEqual(summary['ev'],-5)
        policy,rare=continuation_policies(records[:1])
        self.assertFalse(policy[key])
        self.assertIn(key,rare)

    def test_folding_to_a_raise_does_not_invent_a_side_pot(self):
        key=((0,'raise',10),(1,'raise',100))
        called=Outcome(-100,100,0,False,False,False,(('主池',400,False,False,False),),())
        folded=Outcome(-10,10,0,False,False,False,(),('主池',))
        rows=[(1.,called,folded,key,False)]*60
        summary,_=summarize(dict(action='raise',label='下注到 10',paid=10),rows)
        self.assertFalse(summary['split'])
        self.assertEqual(summary['win'],0)
        self.assertEqual(summary['ev'],-10)

    def test_ev_priority_and_lower_spend_for_statistical_ties(self):
        def action(label,paid,ev,win,kind='raise'):
            return dict(label=label,paid=paid,ev=ev,win=win,loss_risk=.2,action=kind)
        results=[action('高胜率',100,10,.9),action('高收益',50,30,.6)]
        self.assertEqual(select_action(results,[[10]*100,[30]*100],[1.]*100)[0],1)
        # Even when checking is legal, a clear value bet should be considered.
        results=[action('过牌',0,20,.9,'check'),action('下注',50,80,.9)]
        self.assertEqual(select_action(results,[[20]*100,[80]*100],[1.]*100)[0],1)
        results=[action('不稳定跟注',100,1,.8,'call'),action('弃牌',0,0,0,'fold')]
        self.assertEqual(select_action(results,[[101,-99]*50,[0]*100],[1.]*100)[0],1)
        results=[action('跟注',100,-20,.8,'call'),action('弃牌',0,0,0,'fold')]
        self.assertEqual(select_action(results,[[-20]*100,[0]*100],[1.]*100)[0],1)

    def test_sampled_payouts_match_rule_engine_for_every_small_deck_assignment(self):
        v=heads_up()
        v['players'].append(dict(name='短码',stack=0,bet=0,total=20,folded=False))
        root,_=betting_state(v)
        base,_=cost_scenarios(v,[0,1,2])
        choices,_=action_scenarios(v,[0,1,2],base)
        candidates=['As','Ah','3s','3d','9s','9d']
        for first in itertools.combinations(candidates,2):
            for second in itertools.combinations([c for c in candidates if c not in first],2):
                hands={0:v['hole'],1:list(first),2:list(second)}
                values={i:score(hand+v['board']) for i,hand in hands.items()}
                for choice in choices:
                    if choice['action']=='fold':
                        continue
                    for fold in (False,True):
                        state=clone(root)
                        act(state,0,choice['action'],choice.get('target'),stop_at_round_end=True)
                        while not state['round_closed']:
                            options=legal(state)
                            action='fold' if fold else 'check' if options['check'] else 'call'
                            act(state,state['turn'],action,stop_at_round_end=True)
                        observed=outcome(state,v,values)
                        engine=clone(state)
                        for i,hand in hands.items():
                            engine['players'][i]['hole']=hand
                        settle(engine)
                        self.assertEqual(observed.net,engine['awards'][0]-observed.paid)
                        self.assertEqual(observed.refund,engine['refunds'][0])
                        for label,amount,direct,sole,tie in observed.pots:
                            n=0 if label=='主池' else int(label.split()[1])
                            pot=engine['pots'][n]
                            self.assertEqual(amount,pot['amount'])
                            self.assertEqual(direct,len(pot['eligible'])==1)
                            self.assertEqual(sole,not direct and pot['winners']==[0])
                            self.assertEqual(tie,0 in pot['winners'] and len(pot['winners'])>1)


class PublicRiverRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v=frozen()
        cls.a=analyze(cls.v,2000)

    def test_frozen_snapshot_is_pre_action_and_has_no_opponent_hands(self):
        self.assertFalse(self.v['done'])
        self.assertEqual(self.v['turn'],0)
        self.assertEqual(self.v['legal']['call'],140)
        self.assertEqual(self.v['events'][-1]['seat'],3)
        self.assertEqual(self.v['events'][-1]['action'],'raise')
        self.assertNotIn('deck',self.v)
        self.assertTrue(all('hole' not in p for p in self.v['players']))
        self.assertTrue(all(e['kind'] in ('blind','deal','action','round_end') for e in self.v['events']))

    def test_all_straight_families_survive_threat_aggregation_and_default_display(self):
        tables,ranges=range_tables(self.v,self.v['board'],self.v['events'],[0,2,3])
        hands=[h for h in tables[3] if {c[0] for c in h}=={'Q','9'}]
        self.assertEqual(len(hands),12)
        self.assertTrue(all(score(list(h)+self.v['board'])[0]==4 for h in hands))
        for opponent in ranges:
            threat=next(t for t in opponent['threats'] if t['label']=='顺子')
            self.assertEqual(threat['combos'],28)
            self.assertEqual(set(threat['families']),{'Q＋9','9＋7'})
            self.assertGreater(threat['prob'],0)
            self.assertAlmostEqual(sum(t['prob'] for t in opponent['threats']),opponent['ahead'])
        text=render_analysis(self.a,format='markdown')
        self.assertIn('Q＋9',text)
        self.assertIn('9＋7',text)
        self.assertIn('顺子',text)
        self.assertIn('对手关键威胁',text)

    def test_pending_players_do_not_cancel_advice_and_actions_have_forecasts(self):
        p=self.a['prediction']
        self.assertEqual(self.a['advice'],p['best']['label'])
        self.assertNotIn('不确定',self.a['advice'])
        self.assertIn(self.a['advice'],[c['label'] for c in self.a['comparisons']])
        self.assertIn(p['confidence'],('高','中','低'))
        self.assertIsNotNone(p['backup'])
        for c in p['actions']:
            self.assertAlmostEqual(c['win'],c['direct']+c['showdown'])
            self.assertLessEqual(c['win']+c['tie'],1+1e-9)
            self.assertTrue(0<=c['loss_risk']<=1)
            for pot in c['pot_results']:
                self.assertAlmostEqual(pot['win'],pot['direct']+pot['showdown'])
        spending=[c for c in p['actions'] if c['action']!='fold']
        self.assertGreater(len({round(c['win'],3) for c in spending}),1)
        self.assertGreater(p['ess'],100)
        # No assertion that a losing historical hand must recommend folding.
        # Selection is assessed from information available before the call.

    def test_no_real_opponent_cards_or_deck_influence_forecasts(self):
        other=copy.deepcopy(self.v)
        other['players'][3]['hole']=['2h','2d']
        other['deck']=['As','Ah']
        other['future_board']=['Ac']
        self.assertEqual(self.a['prediction'],analyze(other,2000)['prediction'])

    def test_no_sample_future_leak_in_historical_replay(self):
        self.assertAlmostEqual(self.a['timeline'][-1]['win'],self.a['win'])
        self.assertAlmostEqual(self.a['timeline'][0]['win']+
                               sum(s['win_delta'] for s in self.a['timeline'][1:]),self.a['win'])

    def test_forecast_probabilities_not_dependent_on_display_detail(self):
        changed=copy.deepcopy(self.a)
        changed['detail']=True
        before=copy.deepcopy(changed)
        text=render_analysis(changed,format='markdown')
        self.assertIn('反加与追加投入',text)
        self.assertEqual(changed,before)
        self.assertNotIn('模型版本',text)
        self.assertNotIn('计算口径',text)

    def test_refund_and_side_pot_probabilities_not_counted_as_whole_hand_wins(self):
        v=heads_up()
        v['players'][0]['total']=50
        v['players'][1].update(stack=0,total=20)
        v['players'].append(dict(name='远帆',stack=1000,bet=0,total=50,folded=False))
        a=analyze(v,500,seed=42)
        for c in a['prediction']['actions']:
            if c['action']=='fold':
                continue
            self.assertEqual(c['direct'],0)  # Main pot has an all-in opponent.
            self.assertTrue(c['split'])
            self.assertTrue(any(p['label']=='主池' for p in c['pot_results']))
            for pot in c['pot_results']:
                self.assertAlmostEqual(pot['win'],pot['direct']+pot['showdown'])
        self.assertIn('分池',render_analysis(a,format='markdown'))

    def test_adaptive_sampling_has_a_bound_and_keeps_an_action(self):
        a=analyze(self.v,100,seed=42)
        p=a['prediction']
        self.assertGreater(p['samples'],100)
        self.assertLessEqual(p['samples'],10000)
        self.assertTrue(p['ess']>=100 or p['samples']==10000)
        self.assertEqual(a['advice'],p['best']['label'])


if __name__=='__main__':
    unittest.main()
