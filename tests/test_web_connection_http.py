"""Temporary local API test only: no browser and no real game save."""
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from holdem.web import Arena, handler

class HttpConnectionTests(unittest.TestCase):
    def test_auth_connect_and_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            arena = Arena(Path(folder)/'test.json')
            arena.change(dict(op='new', version=arena.snapshot()['version']))
            original = arena.path.read_bytes()
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(arena, Path(folder)))
            arena.port = server.server_port
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with urllib.request.urlopen(base+'/api/table') as response:
                    snap = json.load(response)
                self.assertEqual(snap['connection']['status'], 'not_connected')
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base+'/api/host/wait')
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                self.assertIsNone(arena.host_seen)
                req = urllib.request.Request(base+'/api/host/wait', headers={'Authorization':'Bearer '+arena.token})
                with urllib.request.urlopen(req, timeout=5) as response:
                    host = json.load(response)
                seat = host['table']['turn']
                self.assertNotEqual(seat, 0)
                self.assertIn('hole', host['table']['players'][seat])
                with urllib.request.urlopen(base+'/api/table') as response:
                    snap = json.load(response)
                self.assertEqual(snap['connection']['status'], 'connected')
                self.assertNotIn('hole', snap['table']['players'][seat])
                self.assertNotIn(arena.token, json.dumps(snap))
                arena.host_seen -= 66
                self.assertEqual(arena.snapshot()['connection']['status'], 'disconnected')
                with urllib.request.urlopen(req, timeout=5) as response:
                    self.assertTrue(json.load(response)['host_connected'])
                self.assertEqual(original, arena.path.read_bytes())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
