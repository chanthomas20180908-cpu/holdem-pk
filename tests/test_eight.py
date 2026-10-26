import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class EightPlayerCliTests(unittest.TestCase):
    def test_independent_tables_and_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            def run(path, *args, ok=True):
                result = subprocess.run(
                    [sys.executable, '-m', 'holdem', '--state', str(path), *args],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, ok, result.stderr)
                return json.loads(result.stdout) if ok else None

            six = Path(directory) / 'six.json'
            eight = Path(directory) / 'eight.json'
            six_view = run(six, 'new')
            original = run(eight, 'new', '--players', '8')
            self.assertEqual(len(original['players']), 8)
            self.assertEqual(sum(p['stack'] + p['total'] for p in original['players']), 8000)
            # Both extra seats must be readable and able to act through the CLI.
            for seat in (3, 4, 5, 6, 7):
                visible = run(eight, 'view', '--seat', str(seat))
                self.assertIn('hole', visible['players'][seat])
                run(eight, 'act', '--seat', str(seat), 'fold')
            before = run(eight, 'view')
            names = [f'对手{i}' for i in range(1, 8)]
            after = run(eight, 'rename', *names)
            self.assertEqual([p['name'] for p in after['players'][1:]], names)
            for player, previous in zip(after['players'], before['players']):
                player.pop('name')
                previous.pop('name')
            self.assertEqual(after, before)
            unchanged = run(eight, 'view')
            run(eight, 'rename', *(['重复'] * 7), ok=False)
            run(eight, 'rename', '少一个名字', ok=False)
            self.assertEqual(run(eight, 'view'), unchanged)
            self.assertEqual(run(six, 'view'), six_view)
