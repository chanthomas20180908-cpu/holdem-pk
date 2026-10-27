import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from holdem.__main__ import start_hand, view
from holdem.display import render


class GamblerTests(unittest.TestCase):
    def test_legacy_and_private_profiles(self):
        s = dict(hand=0, button=7, players=[dict(name=str(i), stack=1000) for i in range(8)])
        start_hand(s)
        self.assertEqual(view(s, 0)['mode'], 'standard')
        self.assertIn('模式：标准', render(view(s, 0)))
        s['mode'] = 'gambler'
        self.assertNotIn('decision_profile', view(s, 0))
        self.assertEqual(len({view(s, i)['decision_profile']['style'] for i in range(1, 8)}), 7)
        for seat in range(1, 8):
            visible = view(s, seat)
            self.assertEqual([i for i, p in enumerate(visible['players']) if 'hole' in p], [seat])
        self.assertIn('模式：老赌鬼', render(view(s, 0)))
        self.assertNotIn('decision_profile', render(view(s, 0)))

    def test_cli_persistence_and_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'game.json'
            base = [sys.executable, '-m', 'holdem', '--state', str(path)]
            def run(*args):
                return json.loads(subprocess.check_output(base + list(args), text=True))
            visible = run('new', '--players', '8', '--mode', 'gambler')
            self.assertEqual(visible['mode'], 'gambler')
            while not visible['done']:
                visible = run('act', '--seat', str(visible['turn']), 'fold')
            visible = run('next')
            self.assertEqual(visible['mode'], 'gambler')
            visible = run('rename', *[f'新名{i}' for i in range(1, 8)])
            self.assertEqual(visible['mode'], 'gambler')
            self.assertEqual(run('view', '--seat', '7')['decision_profile']['style'], '诱导')
            before = path.read_bytes()
            result = subprocess.run(base + ['new', '--mode', 'gambler'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), before)
            result = subprocess.run(base + ['new', '--mode', 'invalid'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), before)
