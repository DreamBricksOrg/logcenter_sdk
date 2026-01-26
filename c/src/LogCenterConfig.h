#pragma once
#include <Arduino.h>

struct LogCenterConfig {
  String baseUrl;
  String projectId;
  String apiKey;
  bool enabled = true;

  // Spool (LittleFS)
  const char* spoolPath = "/spool.jsonl";
  size_t spoolMaxBytes = 256 * 1024;    // 256KB
  size_t maxLineBytes  = 1024;          // 1KB por log

  // Flush
  uint16_t flushBatchSize = 15;         // logs por tentativa
  uint32_t flushIntervalMs = 10 * 1000; // 10s base
};
