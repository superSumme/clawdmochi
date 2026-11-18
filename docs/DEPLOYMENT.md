# 部署步骤 · 从零跑起共感娃娃

> 适用于 Windows。整个项目分三层：**ESP32-S3 固件**（采集触摸）→ **touch-server**（翻译触摸）→ **DeepSeek 对话层**（让玩偶"开口"）。
> 按顺序做完 6 步就能摸它并和它说话。

---

## 0. 环境要求

- Windows 10/11
- Python 3.9+（整个项目纯标准库，无需 pip 装依赖；对话层用 `urllib` 调 API）
- Arduino IDE 2.x
- 一部开 **2.4G 热点**的手机（或用家里 2.4G WiFi）
- DeepSeek API Key（[platform.deepseek.com](https://platform.deepseek.com) 申请）

---

## 1. 装 Arduino IDE 与 ESP32 板支持包

1. 下载并安装 [Arduino IDE 2.x](https://www.arduino.cc/en/software)。
2. 打开 Arduino IDE → 菜单 **文件 → 首选项**，在"附加开发板管理器网址"填入：
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. 菜单 **工具 → 开发板 → 开发板管理器**，搜 `esp32`，安装 **esp32 by Espressif Systems**（建议 3.x）。
   > 首次下载较大，若卡住可挂代理或换网络重试。
4. 菜单 **工具 → 开发板 → esp32 → ESP32S3 Dev Module**。
5. 按下面的参数配置（**关键，参数错了烧不进**）：

| 选项 | 值 |
|---|---|
| USB Mode | `Hardware CDC and JTAG` |
| Upload Mode | `UART0 / Hardware CDC` |
| USB CDC On Boot | `Enabled` |
| Flash Mode | `DIO` |
| Flash Size | `16MB (128Mb)` |
| PSRAM | `OPI` |
| Partition Scheme | `Default 4MB with spiffs`（默认即可） |
| Upload Speed | `921600` |

---

## 2. 改固件三处配置

打开 `firmware/touch_doll/touch_doll.ino` 顶部，改这三行：

```cpp
const char* SSID = "YOUR_WIFI_SSID";      // 你的 2.4G WiFi 名
const char* PASS = "YOUR_WIFI_PASSWORD";  // WiFi 密码
const char* HOME = "http://192.168.1.100:9333/hello";  // 电脑局域网 IP
```

**怎么查电脑 IP**：在电脑上开命令行，执行 `ipconfig`，找到正在连热点/WiFi 的那块网卡的 `IPv4 地址`（形如 `192.168.x.x`），把 `HOME` 里的 `192.168.1.100` 换成它。端口 `9333` 不变。

> 电脑和板子必须在**同一个 WiFi/热点**下。热点断开或电脑 IP 变了，固件就要重改重烧（或用第 6 节的 `launcher.py` 自动改）。

---

## 3. 烧录固件

1. 用**数据线**连接板子到电脑，认准板子上标 **USB** 的 Type-C 口（另一个是 COM/UART，烧不进）。
2. Arduino IDE 里选对端口（工具 → 端口，Windows 下是 `COMx`）。
3. 点右上角 **上传** 箭头。
4. 如果一直卡在 connecting / 上传失败：
   - 换数据线（九成问题是线）；
   - 按住板子 **BOOT** 键不放 → 点一下 **RST** → 松开 BOOT，让它进下载模式再上传；
   - 仍不行先全片擦除：`esptool --chip esp32s3 --port COMx erase_flash`，再重烧。

> 常见坑：烧录工具最后一步复位可能把原生 USB 的板子又拽回下载模式，导致程序不跑、串口无输出。此时**只点一下 RST**（不按 BOOT）即可正常启动。

烧完打开串口监视器（115200），应看到重启横幅和 `[beat ...] POST=...` 心跳，具体见[接线教程第 5 节](WIRING.md#5-通电验证)。

---

## 4. 启动 touch-server（触觉翻译官）

在**仓库根目录**开一个终端：

```bash
cd clawdmochi
python -m touch_server.server
```

看到：

```
touch-server 已启动 http://0.0.0.0:9333   记录文件: .../data/touch_moments.jsonl
```

就成功了。浏览器打开 `http://localhost:9333/` 可看通道上岗状态；板子发来的数据会打印成形如：

```
22:35:58  屁股 · 抱住不放 · 力度4095 · 3.25秒
```

> **Windows 防火墙**：首次运行若弹出"允许访问"，请勾选专用网络允许；否则板子的 POST 进不来。若已误点拒绝，到"Windows Defender 防火墙 → 允许应用"里放行 Python，或手动加入站规则放行 TCP 9333。

---

## 5. 配置 DeepSeek 并对话

1. 在仓库根目录新建一个 `.env` 文件（复制 `.env.example` 改名），内容：

   ```
   DEEPSEEK_API_KEY=sk-你的真实key
   DEEPSEEK_MODEL=deepseek-chat
   ```

   > `.env` 已被 `.gitignore` 忽略，不会被提交到仓库。

2. 保持 touch-server 终端开着，**另开一个终端**进入交互对话：

   ```bash
   python chat/demo_chat.py
   ```

3. 摸传感器 → 打字问它"我刚才对你做了什么？" → 它会从【体感】记录里答出部位、动作、力度、时长。

   - `/feel`：查看当前体感记录
   - `/exit`：退出

**动作判定**（参数都在 `touch_server/config.py`）：

| 判定 | 规则 |
|---|---|
| 戳 | 力度≥300 且持续 < 0.4s |
| 抱住不放 | 力度≥300 且持续 > 2.5s |
| 按 | 其余 |
| 上岗 | 通道连续 20 拍安静（<300）才启用，防止坏通道乱报 |

建议测试：**按住 3 秒**（抱住不放）→ 问"我刚才对你做了什么？" → **快速戳一下** → 再问，看它是否答对。

---

## 6. 一键启动 + 自检（推荐日常使用）

Windows 下**双击 `start.bat`**（或命令行 `python launcher.py`），它会自动：

1. 自检并打印：电脑 IP / 固件期望 IP / touch-server / 板子是否在热点 / 数据是否到达；
2. 电脑 IP 变了**自动改写固件里的地址**（然后你重新烧录一次即可）；
3. 拉起 touch-server 并守护（挂了自动重启）；
4. 打开网页版对话页 `http://127.0.0.1:9334`：摸它时它会自动"开口"说话，也能打字聊。

这个窗口别关，每 5 分钟会再报一次状态。

---

## 7. 跑自测

```bash
python tests/test_pipeline.py
```

应显示 `19 PASS / 0 FAIL`（覆盖时长分类边界、上岗闸门、事件聚合、端到端 HTTP）。

---

## 8. 排查速查

| 现象 | 排查 |
|---|---|
| 串口 `POST=-99` | WiFi 没连上：确认 2.4G、密码正确 |
| 串口 `POST=-1` | 服务器没启动，或 `HOME` 的 IP 写错 |
| 服务器收不到数据 | ① 防火墙放行 9333；② 电脑和板子在同一网段；③ 电脑 IP 是否变了 |
| 读数乱漂 | 检查接线/面包板触点；降低环境电磁干扰 |
| 对话层报缺 key | `.env` 没建或 key 填错 |
| 板子重新上电后 IP 对不上 | 用 `launcher.py` 自动改 IP 后重新烧录；或给电脑/板子分配固定 IP |

---

## API 与隐私说明

- 触摸记录写在 `data/touch_moments.jsonl`（已 gitignore，不进仓库），属隐私数据，可随时删除。
- 对话只把最近若干条体感便签发给 DeepSeek；API Key 只存在本地 `.env`。
- 想改成别的 AI：对话层走 OpenAI 兼容接口，改 `.env` 里的 `DEEPSEEK_BASE` / `DEEPSEEK_MODEL` 即可。

完成 ✅ —— 现在你有了一个"摸得到、会回应"的 AI 玩偶。
