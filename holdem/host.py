"""One bridge request for the current Agent; never an autonomous poker bot."""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='供当前 Agent 调用的主持桥接；不会启动 AI 或模型 API')
    parser.add_argument('--state', default='.holdem/web.json')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('operation', choices=['wait', 'act'])
    parser.add_argument('--seat', type=int)
    parser.add_argument('--version')
    parser.add_argument('--action', choices=['fold', 'check', 'call', 'raise'])
    parser.add_argument('--to', type=int)
    args = parser.parse_args()
    if args.operation == 'act':
        if args.seat is None or args.seat == 0 or not args.version or not args.action:
            parser.error('act 需要对手 --seat、当前 --version 和 --action；不能代替用户行动')
        if args.action == 'raise' and args.to is None:
            parser.error('加注需要 --to 总额')
    try:
        token = Path(args.state).resolve().with_suffix('.host-token').read_text()
        data = None if args.operation == 'wait' else json.dumps(dict(
            op='act', seat=args.seat, version=args.version, action=args.action, target=args.to)).encode()
        operation = 'wait' if data is None else 'action'
        req = urllib.request.Request(f'http://127.0.0.1:{args.port}/api/host/{operation}', data=data,
                                     headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as response:
            print(response.read().decode())
    except FileNotFoundError:
        parser.exit(2, '主持凭据不存在：请先启动网页服务，并使用网页「连接主持」中的实际路径和端口。\n')
    except urllib.error.HTTPError as error:
        if error.code == 403:
            message = '主持凭据不匹配：请核对牌桌路径与端口，服务重启后重新执行接管命令。'
        else:
            try:
                message = json.loads(error.read()).get('error', '服务拒绝操作')
            except (ValueError, AttributeError):
                message = f'服务拒绝操作（HTTP {error.code}）'
        parser.exit(2, message + '\n')
    except (urllib.error.URLError, TimeoutError, OSError):
        parser.exit(2, f'无法连接本机 {args.port} 端口的主持服务：请检查服务是否运行。牌局不会被重建。\n')


if __name__ == '__main__':
    main()
