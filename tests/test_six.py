import random
import unittest
from holdem.__main__ import expand, start_hand, act, legal, view, recover_unacted_hand


class SixTests(unittest.TestCase):
    def test_recover_unacted_misaligned_hand(self):
        s = dict(hand=21, button=4, players=[dict(name=str(i), stack=1000) for i in range(6)])
        start_hand(s)
        previous = s['positions']['button']
        s['button'] = 1
        s['positions']['button'] = 4
        s['events'] = [dict(kind='settlement', street='river')]
        recover_unacted_hand(s)
        self.assertEqual((s['hand'], s['button']), (22, 5))
        self.assertEqual(s['positions']['button'], 5)
        self.assertEqual(s['events'][0]['kind'], 'blind')
        self.assertEqual(sum(p['stack'] + p['total'] for p in s['players']), 6000)
        self.assertEqual(previous, 5)
        with self.assertRaises(ValueError): recover_unacted_hand(s)

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
