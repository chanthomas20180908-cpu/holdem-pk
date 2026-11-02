import unittest,tempfile
from pathlib import Path
from holdem.web import Arena
class WebTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.a=Arena(Path(self.temp.name)/'s.json')
 def new(self):return self.a.change(dict(op='new',version=self.a.snapshot()['version'],players=6))
 def test_private_and_stale(self):
  x=self.new();self.assertNotIn('deck',x['table']);self.assertTrue(all('hole' not in p for p in x['table']['players'][1:]));self.assertNotIn('decision_profile',x['table'])
  with self.assertRaises(ValueError):self.a.change(dict(op='act',version='stale',action='fold'))
 def test_browser_cannot_act_for_opponent(self):
  x=self.new()
  if x['table']['turn']!=0:
   with self.assertRaises(ValueError):self.a.change(dict(op='act',seat=x['table']['turn'],version=x['version'],action='fold'))
 def test_complete_hand_and_no_overwrite(self):
  x=self.new()
  with self.assertRaises(ValueError):self.a.change(dict(op='new',version=x['version']))
  for _ in range(10):
   t=x['table']
   if t['done']:break
   i=t['turn'];x=self.a.change(dict(op='act',seat=i,version=x['version'],action='fold'),host=i!=0)
  self.assertTrue(x['table']['done']);self.assertEqual(sum(p['stack'] for p in x['table']['players']),6000)
  old=x['version'];x=self.a.change(dict(op='next',version=old));self.assertEqual(x['table']['hand'],2)
  with self.assertRaises(ValueError):self.a.change(dict(op='next',version=old))
