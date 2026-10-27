"""Exercise the CLI features combined across the merged branches."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CombinedCliTests(unittest.TestCase):
    def test_table_styles_modes_and_assistant_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            for players in (6, 8):
                for mode in ('standard', 'gambler'):
                    path = Path(directory) / f'{players}-{mode}.json'
                    base = [sys.executable, '-m', 'holdem', '--state', str(path)]
                    created = subprocess.run(base + ['new', '--players', str(players), '--mode', mode],
                                             check=True, capture_output=True, text=True)
                    visible = json.loads(created.stdout)
                    original = path.read_bytes()
                    label = '老赌鬼' if mode == 'gambler' else '标准'
                    for style in ('plain', 'rich', 'chat'):
                        command = base + ['table', '--style', style, '--color', 'never', '--width', '120']
                        plain = subprocess.run(command, check=True, capture_output=True, text=True).stdout
                        with self.subTest(players=players, mode=mode, style=style):
                            self.assertIn('模式：' + label, plain)
                            for player in visible['players']:
                                self.assertIn(player['name'], plain)
                            self.assertNotIn('\x1b[', plain)
                            self.assertNotIn('decision_profile', plain)
                            for assist in ('--assist', '--assist-detail'):
                                assisted = subprocess.run(command + [assist, '--samples', '100'],
                                                          check=True, capture_output=True, text=True).stdout
                                self.assertTrue(assisted.startswith(plain))
                                self.assertGreater(len(assisted), len(plain))
                                self.assertNotIn('decision_profile', assisted)
                                self.assertEqual(path.read_bytes(), original)
                            invalid = subprocess.run(command + ['--assist', '--samples', '99'],
                                                     capture_output=True, text=True)
                            self.assertEqual(invalid.returncode, 2)
                            self.assertEqual(path.read_bytes(), original)
                    if players == 8:
                        for style in ('plain', 'rich', 'chat'):
                            result = subprocess.run(base + ['table', '--seat', '7', '--style', style,
                                                            '--assist', '--samples', '100', '--color', 'never'],
                                                    check=True, capture_output=True, text=True)
                            self.assertNotIn('decision_profile', result.stdout)
                            self.assertEqual(path.read_bytes(), original)
