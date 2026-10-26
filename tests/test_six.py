import random
import unittest
from holdem.__main__ import expand, start_hand, act, legal, view


class SixTests(unittest.TestCase):
    def test_expand_and_six_player_games(self):
        s=dict(hand=5,button=0,done=True,players=[dict(name=str(i),stack=n) for i,n in enumerate([980,980,890,1150])],log=[])
        expand(s)
        self.assertEqual([p['stack'] for p in s['players']],[980,980,890,1150,1000,1000])
        start_hand(s)
        self.assertEqual(s['hand'],6)
        self.assertEqual(s['button'],1)
        self.assertEqual(s['turn'],4)
        self.assertEqual(len(view(s,5)['players']),6)
        with self.assertRaises(ValueError): expand(s)
        rng=random.Random(56)
        for hand in range(40):
            count=0
            while not s['done']:
                opts=legal(s); action=rng.choice(['call','fold','raise'])
                amount=None
                if action=='raise':
                    if opts['raise_to_max'] is None: action='call'
                    else: amount=min(opts['raise_to_min'],opts['raise_to_max'])
                act(s,s['turn'],action,amount)
                count+=1
                self.assertLess(count,500)
            self.assertEqual(sum(p['stack'] for p in s['players']),6000)
            if sum(p['stack']>0 for p in s['players'])<2: break
            start_hand(s)
