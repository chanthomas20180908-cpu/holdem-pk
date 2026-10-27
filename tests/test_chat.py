import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from holdem.__main__ import act, settle, start_hand, view
from holdem.chat import render
from holdem.display import cards, render as plain
from holdem.terminal import cell_width


def fresh():
    s = dict(hand=0, button=5, players=[dict(name=n, stack=1000) for n in
             ['你', '岩石', '猎狐', '浪潮', '指南针', '闪电']])
    start_hand(s)
    for p, hole in zip(s['players'], [('Th', 'Ac'), ('3s', '4s'), ('5s', '6s'),
                                     ('7s', '8s'), ('9s', 'Ts'), ('Js', 'As')]):
        p['hole'] = list(hole)
    return s


class ChatTests(unittest.TestCase):
    def test_width_privacy_and_input_immutability(self):
        s = fresh()
        s['board'] = ['2d', 'Ks', 'Qh', 'Tc', '8h']
        for seat in (0, 1):
            v = view(s, seat)
            before = copy.deepcopy(v)
            for width in (40, 60, 79, 80, 100, 119, 120, 160):
                text = render(v, seat, width=width)
                self.assertNotIn('\033', text)
                for icon in ('🧑', '🪨', '🦊', '🌊', '🧭', '⚡', '🃏', '💰', '📜', '🎮', '❌', '🤝', '🔥'):
                    self.assertIn(icon, text)
                self.assertLessEqual(max(map(cell_width, text.splitlines())), width)
                for i, p in enumerate(s['players']):
                    self.assertIn(p['name'], text)
                    for c in p['hole']:
                        if i == seat:
                            self.assertIn(cards([c]), text)
                        else:
                            self.assertNotIn(cards([c]), text)
                for c in s['board']:
                    self.assertIn(cards([c]), text)
                for suit in ('黑桃', '红桃', '方块', '梅花'):
                    self.assertIn(suit, text)
            self.assertEqual(v, before)
        self.assertIn(plain(view(s, 0)), render(view(s, 0), width=30))

    def test_status_hierarchy_and_actions(self):
        s = fresh()
        actor = s['turn']
        s['players'][actor]['stack'] = 15
        act(s, actor, 'raise', 15)
        s['players'][5].update(stack=0, total=0, hole=[], folded=True)
        text = render(view(s, 0))
        for phrase in ('🔥 全押', '💤 坐出', '🟢 正在行动', '╔', '┏', '⌛ 等待'):
            self.assertIn(phrase, text)
        self.assertLess(text.index('的操作：'), text.index('本手行动'))
        act(s, s['turn'], 'fold')
        self.assertIn('❌ 已弃牌', render(view(s, 0)))

    def test_complete_settlement_and_legacy(self):
        s = fresh()
        while not s['done']:
            act(s, s['turn'], 'call' if s['current'] else 'check')
        v = view(s, 0)
        text = render(v)
        for phrase in ('翻牌前', '翻牌', '转牌', '河牌', '本手结算', '累计', '主池', '摊牌', '🏁 本手结束'):
            self.assertIn(phrase, text)
        for p in v['players']:
            for c in p['hole']:
                self.assertIn(cards([c]), text)
        v['history_complete'] = False
        self.assertIn('历史明细不完整', render(v))

    def test_fold_win_and_side_pot_accounting(self):
        s = fresh()
        act(s, s['turn'], 'raise', 100)
        while not s['done']:
            act(s, s['turn'], 'fold')
        text = render(view(s, 0))
        self.assertIn('退回', text)
        self.assertNotIn('摊牌：', text)
        for p in s['players'][1:]:
            for c in p['hole']:
                self.assertNotIn(cards([c]), text)
        s = dict(hand=1, button=3, turn=0, street='river', board=['As', 'Ks', 'Qs', 'Js', 'Ts'],
                 log=[], events=[], history_complete=True,
                 players=[dict(name=str(i), hole=list(h), total=t, stack=0, bet=0, folded=False)
                          for i, (h, t) in enumerate([(('2h', '3h'), 100), (('4h', '5h'), 200),
                                                       (('6h', '7h'), 300), (('8h', '9h'), 400)])])
        settle(s)
        text = render(view(s, 0))
        for phrase in ('主池 400', '边池 1 300', '边池 2 200', '退回3', '累计 未知'):
            self.assertIn(phrase, text)

    def test_cli_default_width_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'state.json'
            state.write_text(json.dumps(fresh()))
            before = state.read_bytes(), state.stat().st_mtime_ns
            for extra in ([], ['--color', 'always'], ['--width', '30']):
                result = subprocess.run([sys.executable, '-m', 'holdem', '--state', str(state),
                                         'table', '--style', 'chat', *extra], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('\033', result.stdout)
                if not extra:
                    self.assertEqual(cell_width(result.stdout.splitlines()[0]), 120)
            self.assertEqual((state.read_bytes(), state.stat().st_mtime_ns), before)
