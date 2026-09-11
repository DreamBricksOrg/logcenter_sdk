from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict


MAIN_FILENAME = "data_logs.jsonl"
BACKUP_FILENAME = "data_logs_backup.jsonl"
CORRUPTED_FILENAME = "data_logs_corrupted.jsonl"


class FileSpool:
    """
    data_logs.jsonl        - pendentes, aguardando envio
    data_logs_backup.jsonl - todo log entregue com sucesso (direto ou via retry)
    data_logs_corrupted.jsonl - linhas que nao deram para parsear como JSON

    Nenhum dos tres arquivos tem limite de tamanho.
    """

    def __init__(self, spool_dir: Path):
        self.spool_dir = spool_dir
        self.main_path = spool_dir / MAIN_FILENAME
        self.backup_path = spool_dir / BACKUP_FILENAME
        self.corrupted_path = spool_dir / CORRUPTED_FILENAME
        self._lock = threading.Lock()

        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.main_path.touch(exist_ok=True)
        self.backup_path.touch(exist_ok=True)
        self.corrupted_path.touch(exist_ok=True)

    def _append_line(self, path: Path, item: Dict[str, Any]) -> None:
        raw = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        with path.open("a", encoding="utf-8") as f:
            f.write(raw + "\n")

    def _count_lines(self, path: Path) -> int:
        try:
            with path.open("r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def append_main(self, item: Dict[str, Any]) -> None:
        with self._lock:
            self._append_line(self.main_path, item)

    def append_backup(self, item: Dict[str, Any]) -> None:
        with self._lock:
            self._append_line(self.backup_path, item)

    def has_pending(self) -> bool:
        try:
            return self.main_path.stat().st_size > 0
        except Exception:
            return False

    def pending_count(self) -> int:
        return self._count_lines(self.main_path)

    def backup_count(self) -> int:
        return self._count_lines(self.backup_path)

    def corrupted_count(self) -> int:
        return self._count_lines(self.corrupted_path)

    def process_pending(self, send_fn: Callable[[Dict[str, Any]], bool]) -> Dict[str, int]:
        """
        Processa data_logs.jsonl da linha mais antiga para a mais nova.
        - linha invalida (nao parseia como JSON) -> data_logs_corrupted.jsonl, segue.
        - send_fn(item) retorna True -> data_logs_backup.jsonl, segue.
        - send_fn(item) retorna False -> para o loop; essa linha e as seguintes
          permanecem em data_logs.jsonl, na mesma ordem, para a proxima tentativa.
        send_fn nao deve lancar excecao - deve capturar e retornar False. Isso e
        so uma linha de defesa: se send_fn lancar mesmo assim, o efeito e o
        mesmo de retornar False (a linha atual e as seguintes ficam pendentes).
        """
        with self._lock:
            try:
                lines = self.main_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                return {"sent": 0, "corrupted": 0, "remaining": 0}

            sent = 0
            corrupted = 0
            stop_index = len(lines)

            for i, line in enumerate(lines):
                if not line.strip():
                    continue

                try:
                    item = json.loads(line)
                except Exception:
                    self._append_line(self.corrupted_path, {"raw": line})
                    corrupted += 1
                    continue

                try:
                    ok = send_fn(item)
                except Exception:
                    ok = False

                if ok:
                    self._append_line(self.backup_path, item)
                    sent += 1
                else:
                    stop_index = i
                    break

            remaining_lines = lines[stop_index:]
            if remaining_lines:
                self.main_path.write_text("\n".join(remaining_lines) + "\n", encoding="utf-8")
            else:
                self.main_path.write_text("", encoding="utf-8")

            return {"sent": sent, "corrupted": corrupted, "remaining": len(remaining_lines)}
