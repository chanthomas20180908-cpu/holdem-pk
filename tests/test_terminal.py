import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from holdem.__main__ import act, settle, start_hand, view
from holdem.display import cards, render as plain
from holdem.terminal import ANSI, cell_width, render, use_color


class TerminalTests(unittest.TestCase):
    def fresh(self, count=6):
        s = dict(hand=0, button=count - 1, players=[dict(name=n, stack=1000) for n in
                 ['你', '岩石', '猎狐', '浪潮', '指南针', '闪电'][:count]])
        start_hand(s)
        return s

    def test_layouts_visibility_and_no_mutation(self):
        for count in (4, 6):
            s = self.fresh(count)
            for p, hole in zip(s['players'], [('Th', 'Ac'), ('3s', '4s'), ('5s', '6s'),
                                             ('7s', '8s'), ('9s', 'Ts'), ('Js', 'As')]):
                p['hole'] = list(hole)
            s['board'] = ['2d', 'Ks', 'Qh', 'Tc', '8h']
            for seat in (0, 1):
                v = view(s, seat)
                before = copy.deepcopy(v)
                for width in (40, 60, 79, 80, 100, 119, 120, 160):
                    for color in (False, True):
                        text = render(v, seat, width=width, color=color)
                        clean = ANSI.sub('', text)
                        self.assertLessEqual(max(map(cell_width, text.splitlines())), width)
                        for i, p in enumerate(s['players']):
                            self.assertIn(p['name'], clean)
                            if i != seat:
                                self.assertNotIn(cards(p['hole']), clean)
                        for card in v['board'] + v['players'][seat]['hole']:
                            self.assertIn(cards([card]), clean)
                        self.assertEqual('\033[' in text, color)
                self.assertEqual(v, before)

    def test_complete_history_settlement_and_legacy(self):
        s = self.fresh()
        while not s['done']:
            act(s, s['turn'], 'call' if s['current'] else 'check')
        v = view(s, 0)
        text = render(v, width=120)
        for phrase in ('翻牌前', '翻牌', '转牌', '河牌', '本手结算', '主池', '累计', '摊牌', '等待确认下一手'):
            self.assertIn(phrase, text)
        for p in v['players']:
            for c in p['hole']:
                self.assertIn(cards([c]), text)
        v['history_complete'] = False
        self.assertIn('历史明细不完整', render(v))
        self.assertIn(plain(v), render(v, width=30))

    def test_fold_win_hides_cards_and_keeps_refund(self):
        s = self.fresh()
        actor = s['turn']
        act(s, actor, 'raise', 100)
        while not s['done']:
            act(s, s['turn'], 'fold')
        v = view(s, 0)
        text = render(v)
        self.assertIn('退回', text)
        self.assertIn('主池', text)
        self.assertNotIn('摊牌：', text)
        for i, p in enumerate(s['players']):
            if i != 0:
                for c in p['hole']:
                    self.assertNotIn(cards([c]), text)

    def test_color_policy(self):
        stream = io.StringIO()
        with patch.dict(os.environ, {'TERM': 'xterm'}, clear=True):
            self.assertFalse(use_color('auto', stream))
            with patch.object(stream, 'isatty', return_value=True):
                self.assertTrue(use_color('auto', stream))
                with patch.dict(os.environ, {'NO_COLOR': ''}):
                    self.assertFalse(use_color('auto', stream))
                    self.assertTrue(use_color('always', stream))
                with patch.dict(os.environ, {'TERM': 'dumb'}):
                    self.assertFalse(use_color('auto', stream))
            self.assertFalse(use_color('never', stream))

    def test_side_pots_short_all_in_and_sitting_out(self):
        s = self.fresh()
        actor = s['turn']
        s['players'][actor]['stack'] = 15
        act(s, actor, 'raise', 15)
        text = render(view(s, 0), width=120)
        self.assertIn('[全押]', text)
        self.assertIn('加注到 25', text)
        s['players'][5].update(stack=0, total=0, hole=[], folded=True)
        self.assertIn('坐出', render(view(s, 0)))

        s = dict(hand=1, button=3, turn=0, street='river', board=['As', 'Ks', 'Qs', 'Js', 'Ts'],
                 log=[], events=[], history_complete=True,
                 players=[dict(name=str(i), hole=list(h), total=t, stack=0, bet=0, folded=False)
                          for i, (h, t) in enumerate([(('2h', '3h'), 100), (('4h', '5h'), 200),
                                                       (('6h', '7h'), 300), (('8h', '9h'), 400)])])
        settle(s)
        text = render(view(s, 0), width=120)
        for phrase in ('主池 400', '边池 1 300', '边池 2 200', '退回3', '累计 未知'):
            self.assertIn(phrase, text)

    def test_cli_compatibility_and_read_only(self):
        s = self.fresh()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'state.json'
            state.write_text(json.dumps(s))
            before = state.read_bytes(), state.stat().st_mtime_ns

            def run(*args):
                return subprocess.run([sys.executable, '-m', 'holdem', '--state', str(state), *args],
                                      capture_output=True, text=True)

            self.assertEqual(run('table').stdout, plain(view(s, 0)) + '\n')
            self.assertEqual(json.loads(run('view').stdout), json.loads(json.dumps(view(s, 0))))
            for color in ('auto', 'never', 'always'):
                result = run('table', '--style', 'rich', '--width', '120', '--color', color)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('六人牌室', result.stdout)
                self.assertEqual('\033[' in result.stdout, color == 'always')
            self.assertEqual(run('table', '--width', '39').returncode, 2)
            self.assertEqual((state.read_bytes(), state.stat().st_mtime_ns), before)


if __name__ == '__main__':
    unittest.main()
