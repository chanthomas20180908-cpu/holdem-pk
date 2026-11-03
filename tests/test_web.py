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
 def test_legacy_without_events(self):
  import json
  self.new();s=self.a.state();s.pop('events');self.a.path.write_text(json.dumps(s))
  before=self.a.path.read_bytes()
  self.assertEqual(self.a.snapshot()['table']['events'],[])
  self.assertEqual(self.a.path.read_bytes(),before)
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

class ConnectionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.a=Arena(Path(self.temp.name)/'table with spaces.json',8768)
 def test_status_and_resume(self):
  from unittest.mock import patch
  self.assertEqual(self.a.connection()['status'],'not_connected')
  with patch('holdem.web.time.monotonic',return_value=100):
   self.a.host_seen=99
   self.assertEqual(self.a.connection()['status'],'connected')
   self.assertTrue(self.a.snapshot()['host_connected'])
  with patch('holdem.web.time.monotonic',return_value=164):
   self.assertEqual(self.a.connection()['status'],'disconnected')
  self.a.host_seen=None
  self.assertEqual(self.a.connection()['status'],'not_connected')
 def test_handoff_exact_path_port_no_secret_no_mutation(self):
  x=self.a.snapshot();prompt=x['connection']['handoff_prompt']
  self.assertIn('--port 8768',prompt)
  self.assertIn(str(self.a.path),prompt)
  self.assertIn('不要打开或刷新网页',prompt)
  self.assertNotIn(self.a.token,prompt)
  self.assertFalse(self.a.path.exists())
  import shlex
  command=prompt.split(' && ')[-1]
  args=shlex.split(command)
  self.assertEqual(args[args.index('--state')+1],str(self.a.path))
 def test_reconnect_preserves_state(self):
  x=self.a.change(dict(op='new',version=self.a.snapshot()['version']))
  before=self.a.path.read_bytes()
  self.a.host_seen=1
  self.a.snapshot()
  resumed=Arena(self.a.path,8768)
  self.assertEqual(resumed.snapshot()['version'],x['version'])
  self.assertEqual(resumed.connection()['status'],'not_connected')
  self.assertEqual(before,self.a.path.read_bytes())

class HostCliTests(unittest.TestCase):
 def test_missing_token_has_actionable_error(self):
  from unittest.mock import patch
  from holdem.host import main
  import contextlib,io
  out=io.StringIO()
  with patch('sys.argv',['host','--state','/nonexistent/holdem/s.json','wait']),contextlib.redirect_stderr(out):
   with self.assertRaises(SystemExit) as e:main()
  self.assertEqual(e.exception.code,2)
  self.assertIn('实际路径和端口',out.getvalue())
 def test_host_cannot_request_user_action(self):
  from unittest.mock import patch
  from holdem.host import main
  import contextlib,io
  with patch('sys.argv',['host','act','--seat','0','--version','v','--action','fold']),contextlib.redirect_stderr(io.StringIO()):
   with self.assertRaises(SystemExit) as e:main()
  self.assertEqual(e.exception.code,2)

class StartupTests(unittest.TestCase):
 def test_busy_port_does_not_replace_live_token(self):
  from unittest.mock import patch
  from holdem.web import main
  with tempfile.TemporaryDirectory() as folder:
   state=Path(folder)/'s.json'; token=state.with_suffix('.host-token')
   token.write_text('existing-host-capability')
   with patch('sys.argv',['web','--state',str(state),'--port','8768']),patch('holdem.web.ThreadingHTTPServer',side_effect=OSError('port busy')):
    with self.assertRaises(OSError):main()
   self.assertEqual(token.read_text(),'existing-host-capability')
   self.assertFalse(state.exists())
