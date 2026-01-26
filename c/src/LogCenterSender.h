#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <vector>

#include "LogCenterConfig.h"
#include "Spool.h"

class LogCenterSender {
public:
  explicit LogCenterSender(const LogCenterConfig& cfg);

  bool begin();

  bool send(
    const char* level,
    const char* message,
    const char* status = nullptr,
    const char* timestampIsoZ = nullptr,
    const char* requestId = nullptr,
    bool spoolOnFail = true
  );

  // Flush do spool (retorna sent/failed/remaining)
  struct FlushResult {
    uint32_t sent = 0;
    uint32_t failed = 0;
    uint32_t remaining = 0;
  };

  FlushResult flushSpool(uint8_t maxBatches = 5);

  void loopTick();

  // Configurações runtime
  void setEnabled(bool enabled) { _cfg.enabled = enabled; }

private:
  LogCenterConfig _cfg;
  Spool _spool;

  // backoff
  uint32_t _nextFlushAtMs = 0;
  uint32_t _currentBackoffMs = 0;

  // HTTP
  bool _postLogJson(const String& payloadJson);

  // JSON build
  bool _buildPayload(
    String& out,
    const char* level,
    const char* message,
    const char* status,
    const char* timestampIsoZ,
    const char* requestId
  );
};
