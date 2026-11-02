"""Host bridge: wait for AI turn; submit one reasoned action without model APIs."""
import argparse,json,urllib.request
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--state',default='.holdem/web.json');p.add_argument('--port',type=int,default=8765)
    p.add_argument('operation',choices=['wait','act']);p.add_argument('--seat',type=int);p.add_argument('--version');p.add_argument('--action',choices=['fold','check','call','raise']);p.add_argument('--to',type=int)
    a=p.parse_args();token=Path(a.state).with_suffix('.host-token').read_text()
    data=None if a.operation=='wait' else json.dumps(dict(op='act',seat=a.seat,version=a.version,action=a.action,target=a.to)).encode()
    req=urllib.request.Request(f'http://127.0.0.1:{a.port}/api/host/'+('wait' if data is None else 'action'),data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as r: print(r.read().decode())
if __name__=='__main__': main()
