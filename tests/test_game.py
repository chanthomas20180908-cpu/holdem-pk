import random
import unittest
from holdem.__main__ import act, legal, score, settle, start_hand, view


class GameTests(unittest.TestCase):
    def fresh(self):
        s = dict(hand=0, button=3, players=[dict(name=str(i), stack=1000) for i in range(4)])
        start_hand(s)
        return s

    def test_rankings(self):
        self.assertGreater(score(['As','Ks','Qs','Js','Ts','2h','3d']), score(['Ah','Ad','Ac','As','Kh','2d','3d']))
        self.assertEqual(score(['As','2h','3c','4d','5s']), (4, 5))
        self.assertEqual(score(['Ah','Ad','Ac','Kh','Kd','Ks','2d']), (6, 14, 13))

    def test_view_and_invalid_action(self):
        s = self.fresh()
        self.assertNotIn('deck', view(s, 0))
        self.assertNotIn('hole', view(s, 0)['players'][1])
        with self.assertRaises(ValueError): act(s, s['turn'], 'check')
        with self.assertRaises(ValueError): act(s, s['turn'], 'raise', 11)

    def test_side_pots(self):
        s = dict(button=3, board=['2s','3h','7d','8c','9s'], players=[dict(name=str(t), hole=h, total=t, stack=0, folded=False) for h,t in [(['As','Ah'],100), (['Ks','Kh'],200), (['Qs','Qh'],300), (['Js','Jh'],300)]], log=[])
        settle(s)
        self.assertEqual(s['awards'], [400,300,200,0])

    def test_random_games_conserve_chips(self):
        rng = random.Random(17)
        for _ in range(50):
            s = self.fresh()
            for hand in range(8):
                actions = 0
                while not s['done']:
                    opts = legal(s)
                    choice = rng.choice(['call','call','fold','raise'])
                    amount = None
                    if choice == 'raise':
                        if opts['raise_to_max'] is None: choice = 'call'
                        else: amount = min(opts['raise_to_min'], opts['raise_to_max']) if rng.random() < .7 else opts['raise_to_max']
                    act(s, s['turn'], choice, amount)
                    actions += 1
                    self.assertLess(actions, 300)
                    self.assertTrue(all(p['stack'] >= 0 for p in s['players']))
                self.assertEqual(sum(p['stack'] for p in s['players']), 4000)
                if sum(p['stack'] > 0 for p in s['players']) < 2: break
                start_hand(s)


if __name__ == '__main__': unittest.main()
