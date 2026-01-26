#include "LogCenterSender.h"

#include <WiFiClientSecure.h>
#include <HTTPClient.h>

static const size_t JSON_CAPACITY = 768; // default seguro
static const char* LOGS_PATH = "/logs/";

LogCenterSender::LogCenterSender(const LogCenterConfig& cfg)
: _cfg(cfg), _spool(cfg.spoolPath) {}

bool LogCenterSender::begin() {
  bool ok = _spool.begin();
  _currentBackoffMs = _cfg.flushIntervalMs;
  _nextFlushAtMs = millis() + _cfg.flushIntervalMs;
  return ok;
}

bool LogCenterSender::_buildPayload(
  String& out,
  const char* level,
  const char* message,
  const char* status,
  const char* timestampIsoZ,
  const char* requestId
) {
  if (!level || !message) return false;

  StaticJsonDocument<JSON_CAPACITY> doc;

  doc["project_id"] = _cfg.projectId;
  doc["level"] = String(level);
  doc["message"] = String(message);

  // status default
  const char* st = status;
  if (!st || !strlen(st)) {
    String lvl = String(level);
    lvl.toUpperCase();
    st = (lvl == "ERROR" || lvl == "CRITICAL" || lvl == "FATAL") ? "ERROR" : "OK";
  }
  doc["status"] = String(st);

  if (timestampIsoZ && strlen(timestampIsoZ)) {
    doc["timestamp"] = String(timestampIsoZ);
  }
  if (requestId && strlen(requestId)) {
    doc["request_id"] = String(requestId);
  }

  JsonArray tags = doc["tags"].to<JsonArray>();
  tags.add("esp");
  tags.add("device");

  JsonObject data = doc["data"].to<JsonObject>();
  data["source"] = "device";

  out.clear();
  serializeJson(doc, out);

  // tamanho máximo por linha (spool também)
  return out.length() > 0 && out.length() <= _cfg.maxLineBytes;
}

bool LogCenterSender::_postLogJson(const String& payloadJson) {
  if (!_cfg.enabled) return false;
  if (_cfg.baseUrl.length() == 0) return false;

  WiFiClientSecure client;
  client.setInsecure(); // aceita qualquer certificado

  HTTPClient http;
  String url = _cfg.baseUrl;
  url += LOGS_PATH;

  if (!http.begin(client, url)) return false;

  http.addHeader("Content-Type", "application/json");
  if (_cfg.apiKey.length()) {
    http.addHeader("x_api_key", _cfg.apiKey);
  }

  int code = http.POST((uint8_t*)payloadJson.c_str(), payloadJson.length());
  http.end();

  return (code >= 200 && code < 300);
}

bool LogCenterSender::send(
  const char* level,
  const char* message,
  const char* status,
  const char* timestampIsoZ,
  const char* requestId,
  bool spoolOnFail
) {
  if (!_cfg.enabled) return false;

  String payload;
  if (!_buildPayload(payload, level, message, status, timestampIsoZ, requestId)) {
    // payload grande demais ou inválido
    return false;
  }

  bool ok = _postLogJson(payload);
  if (!ok && spoolOnFail) {
    _spool.appendLine(payload, _cfg.spoolMaxBytes);
  }
  return ok;
}

LogCenterSender::FlushResult LogCenterSender::flushSpool(uint8_t maxBatches) {
  FlushResult res;

  for (uint8_t i = 0; i < maxBatches; i++) {
    std::vector<String> batch;
    if (!_spool.popBatch(batch, _cfg.flushBatchSize)) {
      res.failed++;
      break;
    }

    if (batch.empty()) break;

    for (auto& line : batch) {
      bool ok = _postLogJson(line);
      if (ok) {
        res.sent++;
      } else {
        res.failed++;
        // recoloca no spool e para (evita loop infinito)
        _spool.appendLine(line, _cfg.spoolMaxBytes);
        res.remaining = _spool.queuedLines();
        return res;
      }
    }
  }

  res.remaining = _spool.queuedLines();
  return res;
}

void LogCenterSender::loopTick() {
  if (!_cfg.enabled) return;

  uint32_t now = millis();
  if ((int32_t)(now - _nextFlushAtMs) < 0) return;

  auto r = flushSpool(5);

  // backoff: se falhou, dobra até 120s
  if (r.failed > 0) {
    _currentBackoffMs = min<uint32_t>(_currentBackoffMs * 2, 120000);
  } else {
    _currentBackoffMs = _cfg.flushIntervalMs;
  }

  _nextFlushAtMs = now + _currentBackoffMs;
}
