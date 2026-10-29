import unittest
from copy import deepcopy
from holdem.assist import public_snapshot, analyze

class ReviewTests(unittest.TestCase):
    def test_fold_replay_ignores_future_board_and_hidden_hands(self):
        v=dict(hand=1,button=0,board=[],turn=None,done=True,history_complete=True,
               hand_start_stacks=[100,100],players=[dict(name='你',hole=['Js','Jc'],stack=100,bet=0,total=0,folded=True),dict(name='对手',hole=['As','Ac'],stack=100,bet=0,total=0,folded=False)],
               events=[dict(kind='action',seat=0,action='fold',paid=0,bet=0)],legal={})
        a=analyze(public_snapshot(v),100,42)
        w=deepcopy(v);w['board']=['2s','3s','4s','5s','6s'];w['players'][1]['hole']=['2h','3h']
        self.assertEqual(a,analyze(public_snapshot(w),100,42))
        self.assertEqual(a['net'],0)
        self.assertEqual(a['decisions'][0]['actual']['action'],'fold')
