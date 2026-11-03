"""Local arena service. Browser sees seat zero; host uses a separate capability."""
import argparse, json, secrets, threading, time, hashlib, shlex
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from .__main__ import view, act, start_hand
from .coach import panel
from .display import render

class Arena:
    def __init__(self, path, port=8765):
        self.path = Path(path).resolve()
        self.port = port
        self.lock = threading.RLock()
        self.host_seen = None
        self.offline_error = None
        self.token = secrets.token_urlsafe(32)
    def host_status(self):
        if self.host_seen is None:
            return 'not_connected'
        return 'connected' if time.monotonic() - self.host_seen < 65 else 'disconnected'

    def connection(self):
        root = Path(__file__).resolve().parents[1]
        command = shlex.join(['python3', '-m', 'holdem.host', '--state', str(self.path),
                              '--port', str(self.port), 'wait'])
        prompt = (f'请接管本地德扑牌桌 http://127.0.0.1:{self.port}。'
                  f'工作目录：{root}；存档：{self.path}。'
                  '请先读取该工作目录的 AGENTS.md，再使用 holdem.host 桥接主持。'
                  '不要打开或刷新网页，不要新建牌局，不要直接读取或写入存档。'
                  '按当前行动席位视角决策，通过桥接执行对手动作；用户在网页自行行动。'
                  '轮到用户时持续 wait，本手结束后停止并等待用户决定下一手。'
                  f'首次连接命令：\ncd {shlex.quote(str(root))} && {command}')
        return dict(status=self.host_status(), port=self.port, handoff_prompt=prompt)

    def state(self):
        return json.loads(self.path.read_text()) if self.path.exists() else None
    def version(self, s):
        return hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()
    def snapshot(self, seat=0):
        s=self.state()
        table=view(s,seat) if s else None
        if table is not None: table.setdefault('events', [])
        return dict(version=self.version(s), table=table,
                    host_connected=self.host_status()=='connected',
                    connection=self.connection(),
                    driver=s.get('driver','codex') if s else 'offline',
                    epoch=s.get('epoch',0) if s else 0,
                    characters=s.get('characters',list(range(8))) if s else list(range(8)),
                    offline_error=self.offline_error,
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
            if host and s and s.get('driver','codex') != 'codex': raise ValueError('当前为离线模式，主持请求已停用')
            if op=='new':
                if s: raise ValueError('已有牌局，不能覆盖')
                n=data.get('players',6); mode=data.get('mode','standard')
                if n not in (6,8) or mode not in ('standard','gambler'): raise ValueError('牌桌配置无效')
                names=['你','岩石','猎狐','浪潮','指南针','闪电','山猫','远帆'][:n]
                driver=data.get('driver','codex')
                if driver not in ('codex','offline'): raise ValueError('执行方式无效')
                s=dict(driver=driver,epoch=0,bot_seed=secrets.randbits(64),mode=mode,hand=0,button=n-1,players=[dict(name=x,stack=1000) for x in names]); start_hand(s)
            elif not s: raise ValueError('请先创建牌局')
            elif op=='driver':
                if host: raise ValueError('执行方式由用户切换')
                driver=data.get('driver')
                if driver not in ('codex','offline'): raise ValueError('执行方式无效')
                s['driver']=driver; s['epoch']=s.get('epoch',0)+1
                self.host_seen=None; self.offline_error=None
            elif op=='characters':
                choices=data.get('characters')
                if host or not isinstance(choices,list) or len(choices)!=len(s['players']) or any(type(x) is not int or not 0<=x<12 for x in choices): raise ValueError('人物选择无效')
                s['characters']=choices
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
            if host: self.host_seen=time.monotonic()
            return self.snapshot()

    def offline_step(self):
        from .offline import decide, decision_view
        with self.lock:
            s = self.state()
            if not s or s.get('driver','codex') != 'offline' or s['done'] or s['turn'] == 0 or self.offline_error:
                return False
            version = self.version(s)
            seat = s['turn']
            v = decision_view(s, seat)
            seed = f"{s.get('bot_seed',0)}:{s['hand']}:{len(s.get('events', []))}:{seat}"
        try:
            action, target = decide(v, seat, seed)
            with self.lock:
                current = self.state()
                if self.version(current) != version: return False
                act(current,seat,action,target)
                tmp=self.path.with_suffix('.tmp')
                tmp.write_text(json.dumps(current,ensure_ascii=False)); tmp.replace(self.path)
            return True
        except Exception as error:
            with self.lock:
                if self.version(self.state()) == version:
                    self.offline_error=f'本地对手已暂停：{error}'
            return False

    def run_offline(self, stop):
        while not stop.wait(.8):
            self.offline_step()

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
                        s=arena.state()
                        if s and s.get('driver','codex')=='offline': return self.send(409,{'error':'当前为离线模式，主持请求已停用'})
                        arena.host_seen=time.monotonic()
                        if s and (s['done'] or s['turn']!=0): return self.send(200,arena.snapshot(s['turn'] if not s['done'] else 0))
                    time.sleep(1)
                with arena.lock: self.send(200,arena.snapshot())
            elif self.path=='/api/events':
                self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Cache-Control','no-cache'); self.end_headers()
                try:
                    while True:
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
    arena=Arena(a.state, a.port); root=(Path(__file__).resolve().parents[1]/'frontend/dist').resolve()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),handler(arena,root))
    token=arena.path.with_suffix('.host-token'); token.parent.mkdir(parents=True,exist_ok=True); token.write_text(arena.token); token.chmod(0o600)
    print(f'Arena: http://127.0.0.1:{a.port} | Host capability: {token}',flush=True)
    print('网页服务就绪。离线模式由本地对手行动；Codex 模式请在网页点击「连接主持」。',flush=True)
    stop=threading.Event()
    worker=threading.Thread(target=arena.run_offline,args=(stop,),daemon=True); worker.start()
    try: server.serve_forever()
    finally:
        stop.set(); worker.join(timeout=2); server.server_close()
if __name__=='__main__': main()
