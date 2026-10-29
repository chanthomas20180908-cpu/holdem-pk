import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from holdem.coach import context, run, panel
from holdem.__main__ import start_hand

class CoachTests(unittest.TestCase):
    def test_public_context_and_record(self):
        from holdem.__main__ import view
        s=dict(mode='standard',hand=0,button=1,players=[dict(name='你',stack=1000),dict(name='对手',stack=1000)])
        start_hand(s); seat=s['turn']
        x=context(view(s,seat),seat)
        self.assertNotIn('deck',x)
        self.assertNotIn('hole',x['players'][1-seat])
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'state.json';state.write_text('unchanged')
            source=Path(d)/'report.json'
            source.write_text(json.dumps(dict(snapshot_id=x['snapshot_id'],action='fold',recommendation='弃牌',reason='公开行动显示需要投入',plan='本手不再争夺')))
            args=SimpleNamespace(seat=seat,operation='record',input=str(source))
            self.assertIn('教练建议',run(s,state,args))
            self.assertIn('公开行动',panel(view(s,seat),state,seat))
            self.assertEqual(state.read_text(),'unchanged')
            s['players'][seat]['stack']-=1
            with self.assertRaises(ValueError):run(s,state,args)
