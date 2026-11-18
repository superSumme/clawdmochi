# -*- coding: utf-8 -*-
"""一键自测：分类边界 / 上岗闸门 / 聚合器 / 端到端（起真 server + HTTP 打合成数据）。

跑法：cd 仓库根目录 && PYTHONIOENCODING=utf-8 python tests/test_pipeline.py
"""
import json
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from touch_server import config  # noqa: E402
from touch_server.classifier import TouchTracker, classify  # noqa: E402
from touch_server.healthcheck import ChannelGate  # noqa: E402
from touch_server.posmap import BODY_PART  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


print("== classify 时长边界 ==")
check("0.2s → 戳", classify(0.2) == "戳")
check("0.39s → 戳", classify(0.39) == "戳")
check("0.4s → 按（边界不算戳）", classify(0.4) == "按")
check("1.2s → 按", classify(1.2) == "按")
check("2.5s → 按（边界不算抱）", classify(2.5) == "按")
check("2.51s → 抱住不放", classify(2.51) == "抱住不放")

print("== ChannelGate 上岗 ==")
g = ChannelGate(quiet_beats=20)
for _ in range(19):
    g.feed(0)
check("19 拍安静还没上岗", not g.armed)
g.feed(0)
check("第 20 拍上岗", g.armed)
g2 = ChannelGate(quiet_beats=20)
for _ in range(10):
    g2.feed(0)
g2.feed(3000)  # 上岗前被按
for _ in range(19):
    g2.feed(0)
check("上岗前触发会清零重来", not g2.armed)

print("== TouchTracker 聚合 ==")
tr = TouchTracker("bd")
t0 = 100.0
for i in range(25):  # 按下 3.0 秒（25 拍 × 0.12s），峰值 4095
    assert tr.feed(4095, t0 + i * 0.12) is None
ev = tr.feed(0, t0 + 25 * 0.12)
check("松开返回事件 key=bd", ev is not None and ev.key == "bd")
check("峰值力度=4095", ev.force == 4095)
check("dur≈3.0s", abs(ev.dur - 3.0) < 0.01)
check("3.0s → 抱住不放", ev.action == "抱住不放")
for i in range(2):  # 快速戳一下：2 拍 ≈0.24s
    assert tr.feed(1500, t0 + 100 + i * 0.12) is None
ev2 = tr.feed(0, t0 + 100 + 2 * 0.12)
check("0.24s → 戳", ev2.action == "戳")

print("== 端到端 server（HTTP） ==")
import touch_server.server as srv  # noqa: E402
with tempfile.TemporaryDirectory() as td:
    srv.DATA_PATH = Path(td) / "touch_moments.jsonl"
    srv.gates = {k: ChannelGate() for k in srv.posmap.POS_MAP}
    srv.trackers = {k: TouchTracker(k) for k in srv.posmap.POS_MAP}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post(payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/hello",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(urllib.request.urlopen(req, timeout=5).read())

    def beat(payload):  # 按固件真实节拍 120ms 一拍发
        r = post(payload)
        time.sleep(config.BEAT_SEC)
        return r

    for _ in range(24):  # 先安静 24 拍让 bd 上岗
        beat({"bd": 0})
    status = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read()
    check("GET 状态页显示 bd 已上岗", "已上岗".encode() in status)
    for _ in range(25):  # 抱住 3 秒（真实节拍）
        beat({"bd": 4095})
    beat({"bd": 0})          # 松开 → 结束 抱住不放
    beat({"bd": 1500})       # 快速戳 1 拍
    beat({"bd": 0})          # 松开 → 戳
    time.sleep(0.2)
    rows = srv.DATA_PATH.read_text(encoding="utf-8").strip().splitlines()
    parsed = [json.loads(r) for r in rows]
    print("  记录:", parsed)
    check("写出 2 条记录", len(rows) == 2)
    check("动作顺序 = [抱住不放, 戳]", [p["action"] for p in parsed] == ["抱住不放", "戳"])
    check(f"pos 都映射为 {BODY_PART}", all(p["pos"] == BODY_PART for p in parsed))
    check("第 1 条 dur≈3.0s（Windows sleep 漂移 ±0.5）", abs(parsed[0]["dur"] - 3.0) < 0.5)
    httpd.shutdown()

print()
print(f"==== 结果：{PASS} PASS / {FAIL} FAIL ====")
sys.exit(1 if FAIL else 0)
