import copy
import unittest
from holdem.__main__ import act, start_hand, view, settle
from holdem.display import render, cards


class DisplayTests(unittest.TestCase):
    def fresh(self):
        s = dict(hand=0, button=3, players=[dict(name=n, stack=1000) for n in ['你','岩石','猎狐','浪潮']])
        start_hand(s)
        return s

    def test_actions_and_refund(self):
        s = self.fresh()
        act(s, 3, 'raise', 30)
        act(s, 0, 'call')
        act(s, 1, 'fold')
        act(s, 2, 'fold')
        self.assertEqual(s['street'], 'flop')
        act(s, 3, 'raise', 40)
        act(s, 0, 'fold')
        self.assertEqual(s['refunds'], [0,0,0,40])
        self.assertEqual([p['amount'] for p in s['pots']], [75])
        table = render(view(s, 0))
        for phrase in ['下小盲 5','下大盲 10','加注到 30（本次投入 30）','跟注 30（本轮累计 30）','下注 40','未被跟注的 40 退回浪潮','主池','本手 -30','累计 -30']:
            self.assertIn(phrase, table)
        self.assertNotIn(cards(s['players'][3]['hole']), table)
        self.assertIn('本轮结束：底池 75', table)
        self.assertEqual([e['paid'] for e in s['events'] if e['kind']=='action'], [30,30,0,0,40,0])

    def test_checkdown_and_card_spacing(self):
        s = self.fresh()
        while not s['done']:
            act(s, s['turn'], 'call' if s['current'] else 'check')
        visible = view(s,0)
        before = copy.deepcopy(visible)
        table = render(visible)
        self.assertEqual(visible, before)
        self.assertEqual(sum(e['kind']=='round_end' for e in s['events']), 4)
        self.assertEqual(sum(e['kind']=='deal' for e in s['events']), 3)
        self.assertEqual(cards(['Ts','3h','Ad']), '10 ♠ / 3 ♥ / A ♦')
        self.assertIn('摊牌', table)
        self.assertNotIn('deck', visible)
        start_hand(s)
        self.assertNotIn('awards', view(s,0))
        self.assertEqual(len(s['events']),2)

    def test_legacy_is_explicit(self):
        s = self.fresh()
        for key in ['events','history_complete','positions','initial_stacks','hand_start_stacks']: s.pop(key)
        table = render(view(s,0))
        self.assertIn('历史明细不完整', table)
        act(s,s['turn'],'fold')
        self.assertFalse(view(s,0)['history_complete'])

    def test_side_pot_split_and_refund(self):
        s = dict(button=3, street='river', board=['As','Ks','Qs','Js','Ts'], log=[], events=[],
            players=[dict(name=str(i),hole=h,total=t,stack=0,bet=0,folded=False) for i,(h,t) in enumerate([(['2h','3h'],100),(['4h','5h'],200),(['6h','7h'],300),(['8h','9h'],400)])])
        settle(s)
        self.assertEqual(s['refunds'],[0,0,0,100])
        self.assertEqual([p['amount'] for p in s['pots']], [400,300,200])
        self.assertEqual(s['awards'],[100,200,300,400])

    def test_short_all_in_display(self):
        s=self.fresh()
        s['players'][3]['stack']=15
        act(s,3,'raise',15)
        table=render(view(s,0))
        self.assertIn('加注到 15（本次投入 15） [全押]',table)
        self.assertIn('加注到 25–1000',table)


if __name__=='__main__': unittest.main()
