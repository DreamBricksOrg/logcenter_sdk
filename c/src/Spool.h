#pragma once
#include <Arduino.h>
#include <vector>

class Spool {
public:
  explicit Spool(const char* path);

  bool begin();
  size_t sizeBytes() const;
  size_t queuedLines() const;

  bool appendLine(const String& line, size_t maxBytes);  // garante newline
  bool popBatch(std::vector<String>& out, size_t batchSize); // remove do arquivo e devolve linhas
  bool ensureMaxBytes(size_t maxBytes); // drop-oldest se exceder
  bool clear();

private:
  const char* _path;

  bool _dropOldestToFit(size_t maxBytes);
  bool _rewriteExcludingFirstN(size_t n);
};
