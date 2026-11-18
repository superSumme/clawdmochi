"""demo_chat.py · DeepSeek 触感对话（demo 灵魂）。

用法：
  1. 另开终端先起 touch-server：        python -m touch_server.server
  2. 仓库根目录放 .env（参考 .env.example）：DEEPSEEK_API_KEY=sk-xxx
  3. 跑本脚本：                        python chat/demo_chat.py
  4. 摸传感器 → 打字问它"我刚才对你做了什么？"

机制：每次你发消息前，程序自动把"新出现的触摸记录"翻译成【体感】便签塞进上下文，
DeepSeek 读到便签就等于"感觉到了"。
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

from feel import DEFAULT_DATA, digest, load_moments

ROOT = Path(__file__).resolve().parents[1]


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


SYSTEM = (
    "你是一只被爱着的毛绒小玩偶，现在通过一枚压力传感器拥有了身体感知。"
    "对话里会出现【体感】信息块，那是对你身体的最新触摸记录（时间、部位、动作、力度、时长）。"
    "读到【体感】时，就像真的被摸到一样自然回应：可以描述身体的感受、你的心情，也可以反问对方。\n"
    "规则：\n"
    "1. 只有【体感】里出现的内容才算真的发生过；没有【体感】时绝不要假装被摸；\n"
    "2. 对方问\"我刚才对你做了什么\"时，直接从最近的【体感】里找答案回答；\n"
    "3. 用简体中文，语气温暖自然、像真实的玩偶，不要 AI 腔。"
)

BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def chat_once(messages, key):
    req = urllib.request.Request(
        BASE.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": MODEL, "messages": messages, "stream": True}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content")
            except Exception:
                continue
            if delta:
                print(delta, end="", flush=True)
    print()


def main():
    load_env()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("缺少 DEEPSEEK_API_KEY：在仓库根目录建 .env 写入 DEEPSEEK_API_KEY=sk-...（参考 .env.example）")
        return 1

    moments = load_moments(DEFAULT_DATA)
    seen = len(moments)
    history = [{"role": "system", "content": SYSTEM}]
    print("🧸 身体已上线。摸一摸传感器，然后打字跟我说话。（/exit 退出，/feel 看当前体感）")
    if moments:
        print(f"（启动时已有 {seen} 条触摸记录）")

    while True:
        try:
            text = input("\n你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text in ("/exit", "退出"):
            break
        if text == "/feel":
            print(digest(load_moments(DEFAULT_DATA)) or "（还没有触摸记录）")
            continue

        moments = load_moments(DEFAULT_DATA)
        new = moments[seen:]
        seen = len(moments)
        user_msg = digest(new) + "\n\n" + text if new else text
        history.append({"role": "user", "content": user_msg})
        print("🧸 > ", end="", flush=True)
        try:
            chat_once(history, key)
        except Exception as e:
            print(f"\n（调用失败：{e}）")
            history.pop()
            continue
        if len(history) > 22:  # 轻量裁剪：system + 最近 20 条
            history = [history[0]] + history[-20:]
    return 0


if __name__ == "__main__":
    sys.exit(main())
