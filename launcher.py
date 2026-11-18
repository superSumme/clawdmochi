# -*- coding: utf-8 -*-
"""共感娃娃 · 一键启动 + 自检（年糕）

双击 start.bat 或运行 python launcher.py：
  ① 自检并打印：电脑IP / 固件期望IP / touch-server / 板子是否在热点 / 数据是否到达
  ② 电脑IP 变了会自动帮你改固件里的地址（并提示重新烧录）
  ③ 自动拉起 touch-server（挂了自动重启）
  ④ 打开「年糕的脸」对话网页（被摸会自动发话）
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "chat"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WEB_PORT = 9334
SRV_PORT = 9333
CAT_NAME = "年糕"

# 常见 Espressif(ESP32) 网卡 MAC 前缀
ESPRESSIF_OUI = {
    "8c:bf:ea", "24:0a:c4", "24:6f:28", "30:ae:a4", "3c:61:05", "3c:71:bf",
    "40:f5:20", "48:27:e2", "4c:11:ae", "54:5a:a6", "5c:cf:7f", "60:01:94",
    "68:c6:3a", "78:21:84", "7c:9e:bd", "80:64:6f", "84:0d:8e", "84:cc:a8",
    "8c:4f:00", "8c:aa:b5", "90:38:0c", "94:b5:55", "94:b9:7e", "a0:20:a6",
    "a4:7b:9d", "a4:cf:12", "ac:67:b2", "b4:e6:2d", "b8:d6:1a", "bc:dd:c2",
    "c4:4f:33", "c4:5b:be", "c8:2b:96", "cc:50:e3", "d4:8a:fc", "d8:a0:1d",
    "d8:f1:5b", "dc:4f:22", "e0:98:06", "e8:31:cd", "e8:68:e7", "ec:62:60",
    "ec:94:cb", "ec:fa:bc", "f0:08:d1", "f4:cf:a2", "f8:1d:78", "fc:f5:c4",
}


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


load_env()
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com")

from feel import DEFAULT_DATA, digest, load_moments  # noqa: E402
from touch_server.posmap import BODY_PART  # noqa: E402  # ⭐ 感知部位（改 posmap.py 那一行即可）


# ============ 自检工具 ============
def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def firmware_files():
    return [p for p in [
        ROOT / "firmware" / "touch_doll" / "touch_doll.ino",
        ROOT / "firmware" / "touch_doll.ino",
    ] if p.exists()]


def firmware_ip():
    for p in firmware_files():
        txt = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'HOME\s*=\s*"http://([\d.]+):', txt)
        if m:
            return m.group(1), p
    return None, None


def sync_firmware_ip(new_ip):
    """固件里的地址与电脑实际 IP 不一致时，自动改写。返回 True 表示改了。"""
    old, path = firmware_ip()
    if not path or old == new_ip:
        return False
    txt = path.read_text(encoding="utf-8", errors="replace")
    txt = re.sub(r'(HOME\s*=\s*"http://)[\d.]+(:9333/hello")', r"\g<1>" + new_ip + r"\g<2>", txt)
    path.write_text(txt, encoding="utf-8")
    return True


def arp_table():
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, timeout=15)
        raw = out.stdout.decode("gbk", "replace")
    except Exception:
        return []
    rows = []
    for line in raw.splitlines():
        m = re.match(r"\s*([\d.]+)\s+([0-9a-fA-F-]{17})\s+(\S+)", line)
        if m and m.group(2).lower() != "ff-ff-ff-ff-ff-ff":
            rows.append((m.group(1), m.group(2).lower().replace("-", ":")))
    return rows


def ping(i, prefix, alive):
    try:
        subprocess.run(["ping", "-n", "1", "-w", "250", f"{prefix}{i}"],
                       capture_output=True, timeout=3)
        alive.append(i)
    except Exception:
        pass


def scan_for_board(ip):
    """并发 ping 扫本网段，再从 ARP 里找 Espressif 设备。返回 (ip, mac) 或 None。"""
    if not ip:
        return None
    prefix = ip.rsplit(".", 1)[0] + "."
    alive = []
    ths = [threading.Thread(target=ping, args=(i, prefix, alive)) for i in range(1, 255)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    for a, mac in arp_table():
        if mac[:8] in ESPRESSIF_OUI:
            return a, mac
    return None


def server_alive():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{SRV_PORT}/", timeout=3):
            return True
    except Exception:
        return False


def port_pid(port):
    """找监听某端口的进程 PID（用来重启旧服务）。"""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, timeout=15)
        raw = out.stdout.decode("gbk", "replace")
    except Exception:
        return None
    for line in raw.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                return int(parts[-1])
    return None


def kill_port(port):
    pid = port_pid(port)
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        return True
    return False


_server_proc = None


def spawn_server():
    global _server_proc
    try:
        _server_proc = subprocess.Popen(
            [sys.executable, "-m", "touch_server.server"], cwd=str(ROOT),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        print("  touch-server 启动失败:", e)


def supervise_server():
    """touch-server 挂了自动重启。"""
    while True:
        time.sleep(5)
        if not server_alive():
            print("  ⚠ 发现 touch-server 掉线，自动重启…", flush=True)
            spawn_server()
            time.sleep(1.5)
            print("  ✅ touch-server 已重新拉起" if server_alive() else "  ❌ 重启失败", flush=True)


def data_fresh(secs=12):
    ms = load_moments(DEFAULT_DATA)
    if not ms:
        return False, None
    try:
        h, m, s = ms[-1]["ts"].split(":")
        last = int(h) * 3600 + int(m) * 60 + int(s)
    except Exception:
        return False, ms[-1].get("ts")
    now = time.localtime()
    nows = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
    return ((nows - last) % 86400) <= secs, ms[-1].get("ts")


def report():
    ip = local_ip()
    fw_ip, fw_path = firmware_ip()
    print("=" * 56)
    print(f"  🧸 共感娃娃 · {CAT_NAME}  自检报告   {time.strftime('%H:%M:%S')}")
    print("=" * 56)

    print(f"[0/5] 感知部位     : {BODY_PART}    （想改：编辑 touch_server/posmap.py 里的 BODY_PART）")
    print(f"[1/5] 电脑局域网 IP : {ip}")
    if fw_ip:
        if fw_ip == ip:
            print(f"      固件里写的 IP : {fw_ip}   ✅ 一致")
        else:
            print(f"      固件里写的 IP : {fw_ip}   ❌ 不一致（电脑 IP 变了）")
            if sync_firmware_ip(ip):
                print(f"      → 已自动把固件改成 {ip}，【请重新烧录一次板子】（上传箭头）")
    else:
        print("      固件文件未找到（跳过 IP 比对）")

    print("[2/5] touch-server : ", end="", flush=True)
    if kill_port(SRV_PORT):
        print("重启中（保证加载最新部位配置）…", flush=True)
        time.sleep(1.0)
    else:
        print("启动中…", flush=True)
    spawn_server()
    for _ in range(12):
        if server_alive():
            break
        time.sleep(0.5)
    print("      " + (f"✅ 已就绪（感知部位：{BODY_PART}）" if server_alive() else "❌ 启动失败"))

    board = scan_for_board(ip)
    print("[3/5] 板子在热点里 : ", end="", flush=True)
    if board:
        print(f"✅ 找到 ESP32（IP {board[0]}，MAC {board[1]}）")
    else:
        print("⚠ 未扫到 ESP32 网卡 —— 板子可能没连上热点，或热点没开/自动关了")

    fresh, last = data_fresh(12)
    print("[4/5] 板子数据到达 : ", end="", flush=True)
    total = len(load_moments(DEFAULT_DATA))
    if fresh:
        print(f"✅ 最近 12 秒内有新触摸（最新 {last}，累计 {total} 条）")
    else:
        print(f"⏳ 最近 12 秒没有新数据（最新 {last or '无'}，累计 {total} 条）")
        print("      → 去摸一下它的脸；仍无反应按下面提示排查")

    print(f"[5/5] 对话网页     : http://127.0.0.1:{WEB_PORT}（即将打开）")

    print("-" * 56)
    if fresh:
        print("  ✅ 一切正常：摸它的脸，网页会自动出现它说的话")
    else:
        print("  排查顺序：① 手机热点是否开着且没自动关（别锁屏，充电挂着）")
        print("            ② 板子串口监视器 115200 看有没有 'WiFi 连上了' 和 'POST结果=200'")
        print("            ③ 若电脑 IP 变了 → 上面已自动改固件，需重新烧录板子")
    print("=" * 56, flush=True)


# ============ 小猫对话（网页） ============
SYSTEM = (
    "你是一只叫「{name}」的毛绒小猫玩偶，通过压力传感器拥有身体感知。"
    "你只有一个感知点：别人摸你的时候，感觉都落在你的{part}上。"
    "对话里你会收到【体感】信息块 —— 那是有人刚摸到你{part}的记录（时间、部位、动作、力度、时长）。"
    "被摸到的时候，你自己会主动发言：好好用身体去感受，并自然地说一句心里话，"
    "开头用一个方括号动作标签表达身体反应（例如「[耳朵竖了起来]」「[抖了抖]」「[眯起眼睛]」「[蹭了蹭]」），"
    "然后说感受。\n"
    "规则：\n"
    "1. 只有【体感】里出现的内容才算真的发生过；没有体感时绝不假装被摸；\n"
    "2. 被摸后的发言要像真的被摸到那样自然、有情绪（舒服/惊喜/撒娇/闹小脾气），口语、简短、可爱，"
    "重点描述{part}上酥酥痒痒的感觉；\n"
    "3. 别人主动跟你说话时，你要记得自己刚才{part}被摸的感受，自然回应；\n"
    "4. 始终是小猫的语气：叫自己「我」，把对方叫「主人」，用「喵」点缀，简体中文，不要 AI 腔。\n"
).format(name=CAT_NAME, part=BODY_PART)

MOMENT_WORDS = {"戳": "戳", "按": "按/摸", "抱住不放": "抱住不放", "抚摸": "抚摸", "捏": "捏"}
FORCE_WORD = lambda v: "很用力" if v >= 3000 else ("用力" if v >= 1500 else ("不轻不重" if v >= 800 else "轻轻"))


def cat_line(m):
    pos = m.get("pos", "某个地方")
    act = MOMENT_WORDS.get(m.get("action", "摸"), "摸")
    return f"{m.get('ts','??')} 有人{FORCE_WORD(m.get('force',0))}地{act}了你的{pos}（力度 {m.get('force')}，持续 {m.get('dur')} 秒）"


_lock = threading.Lock()
HISTORY = []
_next_id = 0
SEEN_REACT = len(load_moments(DEFAULT_DATA))
LAST_REACT = 0.0


def append(who, kind, text, tag=None):
    global _next_id
    with _lock:
        _next_id += 1
        HISTORY.append({"id": _next_id, "who": who, "kind": kind, "text": text, "tag": tag})
        return _next_id


def mutate(id_, **kw):
    with _lock:
        for h in HISTORY:
            if h["id"] == id_:
                h.update(kw)
                return


def ask_deepseek(messages):
    req = urllib.request.Request(
        BASE.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": MODEL, "messages": messages, "stream": False}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        b = json.loads(r.read().decode("utf-8", "replace"))
    return b["choices"][0]["message"]["content"]


def react_loop():
    global SEEN_REACT, LAST_REACT
    while True:
        try:
            moments = load_moments(DEFAULT_DATA)
            new = moments[SEEN_REACT:]
            if new:
                SEEN_REACT = len(moments)
                if time.time() - LAST_REACT >= 5:   # 温柔节流
                    LAST_REACT = time.time()
                    body = "\n".join(cat_line(m) for m in new[-5:])
                    tid = append("cat", "thinking", "")
                    try:
                        reply = ask_deepseek([
                            {"role": "system", "content": SYSTEM},
                            {"role": "user", "content": f"【体感】刚发生：\n{body}\n现在你作为小猫，自己主动说一句心里话（用[动作]标签开头，简短）。"},
                        ])
                        mutate(tid, kind="touch", text=reply)
                    except Exception as e:
                        mutate(tid, kind="reply", text=f"（喵…感应中断：{e}）")
        except Exception:
            pass
        time.sleep(1.2)


def handle_say(text):
    append("user", "user", text)
    moments = load_moments(DEFAULT_DATA)
    new = moments[SEEN_REACT:]
    context = "\n".join(cat_line(m) for m in new[-5:]) if new else "（最近没有新的触摸）"
    tid = append("cat", "thinking", "")
    try:
        reply = ask_deepseek([
            {"role": "system", "content": SYSTEM},
            {"role": "assistant", "content": "（你记得的身体：今天有人摸过你。" + context + "）"},
            {"role": "user", "content": text},
        ])
        mutate(tid, kind="reply", text=reply)
    except Exception as e:
        mutate(tid, kind="reply", text=f"（喵…说话走神了：{e}）")


PAGE = """<!doctype html><html lang=zh><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>🐱 年糕 · 共感娃娃</title>
<style>
body{background:#FBF7EE;color:#3A3A3A;font-family:"霞鹜文楷","Kaiti","楷体",serif;margin:0}
.wrap{max-width:820px;margin:0 auto;padding:16px}
.head{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.face{width:62px;height:62px;border-radius:50%;background:#F6E6C9;display:flex;align-items:center;justify-content:center;font-size:40px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.name{font-size:24px;font-weight:700}
.sub{font-size:13px;color:#8A7F6A}.sub b{color:#3E9B6E}.sub .off{color:#C0392B}
.mood{margin-left:auto;text-align:right;font-size:13px;color:#7A5C3A}
.card{background:#fff;border:1px solid #E4D9C0;border-radius:16px;padding:14px;box-shadow:0 2px 12px rgba(0,0,0,.08)}
#chat{height:360px;overflow:auto;display:flex;flex-direction:column;gap:10px;padding:6px}
.lab{font-size:11px;color:#B9A98A;margin:2px 0 0}
.msg{max-width:82%;padding:9px 12px;border-radius:14px;white-space:pre-wrap;line-height:1.55}
.cat{background:#F1EBDD;align-self:flex-start}
.me{background:#DFF0E4;align-self:flex-end}
.tag{color:#B0533A;font-weight:700}
.think{color:#B9A98A;font-style:italic}
#logbar{border-top:1px dashed #D8C9A8;margin-top:12px;padding-top:8px;font-size:13px;color:#5A5A5A;line-height:2}
#logbar .t{color:#8A7F6A;margin-bottom:2px}
#log{max-height:150px;overflow:auto}
#in{display:flex;gap:8px;margin-top:10px}
#in input{flex:1;padding:10px 12px;border:1px solid #D8CFBC;border-radius:10px;font:inherit;background:#fff}
#in button{padding:10px 18px;border:0;border-radius:10px;background:#3E9B6E;color:#fff;font:inherit;cursor:pointer}
#in button:disabled{background:#B8CDBD}
</style>
<body><div class=wrap>
<div class=head>
  <div class=face id=face>🐱</div>
  <div><div class=name>年糕</div><div class=sub id=st>检查板子…</div></div>
  <div class=mood id=mood>板子：—</div>
</div>
<div class=card>
  <div id=chat></div>
  <div id=in><input id=msg placeholder="跟年糕说点什么…（摸它也能触发对话）" autocomplete=off><button id=go onclick=send()>发送</button></div>
  <div id=logbar><div class=t>身体日志 · 实时</div><div id=log></div></div>
</div>
</div>
<script>
const el=id=>document.getElementById(id);
let last='0', busy=false, moodCat='平静';
function bubble(h){
  const box=document.createElement('div');
  if(h.who==='user'){ box.className='msg me'; box.textContent=h.text; return box; }
  const lab=document.createElement('div'); lab.className='lab';
  lab.textContent=(h.kind==='touch')?'被摸后说的':((h.kind==='thinking')?'':'回你的话');
  const m=document.createElement('div'); m.className='msg cat';
  if(h.kind==='thinking'){ m.className+=' think'; m.textContent='喵…（正感觉着你）'; }
  else {
    let t=h.text||'';
    const tag=t.match(/^\\[.*?\\]/);
    if(tag){ m.innerHTML='<span class=tag>'+tag[0]+'</span> '+t.slice(tag[0].length).trim(); }
    else m.textContent=t;
  }
  const w=document.createElement('div'); w.appendChild(lab); w.appendChild(m);
  return w;
}
async function refresh(){
  try{
    const s=await (await fetch('/state')).json();
    el('st').innerHTML='共感娃娃 · 板子'+(s.online?'<b>在线 ✓</b>':'<span class=off>未收到数据</span>');
    el('mood').textContent='板子: '+(s.online?'在线 · 心情 '+moodCat:'…');
  }catch(e){el('st').textContent='状态读取失败';}
  let r;
  try{ r=await (await fetch('/history?after='+last)).json(); }catch(e){ return; }
  if(r.items.length){
    const c=el('chat');
    r.items.forEach(b=>{ c.appendChild(bubble(b)); if(b.kind==='thinking')moodCat='正感觉着你…'; else if(b.who==='cat')moodCat='平静'; });
    last=r.last;
    c.scrollTop=c.scrollHeight;
  }
  try{
    const ms=await (await fetch('/moments')).json();
    el('log').innerHTML=ms.map(m=>'<div>'+m.ts+'　'+m.pos+(m.action==='抱住不放'?'抱':'摸')+' · 力度'+m.force+'</div>').join('')||'（还没有触摸……）';
  }catch(e){}
}
async function send(){
  const t=el('msg').value.trim(); if(!t||busy)return;
  el('msg').value=''; busy=true; el('go').disabled=true;
  await fetch('/say',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
  busy=false; el('go').disabled=false;
}
el('msg').addEventListener('keydown',e=>{if(e.key==='Enter')send();});
refresh(); setInterval(refresh,1200);
</script>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/state":
            fresh, _ = data_fresh(12)
            body = json.dumps({"online": fresh, "total": len(load_moments(DEFAULT_DATA))}).encode()
            self._res(200, "application/json", body)
        elif self.path.startswith("/history"):
            after = 0
            try:
                after = int(self.path.split("after=")[1])
            except Exception:
                pass
            with _lock:
                items = [h for h in HISTORY if h["id"] > after]
                last = HISTORY[-1]["id"] if HISTORY else after
            self._res(200, "application/json", json.dumps({"items": items, "last": last}, ensure_ascii=False).encode())
        elif self.path == "/moments":
            ms = load_moments(DEFAULT_DATA)
            ms.reverse()
            self._res(200, "application/json; charset=utf-8", json.dumps(ms[:20], ensure_ascii=False).encode())
        else:
            self._res(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))

    def do_POST(self):
        if self.path != "/say":
            self._res(404, "text/plain", b"not found")
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            text = json.loads(self.rfile.read(n) or b"{}").get("text", "")
        except Exception:
            self._res(400, "text/plain", b"bad")
            return
        if not API_KEY:
            self._res(200, "text/plain", "（缺 DEEPSEEK_API_KEY，检查 .env）".encode())
            return
        threading.Thread(target=handle_say, args=(text,), daemon=True).start()
        self._res(200, "application/json", b'{"ok":true}')

    def _res(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def heartbeat():
    n = 0
    while True:
        time.sleep(1)
        n += 1
        if n % 300 == 0:   # 每 5 分钟报一次
            fresh, last = data_fresh(12)
            print(f"[心跳 {time.strftime('%H:%M:%S')}] 板子数据: "
                  f"{'✅ 正常到达' if fresh else '⚠ 12秒内无新数据'}（最新 {last}）", flush=True)


def main():
    report()                                     # ① 自检 + 打印
    if not API_KEY:
        print("⚠ 未找到 DEEPSEEK_API_KEY（检查 .env）")
    threading.Thread(target=supervise_server, daemon=True).start()   # ③ 服务守护（挂了自动重启）
    threading.Thread(target=react_loop, daemon=True).start()          # 被摸自动发话
    threading.Thread(target=heartbeat, daemon=True).start()           # 周期状态报告
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", WEB_PORT), Handler)  # ④ 对话页
    except OSError as e:
        print(f"❌ 对话页端口 {WEB_PORT} 被占用：{e}")
        return
    print(f"\n[启动] 对话页已就绪 → http://127.0.0.1:{WEB_PORT}")
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{WEB_PORT}")).start()
    print("（这个窗口别关；每 5 分钟自动再报一次状态）\n", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
