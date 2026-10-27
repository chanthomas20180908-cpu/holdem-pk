import copy
import unittest
from holdem.assist import public_snapshot, analyze, eligible_pots, render_analysis, range_tables, replay
from holdem.ranges import weight, bucket, contexts


class AssistTests(unittest.TestCase):
    def fixture(self):
        return dict(hand=1,board=['Ts','Js','Qs','Ks','As'],players=[
            dict(name='你',hole=['2h','3d'],stack=100,bet=10,total=10,folded=False),
            dict(name='对手',hole=['4h','5d'],stack=100,bet=10,total=10,folded=False)],
            turn=0,done=False,button=0,history_complete=False,
            legal=dict(call=0,check=True,raise_to_min=20,raise_to_max=110))

    def test_hidden_information_and_names_invariance(self):
        first=self.fixture(); second=copy.deepcopy(first)
        first['deck']=['2s']; second['deck']=['3s']
        second['players'][1]['hole']=['Ah','Ad']
        second['events']=[dict(kind='secret',hole=['Ah','Ad'])]
        a=public_snapshot(first); b=public_snapshot(second)
        self.assertEqual(a,b)
        self.assertEqual(analyze(a,100,42),analyze(b,100,42))
        self.assertNotIn('hole',a['players'][1])
        second['players'][1]['name']='另一个角色'
        self.assertEqual(analyze(a,100,42)['equity'],analyze(public_snapshot(second),100,42)['equity'])

    def test_allowlist_events(self):
        v=self.fixture(); v['events']=[dict(kind='deal',cards=['Ts','Js','Qs'],secret='x'),
            dict(kind='action',seat=1,action='call',paid=10,bet=10,hole=['Ah','Ad'])]
        events=public_snapshot(v)['events']
        self.assertNotIn('secret',events[0]); self.assertNotIn('hole',events[1])

    def test_board_tie_and_repeatability(self):
        snapshot=public_snapshot(self.fixture())
        a=analyze(snapshot,100)
        self.assertEqual(a,analyze(snapshot,100))
        self.assertEqual((a['win'],a['tie'],a['equity']),(0,1,.5))
        self.assertEqual(a['estimates'][0]['ev'],10)
        self.assertEqual(a['advice'],'过牌')
        self.assertIn('公共牌即可组成',a['current'])

    def test_nuts_stays_conservative_but_compares_raises(self):
        v=self.fixture(); v['board']=['Ts','Js','Qs','2c','3c']
        v['players'][0]['hole']=['Ks','As']
        a=analyze(public_snapshot(v),100,1)
        self.assertEqual(a['win'],1)
        self.assertEqual(a['advice'],'过牌')
        self.assertIsNone(a['alternative'])
        self.assertEqual([c['target'] for c in a['comparisons'] if c['action']=='raise'], [20,30,110])
        self.assertIn('没有后续补牌',render_analysis(a))

    def test_no_advice_out_of_turn(self):
        v=self.fixture(); v['turn']=1
        a=analyze(public_snapshot(v),100,1)
        self.assertIn('等待',a['advice'])
        self.assertIsNone(a['alternative'])
        self.assertEqual(a['estimates'],[])

    def test_sidepots_and_refund(self):
        self.assertEqual(list(eligible_pots([20,50,100],[0,1,2])),
                         [(60,[0,1,2],3),(60,[1,2],2),(50,[2],1)])

    def test_multiway_tie(self):
        v=self.fixture(); v['players'].append(dict(v['players'][1]))
        a=analyze(public_snapshot(v),100,1)
        self.assertAlmostEqual(a['equity'],1/3)
        self.assertAlmostEqual(a['estimates'][0]['ev'],10)

    def test_short_stack_side_pot_excluded(self):
        v=self.fixture()
        v['players'][0].update(stack=10,bet=10,total=10)
        v['players'][1].update(bet=50,total=50)
        v['players'].append(dict(v['players'][1]))
        v['legal']=dict(call=10,check=False,raise_to_min=None,raise_to_max=None)
        a=analyze(public_snapshot(v),100,1)
        e=a['estimates'][0]
        self.assertEqual(e['contestable'],60)
        self.assertAlmostEqual(e['threshold'],1/6)
        self.assertAlmostEqual(e['ev'],10)
        self.assertEqual(a['advice'],'全押跟注 10')

    def test_pending_players_are_conditional_not_fake_sidepot(self):
        v=self.fixture()
        v['players'][0].update(bet=0,total=0)
        v['players'][1].update(bet=30,total=30)
        v['players'].append(dict(name='未回应',stack=100,bet=5,total=5,folded=False))
        v['legal']=dict(call=30,check=False,raise_to_min=60,raise_to_max=100)
        a=analyze(public_snapshot(v),100,1)
        self.assertEqual(len(a['estimates']),2)
        self.assertEqual([e['contestable'] for e in a['estimates']],[65,90])
        self.assertAlmostEqual(a['estimates'][0]['ev'],2)  # Odd chip goes left of the button.
        self.assertAlmostEqual(a['estimates'][1]['ev'],0)
        self.assertIn('条件建议',a['advice'])

    def test_inactive(self):
        v=self.fixture(); v['done']=True
        self.assertTrue(analyze(public_snapshot(v),100)['inactive'])
        v['done']=False; v['players'][0]['folded']=True
        self.assertTrue(analyze(public_snapshot(v),100)['inactive'])

    def test_exact_paths_and_detail(self):
        v=self.fixture(); v['board']=['6c','3h','Td','Kh']; v['players'][0]['hole']=['Ks','7d']
        a=analyze(public_snapshot(v),100,12,True)
        distribution=a['paths']['distribution']
        self.assertAlmostEqual(sum(distribution),1)
        self.assertAlmostEqual(distribution[3],2/46)
        self.assertEqual(distribution[5],0)
        self.assertEqual(sum(len(g['items']) for g in a['paths']['groups']),46)
        self.assertEqual(len({x['card'] for x in a['paths']['details']}),46)
        text=render_analysis(a)
        self.assertNotIn('不可达',text); self.assertIn('关键来牌展开',text)
        self.assertIn('K ♦',text)
        a['detail']=False
        self.assertNotIn('【关键来牌展开】',render_analysis(a))

    def test_range_rules_and_public_action_changes_equity(self):
        self.assertEqual(bucket(['As','Kh'],[]),0)
        self.assertEqual(bucket(['8s','7s'],[]),1)
        self.assertEqual(bucket(['8s','2h'],[]),2)
        action=dict(action='raise',board=[],late=False,ratio=1)
        self.assertEqual(weight(['As','Kh'],[action]),4)
        self.assertEqual(weight(['8s','2h'],[action]),1)
        v=self.fixture(); v['board']=['6c','3h','Td']; v['players'][0]['hole']=['Ks','7d']
        v['history_complete']=True; v['events']=[dict(kind='action',seat=1,action='raise',paid=30,bet=30)]
        snapshot=public_snapshot(v)
        tables,summaries=range_tables(snapshot,snapshot['board'],snapshot['events'],[0,1])
        self.assertAlmostEqual(sum(g['prob'] for g in summaries[0]['groups']),1)
        self.assertTrue(all(not(set(h)&set(snapshot['hole']+snapshot['board'])) for h in tables[1]))
        a=analyze(snapshot,1000,2)
        self.assertNotEqual(a['equity'],a['uniform'])
        snapshot['history_complete']=False
        b=analyze(snapshot,1000,2)
        self.assertAlmostEqual(b['equity'],b['uniform'])

    def test_replay_no_future_leak_and_telescopes(self):
        v=self.fixture(); v['board']=['6c','3h','Td','Kh']; v['players'][0]['hole']=['Ks','7d']
        v['history_complete']=True; v['events']=[
            dict(kind='blind',seat=0,paid=5,bet=5),dict(kind='blind',seat=1,paid=10,bet=10),
            dict(kind='action',seat=0,action='call',paid=5,bet=10),
            dict(kind='deal',cards=['6c','3h','Td']),
            dict(kind='action',seat=1,action='raise',paid=10,bet=10),
            dict(kind='action',seat=0,action='call',paid=10,bet=10),
            dict(kind='deal',cards=['6c','3h','Td','Kh']),
            dict(kind='action',seat=1,action='raise',paid=20,bet=20)]
        a=analyze(public_snapshot(v),100,10)
        v['board'][-1]='Ah'; v['events'][-2]['cards'][-1]='Ah'
        b=analyze(public_snapshot(v),100,10)
        self.assertEqual(a['timeline'][0],b['timeline'][0])
        self.assertAlmostEqual(a['timeline'][0]['equity']+sum(x['delta'] for x in a['timeline'][1:]),a['equity'])
        self.assertAlmostEqual(a['timeline'][-1]['equity'],a['equity'])

    def test_bet_ratio_excludes_call_portion(self):
        events=[dict(kind='blind',seat=0,paid=5,bet=5),dict(kind='blind',seat=1,paid=10,bet=10),
                dict(kind='action',seat=0,action='raise',paid=25,bet=30)]
        c=contexts(events,0,2)[0]
        self.assertAlmostEqual(c['ratio'],20/15)

    def test_public_state_not_mutated_and_pair_is_not_victory(self):
        v=self.fixture(); v['board']=['6c','3h','Td']; v['players'][0]['hole']=['Ks','7d']
        snapshot=public_snapshot(v); before=copy.deepcopy(snapshot)
        a=analyze(snapshot,100,7)
        self.assertEqual(snapshot,before)
        self.assertAlmostEqual(sum(g['prob'] for g in a['paths']['groups']),1)
        for group in a['paths']['groups']:
            threat=group['threat']
            if not threat: continue
            from holdem.__main__ import score
            b=snapshot['board']+[threat['card']]
            self.assertFalse(set(threat['hole'])&set(snapshot['hole']+b))
            self.assertGreater(score(threat['hole']+b),score(snapshot['hole']+b))

    def test_illegal_cards_and_samples(self):
        v=public_snapshot(self.fixture())
        with self.assertRaises(ValueError): analyze(v,0)
        v['hole']=['Ts','3d']
        with self.assertRaises(ValueError): analyze(v,100)

    def test_cli_readonly_repeatable_and_detail(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        from holdem.__main__ import start_hand
        with tempfile.TemporaryDirectory() as directory:
            s=dict(hand=0,button=5,players=[dict(name=str(i),stack=1000) for i in range(6)])
            start_hand(s)
            p=Path(directory)/'state.json'; p.write_text(json.dumps(s))
            before=p.read_bytes()
            command=[sys.executable,'-m','holdem','--state',str(p),'table','--assist-detail','--samples','100']
            first=subprocess.run(command,check=True,capture_output=True,text=True).stdout
            second=subprocess.run(command,check=True,capture_output=True,text=True).stdout
            self.assertEqual(first,second)
            self.assertEqual(p.read_bytes(),before)
            self.assertIn('【对手公开证据】',first)
            self.assertNotIn('【范围规则】',first)
            plain=subprocess.run(command[:-3],check=True,capture_output=True,text=True).stdout
            self.assertNotIn('辅助分析',plain)

    def test_weighted_river_equity_against_enumeration(self):
        from holdem.__main__ import score
        v=self.fixture(); v['board']=['6c','3h','Td','Kh','2s']; v['players'][0]['hole']=['Ks','7d']
        v['history_complete']=True
        v['events']=[dict(kind='action',seat=1,action='raise',paid=30,bet=30)]
        snapshot=public_snapshot(v)
        tables,_=range_tables(snapshot,snapshot['board'],snapshot['events'],[0,1])
        my_score=score(snapshot['hole']+snapshot['board'])
        expected=total=0.
        for h,w in tables[1].items():
            their_score=score(list(h)+snapshot['board'])
            expected+=w*(1 if my_score>their_score else .5 if my_score==their_score else 0)
            total+=w
        result=analyze(snapshot,10000,48)
        self.assertAlmostEqual(result['equity'],expected/total,delta=.03)
        self.assertAlmostEqual(result['win']+result['tie']+result['loss'],1)
