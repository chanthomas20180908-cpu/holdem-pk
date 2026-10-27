import copy
import unittest
from holdem.assist import public_snapshot, analyze, eligible_pots


class AssistTests(unittest.TestCase):
    def fixture(self):
        return dict(board=['Ts','Js','Qs','Ks','As'], players=[
            dict(hole=['2h','3d'], stack=100, bet=10, total=10, folded=False),
            dict(hole=['4h','5d'], stack=100, bet=10, total=10, folded=False)],
            turn=0, done=False, button=0,
            legal=dict(call=0,check=True,raise_to_min=20,raise_to_max=110))

    def test_hidden_information_invariance(self):
        first=self.fixture(); second=copy.deepcopy(first)
        first['deck']=['2s']; second['deck']=['3s']
        second['players'][1]['hole']=['Ah','Ad']
        second['events']=[dict(secret='hidden')]
        a=public_snapshot(first); b=public_snapshot(second)
        self.assertEqual(a,b)
        self.assertEqual(analyze(a,100,42),analyze(b,100,42))
        self.assertNotIn('hole',a['players'][1])

    def test_board_tie(self):
        a=analyze(public_snapshot(self.fixture()),100,1)
        self.assertEqual((a['win'],a['tie'],a['equity']),(0,1,.5))
        self.assertEqual(a['call_ev'],10)

    def test_nuts_and_legal_raise(self):
        v=self.fixture(); v['board']=['Ts','Js','Qs','2c','3c']
        v['players'][0]['hole']=['Ks','As']
        a=analyze(public_snapshot(v),100,1)
        self.assertEqual(a['win'],1)
        self.assertEqual(a['categories'][8],1)
        self.assertIn('20',a['advice'])

    def test_no_advice_out_of_turn(self):
        v=self.fixture(); v['turn']=1
        a=analyze(public_snapshot(v),100,1)
        self.assertNotIn('reason',a)
        self.assertIn('等待',a['advice'])

    def test_sidepots_and_refund(self):
        self.assertEqual(list(eligible_pots([20,50,100],[0,1,2])),
                         [(60,[0,1,2],3),(60,[1,2],2),(50,[2],1)])

    def test_multiway_tie(self):
        v=self.fixture(); v['players'].append(dict(v['players'][1]))
        a=analyze(public_snapshot(v),100,1)
        self.assertAlmostEqual(a['equity'],1/3)
        self.assertAlmostEqual(a['call_ev'],10)

    def test_short_stack_side_pot_excluded(self):
        v=self.fixture()
        v['players'][0].update(stack=10,bet=10,total=10)
        v['players'][1].update(bet=50,total=50)
        v['players'].append(dict(v['players'][1]))
        v['legal']=dict(call=10,check=False,raise_to_min=None,raise_to_max=None)
        a=analyze(public_snapshot(v),100,1)
        self.assertEqual(a['contestable'],60)
        self.assertAlmostEqual(a['threshold'],1/6)
        self.assertAlmostEqual(a['call_ev'],10)
        self.assertEqual(a['advice'],'跟注 10')

    def test_inactive(self):
        v=self.fixture(); v['done']=True
        self.assertTrue(analyze(public_snapshot(v),100)['inactive'])
        v['done']=False; v['players'][0]['folded']=True
        self.assertTrue(analyze(public_snapshot(v),100)['inactive'])
