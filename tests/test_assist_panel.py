import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from holdem.assist import analyze, public_snapshot, render_analysis
from holdem.terminal import cell_width


class DecisionPanelTests(unittest.TestCase):
    def fixture(self):
        return dict(hand=7, board=['6c', '3h', 'Td', 'Kh', '2s'], players=[
            dict(name='你', hole=['Ks', '7d'], stack=1000, bet=0, total=100, folded=False),
            dict(name='山猫', hole=['4h', '5d'], stack=1000, bet=0, total=100, folded=False)],
            turn=0, done=False, button=0, history_complete=False,
            legal=dict(fold=True, call=0, check=True, raise_to_min=10, raise_to_max=1000))

    def analyze(self, v=None, samples=500):
        return analyze(public_snapshot(v or self.fixture()), samples, seed=42)

    def test_amount_changes_cost_not_same_opponents_odds(self):
        a = self.analyze()
        choices = [c for c in a['comparisons'] if c['action'] != 'fold']
        baseline = choices[0]['scenarios'][0]
        self.assertEqual([c['target'] for c in choices[1:]], [100, 200, 1000])
        for choice in choices:
            s = choice['scenarios'][0]
            self.assertEqual((s['win'], s['tie'], s['loss']), (a['win'], a['tie'], a['loss']))
            self.assertAlmostEqual(s['win']+s['tie']+s['loss'], 1)
        self.assertNotEqual(baseline['ev'], choices[-1]['scenarios'][0]['ev'])
        for choice in choices[1:]:
            pickup = choice['scenarios'][1]
            self.assertTrue(pickup['direct'])
            self.assertIsNone(pickup['win'])
            self.assertEqual(pickup['ev'], 200)  # Prior pot, less no sunk costs.
            self.assertEqual(pickup['refund'], choice['paid'])

    def test_candidates_match_real_legal_actions(self):
        from holdem.__main__ import start_hand, view, act
        s = dict(hand=0, button=0, players=[dict(name=str(i), stack=1000) for i in range(6)])
        start_hand(s)
        seat = s['turn']
        visible = view(s, seat)
        a = analyze(public_snapshot(visible, seat), 100, seed=2)
        targets = [c['target'] for c in a['comparisons'] if c['action'] == 'raise']
        self.assertEqual(len(set(targets)), len(targets))
        self.assertLessEqual(len(targets), 3)
        for c in a['comparisons']:
            state = copy.deepcopy(s)
            act(state, seat, c['action'], c.get('target'))
            self.assertEqual(next(e['paid'] for e in state['events'] if e['kind'] == 'action'), c['paid'])
        after_call = sum(p['total'] for p in s['players'])+visible['legal']['call']
        self.assertEqual(targets[0], max(visible['legal']['raise_to_min'], 10+(after_call+1)//2))

    def test_no_raise_if_not_reopened_and_short_all_in_is_legal(self):
        v = self.fixture()
        v['players'][1]['bet'] = 30
        v['legal'] = dict(fold=True, call=30, check=False, raise_to_min=None, raise_to_max=None)
        a = self.analyze(v)
        self.assertEqual([c['action'] for c in a['comparisons']], ['call', 'fold'])
        v['players'][0]['stack'] = 45
        v['legal'].update(raise_to_min=60, raise_to_max=45)
        a = self.analyze(v)
        raises = [c for c in a['comparisons'] if c['action'] == 'raise']
        self.assertEqual([(c['target'], c['paid']) for c in raises], [(45, 45)])
        self.assertIn('全押', raises[0]['label'])

    def test_short_call_is_all_in_without_duplicate_raise(self):
        v = self.fixture()
        v['players'][0].update(stack=10, bet=0)
        v['players'][1].update(bet=100)
        v['legal'] = dict(fold=True, call=10, check=False, raise_to_min=None, raise_to_max=None)
        a = self.analyze(v)
        self.assertEqual(a['comparisons'][0]['label'], '全押跟注 10')
        self.assertEqual(len(a['comparisons']), 2)

    def test_side_pots_exclude_ineligible_and_refunds_from_victory(self):
        v = self.fixture()
        v['board'] = ['Ts', 'Js', 'Qs', '2c', '3c']
        v['players'][0].update(hole=['Ks', 'As'], stack=10, bet=10, total=10)
        v['players'][1].update(bet=50, total=50)
        v['players'].append(dict(name='远帆', stack=0, bet=100, total=100, folded=False))
        v['legal'] = dict(fold=True, call=10, check=False, raise_to_min=None, raise_to_max=None)
        a = self.analyze(v)
        s = a['estimates'][0]
        self.assertEqual(s['contestable'], 60)
        self.assertEqual(s['ev'], 50)
        self.assertEqual(s['win'], 1)
        self.assertEqual(s['refund'], 0)
        self.assertEqual([p['amount'] for p in s['excluded_pots']], [60])
        text = render_analysis(a, format='markdown')
        self.assertIn('无资格争夺 边池 1 60', text)
        self.assertNotIn('100.0% / 0.0% /', text)

    def test_already_all_in_opponent_cannot_fold(self):
        v = self.fixture()
        v['players'][0]['total'] = 50
        v['players'][1].update(stack=0, total=20)
        v['players'].append(dict(name='远帆', stack=1000, bet=0, total=50, folded=False))
        a = self.analyze(v)
        for c in a['comparisons']:
            if c['action'] != 'raise':
                continue
            folded = c['scenarios'][1]
            self.assertFalse(folded['direct'])
            self.assertTrue(any(1 in p['eligible'] for p in folded['pot_results']))
            self.assertTrue(any(p['direct'] for p in folded['pot_results']))
        text = render_analysis(a, format='markdown')
        self.assertIn('分池见下', text)
        self.assertIn('主池', text)
        self.assertIn('边池', text)

    def test_tie_is_not_equity_and_odd_chip_matches_settlement(self):
        v = self.fixture()
        v['board'] = ['Ts', 'Js', 'Qs', 'Ks', 'As']
        v['players'][0]['hole'] = ['2h', '3d']
        v['players'][0]['total'] = 100
        v['players'][1]['total'] = 101
        # Third chip contributor has folded, leaving an odd 203 chip pot.
        v['players'].append(dict(name='已弃牌', stack=998, bet=0, total=2, folded=True))
        a = self.analyze(v)
        self.assertEqual((a['win'], a['tie'], a['equity']), (0, 1, .5))
        self.assertEqual(a['estimates'][0]['ev'], 101)
        text = render_analysis(a, format='markdown')
        self.assertIn('独赢 0.0%', text)
        self.assertIn('平局 100.0%', text)
        self.assertNotIn('50.0%', text)

    def test_pending_responses_change_eligible_set_not_occurrence_probability(self):
        v = self.fixture()
        v['players'][1].update(bet=30, total=130)
        v['players'].append(dict(name='未回应', stack=1000, bet=0, total=100, folded=False))
        v['legal'].update(call=30, check=False, raise_to_min=60)
        a = self.analyze(v)
        self.assertIn('条件建议', a['advice'])
        self.assertEqual(len(a['comparisons'][0]['scenarios']), 2)
        folded, called = a['comparisons'][0]['scenarios']
        self.assertEqual(folded['pot_results'][0]['eligible'], [0, 1])
        self.assertEqual(called['pot_results'][0]['eligible'], [0, 1, 2])
        self.assertNotIn('probability', folded)

    def test_low_reliability_never_fills_in_zero_odds_or_profit(self):
        a = self.analyze()
        a['ess'] = 99
        text = render_analysis(a, format='markdown')
        self.assertIn('暂无法可靠判断', text)
        self.assertNotRegex(text, r'\d+\.\d+%')
        self.assertIn('直接拿池（发生率未预测）', text)

    def test_not_your_turn_all_in_and_inactive_have_no_actions(self):
        v = self.fixture()
        for turn, stack in ((1, 100), (0, 0)):
            v['turn'], v['players'][0]['stack'] = turn, stack
            a = self.analyze(v)
            self.assertEqual(a['comparisons'], [])
            self.assertIn('等待', a['advice'])
            self.assertNotIn('| 选择', render_analysis(a, format='markdown'))
        for key in ('done', 'folded'):
            v = self.fixture()
            (v if key == 'done' else v['players'][0])[key] = True
            self.assertIn('辅助分析停止', render_analysis(self.analyze(v), format='markdown'))

    def test_markdown_hierarchy_and_compact_content(self):
        a = self.analyze()
        text = render_analysis(a, format='markdown')
        positions = [text.index('### '+heading) for heading in ('辅助决策', '最终获胜机会', '选择对比', '为什么')]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('**建议：过牌**', text)
        self.assertLessEqual(len(text.splitlines()), 45)
        self.assertEqual(sum(line.startswith('- **') for line in text.splitlines()), 5)
        self.assertNotIn('```', text)
        for hidden in ('模型版本', '抽样', '计算口径', '权重', '不可达', '逐张下一公共牌', '到河牌最终牌型'):
            self.assertNotIn(hidden, text)
        a['detail'] = True
        detail = render_analysis(a, format='markdown')
        self.assertIn('对手公开证据', detail)
        self.assertIn('各选择的取舍', detail)
        self.assertNotIn('范围规则', detail)

    def test_long_names_markdown_escaping_text_width_and_card_spacing(self):
        v = self.fixture()
        v['board'].pop()
        v['players'][1]['name'] = '山猫|**[危险昵称](https://example.com)<b>'*3
        v['history_complete'] = True
        v['events'] = [dict(kind='action', seat=1, action='raise', paid=30, bet=30)]
        a = self.analyze(v)
        a['detail'] = True
        md = render_analysis(a, format='markdown')
        self.assertNotIn('[危险昵称](', md)
        self.assertIn(r'\|', md)
        self.assertIn(r'\<b\>', md)
        for width in (40, 64, 80):
            text = render_analysis(a, width=width)
            self.assertTrue(all(cell_width(line) <= width for line in text.splitlines()))
            self.assertNotRegex(text, r'(?:10|[2-9TJQKA])[♠♥♦♣]')
            self.assertNotRegex(text, r'(?:10|[2-9TJQKA])\n[♠♥♦♣]')
        self.assertRegex(md, r'(?:10|[2-9TJQKA]) [♠♥♦♣]')

    def test_conditional_payouts_and_each_pool_match_engine_enumeration(self):
        from itertools import combinations
        from unittest.mock import patch
        from holdem.__main__ import settle

        v = self.fixture()
        v['players'].append(dict(name='短码', stack=0, bet=0, total=20, folded=False))
        snapshot = public_snapshot(v)
        candidates = ['As', 'Ah', '3s', '3d', '9s', '9d']
        draws = [list(first+second) for first in combinations(candidates, 2)
                 for second in combinations([c for c in candidates if c not in first], 2)]
        with patch('holdem.assist.DECK', snapshot['hole']+snapshot['board']+candidates), \
                patch('holdem.assist.random.Random.sample', side_effect=draws*10):
            a = analyze(snapshot, 900, seed=3)
        self.assertEqual(len(a['headline']['pot_results']), 2)
        self.assertNotEqual(a['headline']['pot_results'][0]['win'], a['headline']['pot_results'][1]['win'])
        self.assertIn('主池 60：', render_analysis(a, format='markdown'))
        self.assertIn('暂不将整桌胜率变化归因到各池', render_analysis(a, format='markdown'))
        for choice in a['comparisons']:
            for estimate in choice['scenarios']:
                ev = 0
                counts = {tuple(p['eligible']): [0, 0] for p in estimate['pot_results']}
                for draw in draws:
                    state = copy.deepcopy(v)
                    state['events'] = []
                    state['log'] = []
                    state['players'][1]['hole'] = draw[:2]
                    state['players'][2]['hole'] = draw[2:]
                    state['players'][0]['total'] += choice['paid']
                    if choice['action'] == 'raise':
                        if estimate['label'].endswith('弃牌'):
                            state['players'][1]['folded'] = True
                        else:
                            state['players'][1]['total'] += min(state['players'][1]['stack'], choice['target'])
                    settle(state)
                    ev += state['awards'][0]-choice['paid']
                    for pot in state['pots']:
                        key = tuple(pot['eligible'])
                        if key not in counts or len(key) == 1:
                            continue
                        if pot['winners'] == [0]:
                            counts[key][0] += 1
                        elif 0 in pot['winners']:
                            counts[key][1] += 1
                self.assertAlmostEqual(estimate['ev'], ev/len(draws))
                for pot in estimate['pot_results']:
                    if not pot['direct']:
                        expected = counts[tuple(pot['eligible'])]
                        self.assertAlmostEqual(pot['win'], expected[0]/len(draws))
                        self.assertAlmostEqual(pot['tie'], expected[1]/len(draws))

    def test_cli_standalone_formats_seats_legacy_styles_and_readonly(self):
        from holdem.__main__ import start_hand
        with tempfile.TemporaryDirectory() as directory:
            s = dict(hand=0, button=0, players=[dict(name=str(i), stack=1000) for i in range(8)])
            start_hand(s)
            path = Path(directory)/'state.json'
            path.write_text(json.dumps(s))
            before = path.read_bytes()
            command = [sys.executable, '-m', 'holdem', '--state', str(path)]
            for seat in (0, s['turn'], 7):
                for fmt in ('text', 'markdown'):
                    args = command+['assist', '--format', fmt, '--seat', str(seat), '--samples', '100']
                    first = subprocess.run(args, capture_output=True, text=True, check=True).stdout
                    second = subprocess.run(args, capture_output=True, text=True, check=True).stdout
                    self.assertEqual(first, second)
                    self.assertEqual(path.read_bytes(), before)
                    self.assertIn('最终获胜机会', first)
                    self.assertNotIn('本手行动', first)
            default = subprocess.run(command+['assist', '--samples', '100'], capture_output=True, text=True, check=True).stdout
            self.assertTrue(default.startswith('### 辅助决策'))
            for style in ('plain', 'rich', 'chat'):
                result = subprocess.run(command+['table', '--style', style, '--assist', '--samples', '100', '--width', '40'],
                                        capture_output=True, text=True, check=True)
                panel = result.stdout.split('【辅助决策】')[1]
                self.assertTrue(all(cell_width(line) <= 40 for line in panel.splitlines()))
            detail = subprocess.run(command+['assist', '--detail', '--samples', '100'], capture_output=True, text=True, check=True)
            self.assertIn('对手公开证据', detail.stdout)
            for extra in (['--samples', '99'], ['--samples', '100001'], ['--seat', '8'], ['--width', '39']):
                result = subprocess.run(command+['assist']+extra, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(path.read_bytes(), before)
            s['done'] = True
            s['turn'] = None
            path.write_text(json.dumps(s))
            before = path.read_bytes()
            result = subprocess.run(command+['assist'], capture_output=True, text=True, check=True)
            self.assertIn('辅助分析停止', result.stdout)
            self.assertEqual(path.read_bytes(), before)
