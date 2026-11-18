"""classifier.py · 单通道触摸事件聚合 + 动作粗分类（demo 版）。

输入：按拍的 (t, v)。v >= 阈值视为按下（可持续多拍），之后一拍 < 阈值视为松开，
聚合成一次 TouchEvent，再按时长粗分动作：
  dur < 0.4s → 戳；dur > 2.5s → 抱住不放；其余 → 按。
（多通道的 捏/抚摸 判定留待完整版；本模块保持纯函数/可注入时钟，便于单测。）
"""
from dataclasses import dataclass

from . import config


@dataclass
class TouchEvent:
    key: str
    start: float   # 秒（单调钟）
    end: float
    dur: float     # 持续秒数
    force: int     # 峰值力度 0~4095
    action: str    # 戳 / 按 / 抱住不放


def classify(dur, poke_max=None, hold_min=None):
    """按时长粗分动作（边界：0.4s 算按，2.5s 算按，严格大于/小于才升级）。"""
    poke_max = config.POKE_MAX if poke_max is None else poke_max
    hold_min = config.HOLD_MIN if hold_min is None else hold_min
    if dur < poke_max:
        return "戳"
    if dur > hold_min:
        return "抱住不放"
    return "按"


class TouchTracker:
    """单个通道：按下→松开聚合成一次事件。"""

    def __init__(self, key, trigger=None):
        self.key = key
        self.trigger = config.TRIGGER if trigger is None else trigger
        self._active = False
        self._start = 0.0
        self._peak = 0

    def feed(self, v, t):
        """喂一拍。松开瞬间返回 TouchEvent，其余情况返回 None。"""
        if v >= self.trigger:
            if not self._active:
                self._active = True
                self._start = t
                self._peak = v
            else:
                self._peak = max(self._peak, v)
            return None
        if not self._active:
            return None
        self._active = False
        dur = t - self._start
        ev = TouchEvent(key=self.key, start=self._start, end=t, dur=dur,
                        force=self._peak, action=classify(dur))
        self._peak = 0
        return ev
