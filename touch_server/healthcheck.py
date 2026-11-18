"""healthcheck.py · 通道体检。

规则（教程）：通道上电后需连续 20 拍安静（读数 < 触发阈值）才"上岗"；
上岗前若出现触发级读数会清零计数重来。这样接线坏/悬空乱漂的通道不会乱报。
"""
from . import config


class ChannelGate:
    """单通道上岗闸门。"""

    def __init__(self, quiet_beats=None):
        self.quiet_beats = quiet_beats if quiet_beats is not None else config.SETTLE_BEATS
        self._quiet = 0
        self.armed = False

    def feed(self, value, trigger=None):
        """喂一拍读数。返回该通道是否已上岗。"""
        trigger = config.TRIGGER if trigger is None else trigger
        if self.armed:
            return True
        if value < trigger:
            self._quiet += 1
            if self._quiet >= self.quiet_beats:
                self.armed = True
        else:
            self._quiet = 0  # 上岗前就被按 → 推倒重来
        return self.armed
