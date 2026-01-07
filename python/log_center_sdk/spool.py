from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


@dataclass
class SpoolStats:
    queued: int
    bytes: int


class FileSpool:
    """
    Spool simples e robusto:
      - append-only em JSONL (1 evento por linha)
      - flush consome N linhas e regrava o resto (OK para filas pequenas/médias)
    """

    def __init__(self, spool_dir: Path, filename: str, max_bytes: int):
        self.spool_dir = spool_dir
        self.path = spool_dir / filename
        self.max_bytes = max_bytes
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def stats(self) -> SpoolStats:
        try:
            size = self.path.stat().st_size
        except Exception:
            size = 0

        queued = 0
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for _ in f:
                    queued += 1
        except Exception:
            queued = 0

        return SpoolStats(queued=queued, bytes=size)

    def append(self, item: Dict[str, Any]) -> None:
        raw = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        raw_line = raw + "\n"

        if self.path.exists():
            try:
                size = self.path.stat().st_size
            except Exception:
                size = 0
        else:
            size = 0

        if size + len(raw_line.encode("utf-8")) > self.max_bytes:
            self._trim_to_fit(extra_bytes=len(raw_line.encode("utf-8")))

        with self.path.open("a", encoding="utf-8") as f:
            f.write(raw_line)

    def _trim_to_fit(self, extra_bytes: int) -> None:
        """
        Remove linhas mais antigas até caber.
        Implementação simples: mantém as últimas linhas que cabem.
        """
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines(True)
        except Exception:
            self.path.write_text("", encoding="utf-8")
            return

        kept: List[str] = []
        total = extra_bytes
        for line in reversed(lines):
            b = len(line.encode("utf-8"))
            if total + b > self.max_bytes:
                break
            kept.append(line)
            total += b

        kept.reverse()
        self.path.write_text("".join(kept), encoding="utf-8")

    def pop_batch(self, n: int) -> Tuple[List[Dict[str, Any]], int]:
        """
        Remove e retorna até n itens.
        Retorna (items, remaining_count).
        """
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return ([], 0)

        if not lines:
            return ([], 0)

        take = lines[:n]
        rest = lines[n:]

        items: List[Dict[str, Any]] = []
        for ln in take:
            try:
                items.append(json.loads(ln))
            except Exception:
                continue

        self.path.write_text("\n".join(rest) + ("\n" if rest else ""), encoding="utf-8")
        return (items, len(rest))
