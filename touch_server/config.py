"""config.py · 可调参数集中地。

教程经验值，真机联调后按手感微调，全部做成常量便于覆盖。
Phase 1 实现时补全 + 支持环境变量/命令行覆盖。
"""

# 触发阈值：力度 >= TRIGGER 才算"按下了"
TRIGGER = 300

# 动作分类时间边界（秒）
POKE_MAX = 0.4      # 短于 0.4s = 戳
HOLD_MIN = 2.5      # 超过 2.5s = 抱住不放

# 抚摸判定
STROKE_SWEEPS = 3   # 连续轻扫 >= 3 次 = 抚摸

# 通道体检：连续安静 N 拍才"上岗"
SETTLE_BEATS = 20

# 板子节拍间隔（秒），与固件 delay(120) 对应
BEAT_SEC = 0.12

# 服务
HOST = "0.0.0.0"
PORT = 9333
ENDPOINT = "/hello"

# 输出
DATA_FILE = "data/touch_moments.jsonl"
