// touch_doll.ino · 共感娃娃 demo 固件（加固版 · ESP32-S3 · 单传感器）
// 加固点：① WiFi 掉线每 5 秒自动重连 ② HTTP 2 秒超时不再卡死 ③ 每 2 秒打心跳，能看出循环在跑
#include <WiFi.h>
#include <HTTPClient.h>

// ⚠️ 烧录前必改这三行（详见 docs/DEPLOYMENT.md）：
//   SSID/WIFI_PASS 填你自己的 2.4G WiFi；HOME 填电脑局域网 IP（ipconfig 查）。
//   也可用 launcher.py 自动改写 HOME 的 IP，然后重新烧录。
const char* SSID = "YOUR_WIFI_SSID";      // ← 改成你的 2.4G WiFi 名
const char* PASS = "YOUR_WIFI_PASSWORD";  // ← 改成你的 WiFi 密码
const char* HOME = "http://192.168.1.100:9333/hello";  // ← 改成电脑局域网 IP

const int SENSOR_PIN = 4;   // ADC1（GPIO1~10 才可用）
const char* KEY = "bd";     // 与电脑端 posmap.py 对应（bd=脸）

unsigned long lastBeat = 0;
unsigned long lastWifiTry = 0;
int beatCount = 0;
int lastCode = 999;

void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  unsigned long now = millis();
  if (now - lastWifiTry < 5000) return;      // 每 5 秒尝试重连一次
  lastWifiTry = now;
  Serial.println("[wifi] 掉线，重连中…");
  WiFi.disconnect();
  WiFi.begin(SSID, PASS);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== touch_doll 启动 ===");
  analogReadResolution(12);                  // 0~4095
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(SSID, PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(200);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[wifi] 连上了 IP=");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[wifi] 没连上（后台继续重试，检查热点/密码）");
  }
  lastWifiTry = millis();
}

void loop() {
  ensureWiFi();                              // 掉线自动重连
  unsigned long now = millis();
  if (now - lastBeat >= 120) {
    lastBeat = now;
    int v = analogRead(SENSOR_PIN);
    if (WiFi.status() == WL_CONNECTED) {
      String j = String("{\"") + KEY + "\":" + v + "}";
      HTTPClient h;
      h.setConnectTimeout(2000);             // 不再无限等待
      h.setTimeout(2000);
      h.begin(HOME);
      h.addHeader("Content-Type", "application/json");
      lastCode = h.POST(j);
      h.end();
    } else {
      lastCode = -99;                        // -99 = 当前没 WiFi
    }
    beatCount++;
    if (beatCount % 16 == 0) {               // 约每 2 秒一条心跳，不刷屏
      Serial.print("[beat ");
      Serial.print(beatCount);
      Serial.print("] bd=");
      Serial.print(v);
      Serial.print("  WiFi=");
      Serial.print(WiFi.status() == WL_CONNECTED ? "OK" : "DOWN");
      Serial.print("  POST=");
      Serial.println(lastCode);              // 200=成功到服务器; -1=连不上; -99=没WiFi
    }
  }
  delay(10);
}
