import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from holdem.web import Arena
from holdem.offline import decide, decision_view

class OfflineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.arena=Arena(Path(self.temp.name)/'test.json')
 def new(self,n=8):
  a=self.arena;a.change(dict(op='new',version=a.snapshot()['version'],players=n,driver='offline'))
 def test_full_game_stop_user_and_conservation(self):
  self.new()
  for _ in range(160):
   s=self.arena.state()
   if s['done']:break
   if s['turn']==0:
    before=self.arena.path.read_bytes();self.assertFalse(self.arena.offline_step());self.assertEqual(before,self.arena.path.read_bytes())
    self.arena.change(dict(op='act',version=self.arena.version(s),action='call'))
   else:self.assertTrue(self.arena.offline_step(),self.arena.offline_error)
  self.assertTrue(self.arena.state()['done'])
  self.assertEqual(sum(p['stack'] for p in self.arena.state()['players']),8000)
 def test_switch_preserves_game_and_invalidates_host(self):
  self.new();a=self.arena;s=a.state();old=a.version(s)
  a.change(dict(op='driver',driver='codex',version=old));current=a.state()
  for field in ('players','board','deck','turn','events'):self.assertEqual(s[field],current[field])
  with self.assertRaises(ValueError):a.change(dict(op='act',seat=s['turn'],action='fold',version=old),host=True)
  a.change(dict(op='driver',driver='offline',version=a.version(current)))
  with self.assertRaises(ValueError):a.change(dict(op='act',seat=s['turn'],action='fold',version=a.snapshot()['version']),host=True)
 def test_hidden_cards_do_not_affect_policy(self):
  self.new();s=self.arena.state();seat=s['turn'];v=decision_view(s,seat)
  changed=copy.deepcopy(s);changed['deck'].reverse()
  for i,p in enumerate(changed['players']):
   if i!=seat:p['hole']=['As','Ah']
  self.assertEqual(v,decision_view(changed,seat))
  self.assertEqual(decide(v,seat,42),decide(decision_view(changed,seat),seat,42))
 def test_stale_worker_cannot_commit(self):
  self.new();a=self.arena;before=a.state()
  def switch(*args):
   a.change(dict(op='driver',driver='codex',version=a.snapshot()['version']))
   return 'fold',None
  with patch('holdem.offline.decide',side_effect=switch):self.assertFalse(a.offline_step())
  self.assertEqual(before['events'],a.state()['events'])
 def test_policy_error_pauses_without_action(self):
  self.new();before=self.arena.path.read_bytes()
  with patch('holdem.offline.decide',side_effect=ValueError('invalid')):self.assertFalse(self.arena.offline_step())
  self.assertEqual(before,self.arena.path.read_bytes());self.assertIn('暂停',self.arena.offline_error)
 def test_restore_driver(self):
  self.new();other=Arena(self.arena.path)
  self.assertEqual(other.snapshot()['driver'],'offline');self.assertTrue(other.offline_step())
 def test_legal_candidates_with_short_stack_and_closed_raises(self):
  self.new();s=self.arena.state();seat=s['turn'];v=decision_view(s,seat)
  v['players'][seat]['hole']=['As','Ah'];v['players'][seat]['stack']=15
  v['legal'].update(raise_to_min=20,raise_to_max=15)
  for seed in range(100):
   action,target=decide(v,seat,seed)
   if action=='raise':self.assertEqual(target,15)
  v['legal'].update(raise_to_min=None,raise_to_max=None)
  for seed in range(100):self.assertNotEqual(decide(v,seat,seed)[0],'raise')
 def test_six_and_eight_both_styles(self):
  from holdem.__main__ import act,start_hand
  for count in (6,8):
   for mode in ('standard','gambler'):
    for run in range(8):
     s=dict(mode=mode,hand=0,button=count-1,players=[dict(name=str(i),stack=1000) for i in range(count)])
     start_hand(s)
     for step in range(180):
      if s['done']:break
      seat=s['turn']
      if seat==0:act(s,0,'call')
      else:
       action,target=decide(decision_view(s,seat),seat,f'{run}:{step}')
       act(s,seat,action,target)
     self.assertTrue(s['done']);self.assertEqual(sum(p['stack'] for p in s['players']),count*1000)
