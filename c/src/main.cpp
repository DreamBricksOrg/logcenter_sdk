#include <Arduino.h>
#include <WiFi.h>

#include "LogCenterConfig.h"
#include "LogCenterSender.h"
#include "config.h"

LogCenterSender* sender = nullptr;
LogCenterConfig cfg;

static bool wifi_ok() {
  return WiFi.status() == WL_CONNECTED;
}

void setup() {
  Serial.begin(115200);

  cfg.baseUrl = LOGCENTER_BASE_URL;
  cfg.projectId = LOGCENTER_PROJECT_ID;
  cfg.apiKey = LOGCENTER_API_KEY;
  cfg.enabled = true;

  cfg.spoolPath = "/spool.jsonl";
  cfg.spoolMaxBytes = 256 * 1024;
  cfg.maxLineBytes = 1024;

  cfg.flushBatchSize = 15;
  cfg.flushIntervalMs = 10 * 1000;

  sender = new LogCenterSender(cfg);

  if (!sender->begin()) {
    Serial.println("LittleFS begin failed");
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  uint32_t t0 = millis();
  while (!wifi_ok() && millis() - t0 < 15000) {
    delay(250);
  }

  sender->send("INFO", "Device booted", "OK", nullptr, nullptr, true);
}

void loop() {
  sender->loopTick();

  static uint32_t last = 0;
  if (millis() - last > 30000) {
    last = millis();
    sender->send("INFO", wifi_ok() ? "Heartbeat online" : "Heartbeat offline", "OK", nullptr, nullptr, true);
  }

  delay(20);
}
