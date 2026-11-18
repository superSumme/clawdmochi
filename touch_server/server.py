"""server.py · touch-server 入口（demo 版）。

ThreadingHTTPServer（⚠️ 勿用单线程：一个断开的连接会卡死全场）。
  POST /hello   收一拍读数 {"bd":123,...} → 体检 → 聚合 → 写 jsonl
  GET /         状态页（浏览器开 http://localhost:9333/ 看各通道上岗情况）

跑起来（在仓库根目录）：
  python -m touch_server.server
"""
import json
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, posmap
from .classifier import TouchTracker
from .healthcheck import ChannelGate

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / config.DATA_FILE

# 每个 KEYS 一个闸门 + 一个聚合器（demo 只接 bd，其余通道无读数自然不上岗）
gates = {k: ChannelGate() for k in posmap.POS_MAP}
trackers = {k: TouchTracker(k) for k in posmap.POS_MAP}
total_events = 0


def handle_beats(payload):
    """处理一拍读数，返回本拍新结束的触摸事件列表。"""
    events = []
    for key, value in payload.items():
        key = str(key)
        if key not in gates:
            continue
        try:
            value = int(value)
        except (TypeError, ValueError):
            continue
        if not gates[key].feed(value):
            continue
        ev = trackers[key].feed(value, time.monotonic())
        if ev is not None:
            events.append(ev)
    return events


def append_event(ev):
    global total_events
    total_events += 1
    rec = {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "key": ev.key,
        "pos": posmap.POS_MAP.get(ev.key, ev.key),
        "action": ev.action,
        "force": ev.force,
        "dur": round(ev.dur, 2),
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f'{rec["ts"]}  {rec["pos"]} · {rec["action"]} · 力度{rec["force"]} · {rec["dur"]}秒', flush=True)
    return rec


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != config.ENDPOINT:
            self.send_response(404)
            self.end_headers()
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
        events = handle_beats(payload)
        for ev in events:
            append_event(ev)
        body = json.dumps({
            "ok": True,
            "armed": sum(1 for g in gates.values() if g.armed),
            "new_events": len(events),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        lines = [f"touch-server · 已记录 {total_events} 次触摸", ""]
        for k, g in gates.items():
            status = "已上岗" if g.armed else "候岗中(需连续20拍安静)"
            lines.append(f"  {k} ({posmap.POS_MAP.get(k, k)}): {status}")
        body = ("\n".join(lines)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # 请求日志太吵；事件日志已由 append_event 打印


def serve(host=None, port=None):
    host = host or config.HOST
    port = port or config.PORT
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"touch-server 已启动 http://{host}:{port}   记录文件: {DATA_PATH}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="共感娃娃 touch-server")
    ap.add_argument("--host", default=config.HOST)
    ap.add_argument("--port", type=int, default=config.PORT)
    ap.add_argument("--data", default=None, help="jsonl 输出路径（默认 data/touch_moments.jsonl）")
    args = ap.parse_args()
    if args.data:
        DATA_PATH = Path(args.data)
    serve(args.host, args.port)
