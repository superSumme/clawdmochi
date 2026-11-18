"""feel.py · 把 touch_moments.jsonl 翻译成"体感便签"。

demo 里这些便签会喂给 DeepSeek，让它"感觉到"被摸。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "touch_moments.jsonl"

ACTION_WORDS = {
    "戳": "戳了你一下",
    "按": "按着你",
    "捏": "捏了你一下",
    "抚摸": "轻轻抚摸你",
    "抱住不放": "紧紧抱住了你",
}


def force_words(v):
    if v >= 3500:
        return "很用力"
    if v >= 2000:
        return "用力"
    if v >= 1000:
        return "不轻不重地"
    return "轻轻地"


def load_moments(path=None):
    path = Path(path) if path else DEFAULT_DATA
    if not path.exists():
        return []
    moments = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    moments.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return moments


def describe(m):
    verb = ACTION_WORDS.get(m.get("action"), f"{m.get('action', '触碰')}了你一下")
    pos = m.get("pos", "某个位置")
    force = force_words(m.get("force", 0))
    dur = m.get("dur", 0)
    dur_s = f"{dur} 秒" if dur >= 1 else f"{int(dur * 1000)} 毫秒"
    return (f"{m.get('ts', '??')} 有人{force}地{verb}"
            f"（{pos}，力度 {m.get('force')}，持续 {dur_s}）")


def digest(moments, limit=8):
    """最近 N 条 → 多行体感文本（新的在前）。"""
    if not moments:
        return ""
    recent = moments[-limit:][::-1]
    return "\n".join("【体感】" + describe(m) for m in recent)


if __name__ == "__main__":
    all_m = load_moments()
    print(f"共 {len(all_m)} 条记录")
    print(digest(all_m) or "（还没有触摸记录 —— 先摸一摸传感器）")
