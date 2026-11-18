"""touch_server 包：触觉翻译官。

ESP32-S3 每 120ms POST 一拍 JSON（8 通道力度 0~4095）到 :9333/hello，
本服务负责：通道体检上岗 → 动作分类（戳/按/捏/抱住不放/抚摸）→
把一次完整触摸写成一行 JSON 追加进 data/touch_moments.jsonl。

模块划分见各文件 docstring，Phase 1 逐个以 TDD 实现。
"""

__version__ = "0.1.0"
