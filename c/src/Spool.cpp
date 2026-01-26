#include "Spool.h"

#include <FS.h>
#include <LittleFS.h>

Spool::Spool(const char* path) : _path(path) {}

bool Spool::begin() {
  return LittleFS.begin(true);
}

size_t Spool::sizeBytes() const {
  File f = LittleFS.open(_path, "r");
  if (!f) return 0;
  size_t sz = f.size();
  f.close();
  return sz;
}

size_t Spool::queuedLines() const {
  File f = LittleFS.open(_path, "r");
  if (!f) return 0;
  size_t count = 0;
  while (f.available()) {
    String line = f.readStringUntil('\n');
    if (line.length()) count++;
  }
  f.close();
  return count;
}

bool Spool::appendLine(const String& line, size_t maxBytes) {
  if (!line.length()) return false;

  // tenta garantir espaço antes
  ensureMaxBytes(maxBytes);

  File f = LittleFS.open(_path, "a");
  if (!f) return false;

  // garante newline
  String out = line;
  if (!out.endsWith("\n")) out += "\n";

  size_t written = f.print(out);
  f.close();

  // se estourou, drop-oldest
  ensureMaxBytes(maxBytes);

  return written == out.length();
}

bool Spool::popBatch(std::vector<String>& out, size_t batchSize) {
  out.clear();

  File f = LittleFS.open(_path, "r");
  if (!f) return false;

  while (f.available() && out.size() < batchSize) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length()) out.push_back(line);
  }

  // conta quantas linhas vamos remover
  size_t n = out.size();
  f.close();

  if (n == 0) return true;

  return _rewriteExcludingFirstN(n);
}

bool Spool::_rewriteExcludingFirstN(size_t n) {
  File in = LittleFS.open(_path, "r");
  if (!in) return false;

  File tmp = LittleFS.open("/spool.tmp", "w");
  if (!tmp) { in.close(); return false; }

  size_t skipped = 0;
  while (in.available()) {
    String line = in.readStringUntil('\n');
    // mantém exatamente como veio (mas garantindo newline na gravação)
    if (skipped < n) {
      skipped++;
      continue;
    }
    if (!line.endsWith("\n")) line += "\n";
    tmp.print(line);
  }

  in.close();
  tmp.close();

  LittleFS.remove(_path);
  return LittleFS.rename("/spool.tmp", _path);
}

bool Spool::ensureMaxBytes(size_t maxBytes) {
  if (maxBytes == 0) return true;
  size_t sz = sizeBytes();
  if (sz <= maxBytes) return true;
  return _dropOldestToFit(maxBytes);
}

bool Spool::_dropOldestToFit(size_t maxBytes) {
  // Estratégia simples:
  // - se arquivo > maxBytes, remove linhas do começo até caber.
  // Para evitar loop gigante, remove “em blocos” de 10 linhas.
  const size_t block = 10;

  while (sizeBytes() > maxBytes) {
    std::vector<String> batch;
    if (!popBatch(batch, block)) return false;
    if (batch.size() == 0) {
      // não conseguiu reduzir (arquivo vazio ou corrompido)
      return clear();
    }
  }
  return true;
}

bool Spool::clear() {
  LittleFS.remove(_path);
  File f = LittleFS.open(_path, "w");
  if (!f) return false;
  f.close();
  return true;
}
