"""Local arena service. Browser sees seat zero; host uses a separate capability."""
import argparse, json, secrets, threading, time, hashlib
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from .__main__ import view, act, start_hand
from .coach import panel
from .display import render

class Arena:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.host_seen = 0
        self.token = secrets.token_urlsafe(32)
    def state(self):
        return json.loads(self.path.read_text()) if self.path.exists() else None
    def version(self, s):
        return hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()
    def snapshot(self, seat=0):
        s=self.state()
        return dict(version=self.version(s), table=view(s,seat) if s else None,
                    host_connected=time.time()-self.host_seen<65,
                    coach=panel(view(s,0),self.path,0) if s else '',
                    history=render(view(s,0),0) if s else '',
                    settlement=render(view(s,0),0) if s and s['done'] else '')
    def change(self, data, host=False):
        with self.lock:
            s=self.state()
            if not isinstance(data,dict): raise ValueError('请求必须为对象')
            if data.get('version')!=self.version(s): raise ValueError('牌局已更新，请重试')
            if not isinstance(data,dict): raise ValueError('请求必须为对象')
            op=data.get('op')
            if op=='new':
                if s: raise ValueError('已有牌局，不能覆盖')
                n=data.get('players',6); mode=data.get('mode','standard')
                if n not in (6,8) or mode not in ('standard','gambler'): raise ValueError('牌桌配置无效')
                names=['你','岩石','猎狐','浪潮','指南针','闪电','山猫','远帆'][:n]
                s=dict(mode=mode,hand=0,button=n-1,players=[dict(name=x,stack=1000) for x in names]); start_hand(s)
            elif not s: raise ValueError('请先创建牌局')
            elif op=='next':
                if not s['done']: raise ValueError('本手尚未结束')
                if sum(p['stack']>0 for p in s['players'])<2: raise ValueError('场次已结束')
                start_hand(s)
            elif op=='act':
                seat=data.get('seat',0) if host else 0
                if host and seat==0: raise ValueError('主持不能代替用户行动')
                if type(seat) is not int or not 0 <= seat < len(s['players']): raise ValueError('座位无效')
                if data.get('action')=='raise' and type(data.get('target')) is not int: raise ValueError('加注金额必须为整数')
                act(s,seat,data.get('action'),data.get('target'))
            else: raise ValueError('未知操作')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(s,ensure_ascii=False)); tmp.replace(self.path)
            return self.snapshot()

def handler(arena, root):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,code,data,kind='application/json'):
            raw=json.dumps(data,ensure_ascii=False).encode() if kind=='application/json' else data
            self.send_response(code); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def host(self): return secrets.compare_digest(self.headers.get('Authorization',''), 'Bearer '+arena.token)
        def do_GET(self):
            if self.path=='/api/table':
                with arena.lock: self.send(200,arena.snapshot())
            elif self.path=='/api/host/wait':
                if not self.host(): return self.send(403,{'error':'主持凭据无效'})
                for _ in range(50):
                    with arena.lock:
                        arena.host_seen=time.time(); s=arena.state()
                        if s and (s['done'] or s['turn']!=0): return self.send(200,arena.snapshot(s['turn'] if not s['done'] else 0))
                    time.sleep(1)
                self.send(200,arena.snapshot())
            elif self.path=='/api/events':
                self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Cache-Control','no-cache'); self.end_headers()
                try:
                    for _ in range(50):
                        with arena.lock: payload=json.dumps(arena.snapshot(),ensure_ascii=False)
                        self.wfile.write(('data: '+payload+'\n\n').encode()); self.wfile.flush(); time.sleep(1)
                except (BrokenPipeError,ConnectionResetError): pass
            else:
                rel=self.path.split('?')[0].lstrip('/') or 'index.html'; f=(root/rel).resolve()
                if not f.is_relative_to(root) or not f.is_file(): return self.send(404,{'error':'请先构建前端'})
                import mimetypes
                self.send(200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
        def do_POST(self):
            origin=self.headers.get('Origin')
            if origin and origin!='http://'+self.headers.get('Host',''): return self.send(403,{'error':'来源无效'})
            is_host=self.path=='/api/host/action'
            if self.path not in ('/api/action','/api/host/action'): return self.send(404,{})
            if is_host and not self.host(): return self.send(403,{'error':'主持凭据无效'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size>8192: raise ValueError('请求过大')
                data=json.loads(self.rfile.read(size)); self.send(200,arena.change(data,is_host))
            except (ValueError,TypeError,KeyError) as e: self.send(400,{'error':str(e)})
    return Handler

def main():
    p=argparse.ArgumentParser(); p.add_argument('--state',default='.holdem/web.json'); p.add_argument('--port',type=int,default=8765); a=p.parse_args()
    arena=Arena(a.state); root=(Path(__file__).resolve().parents[1]/'frontend/dist').resolve()
    token=arena.path.with_suffix('.host-token'); token.parent.mkdir(parents=True,exist_ok=True); token.write_text(arena.token); token.chmod(0o600)
    print(f'Arena: http://127.0.0.1:{a.port} | Host capability: {token}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',a.port),handler(arena,root)).serve_forever()
if __name__=='__main__': main()
