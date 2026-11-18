# ClawdMochi · 共感娃娃（触觉玩偶）

> 给你的 AI 造一个摸得到的身体 —— FSR402 压力传感器 + ESP32-S3，让 DeepSeek 真的知道你什么时候摸了它、多用力、多久。
> 当前 demo：单传感器跑通「DeepSeek 有触感」，被摸会自动开口、也能打字陪聊。

## 它能做什么

- 手指按压 FSR402 → ESP32-S3 读出压力（0~4095）→ WiFi 每秒发 ~8 拍到电脑
- touch-server 把压力聚合为一次触摸，粗分动作：**戳 / 按 / 抱住不放**
- DeepSeek 读到【体感】便签后，像真的被摸到一样自然回应
- 自带**一键启动 + 自检**脚本：查 IP、查板子在线、查数据到达、服务挂了自动重启

```
手指按压 → FSR402(3.3V分压) → ESP32-S3 GPIO4 (ADC1)
  → WiFi POST {"bd":力度} → touch-server :9333 (体检→聚合→分类)
  → data/touch_moments.jsonl → DeepSeek 触感层
  → 网页/终端 · 被摸自动发话
```

一条触摸记录：

```json
{"ts":"22:35:58","key":"bd","pos":"屁股","action":"抱住不放","force":4095,"dur":3.25}
```

## 文档（先看这两个）

| 文档 | 内容 |
|---|---|
| **[接线教程](docs/WIRING.md)** | 材料清单、分压电路原理、面包板逐列插法、通电验证、常见问题（[示意图](docs/wiring_demo.png)） |
| **[部署步骤](docs/DEPLOYMENT.md)** | Arduino 环境、板支持包、烧录参数、配置 WiFi/IP、启动服务器、DeepSeek 对话、一键启动、排查 |

其他：[firmware/README.md](firmware/README.md) · [chat/README.md](chat/README.md)

## 快速开始（三步）

```bash
# ① 起 touch-server（纯标准库，无需 pip 装依赖）
cd clawdmochi && python -m touch_server.server
#    浏览器开 http://localhost:9333/ 看通道上岗状态

# ② 接线 + 烧录固件（见 docs/WIRING.md 和 docs/DEPLOYMENT.md，改 WiFi/密码/IP 三处）

# ③ 填 key 后和它说话
#    仓库根目录建 .env（参考 .env.example）：DEEPSEEK_API_KEY=sk-你的key
python chat/demo_chat.py
#    摸传感器 → 问"我刚才对你做了什么？"

# 或者 Windows 下直接双击 start.bat：一键自检 + 拉服务 + 打开网页对话 http://127.0.0.1:9334
```

## 目录结构

```
clawdmochi/
├── README.md              # 本文件
├── start.bat              # Windows 一键启动（自检 + 守护 + 开网页）
├── launcher.py            # 一键启动/自检/自动改固件IP/对话网页
├── .env.example           # DEEPSEEK_API_KEY 模板（.env 已被 gitignore）
├── docs/
│   ├── WIRING.md          # 详细接线教程
│   ├── DEPLOYMENT.md      # 详细部署步骤
│   └── wiring_demo.png    # 接线示意图
├── firmware/
│   ├── README.md
│   └── touch_doll/touch_doll.ino   # ESP32-S3 固件（单传感器）
├── touch_server/          # 触觉翻译官（纯标准库）
│   ├── config.py          #   阈值300 / <0.4s戳 / >2.5s抱 / 120ms节拍
│   ├── posmap.py          #   KEYS→部位（改 BODY_PART 一行即可换部位）
│   ├── healthcheck.py     #   连续20拍安静才"上岗"
│   ├── classifier.py      #   事件聚合 + 动作粗分
│   └── server.py          #   ThreadingHTTPServer :9333 POST /hello
├── chat/                  # DeepSeek 触感层
│   ├── feel.py            #   jsonl → 体感便签
│   ├── demo_chat.py       #   终端流式对话
│   └── README.md
├── data/                  # touch_moments.jsonl 输出（已 gitignore，保护隐私）
└── tests/test_pipeline.py # 自测：python tests/test_pipeline.py（19 PASS）
```

## 自定义

- **换感知部位**（脸/头/尾巴…）：只改 `touch_server/posmap.py` 里的 `BODY_PART` 一行，电脑端记录和小猫人设自动跟着变。
- **调灵敏度/时长**：改 `touch_server/config.py` 的 `TRIGGER`、`POKE_MAX`、`HOLD_MIN`。
- **换 AI 服务商**：对话走 OpenAI 兼容接口，改 `.env` 的 `DEEPSEEK_BASE` / `DEEPSEEK_MODEL`。
- **多传感器**：教程 8 路版的映射在 `posmap.py` 已预留，加 ADC 引脚（限 GPIO1~10）后改固件数组即可。

## 动作判定（demo 粗分版）

| 判定 | 规则 |
|---|---|
| 戳 | 力度≥300 且持续 < 0.4s |
| 抱住不放 | 力度≥300 且持续 > 2.5s |
| 按 | 其余 |
| 上岗 | 通道连续 20 拍安静（<300）才启用，防坏通道乱报 |

力度 = 0~4095 峰值。完整五分类（捏=双通道同时、抚摸=连续轻扫）等接多传感器时再上。

## 自测

```bash
python tests/test_pipeline.py
# 19 PASS / 0 FAIL
```

## 许可与致谢

- 硬件教程原作：《Claude 共感娃娃免焊接教程》by Eve。
- 本项目代码开源，仅供学习交流。DeepSeek API 费用按官方标准自理。

> 隐私说明：触摸记录写在 `data/touch_moments.jsonl`（已 gitignore），API Key 只存本地 `.env`，两者都不会进仓库。
