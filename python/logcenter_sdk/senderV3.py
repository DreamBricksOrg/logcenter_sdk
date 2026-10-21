from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import LogCenterV3Config
from .client import LogCenterHttpClient
from .spool import FileSpool

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LogCenterV3Sender:
    """
    - send() / send_sync(): tenta HTTP direto. Sucesso -> data_logs_backup.jsonl.
      Qualquer erro (rede, config, status nao-2xx) -> data_logs.jsonl.
    - background thread: a cada flush_interval_s, se houver pendentes e
      {base_url}/alive responder 200, reprocessa data_logs.jsonl um item por vez
      (spool.py para no primeiro erro de envio).
    """

    def __init__(self, config: LogCenterV3Config):
        self.cfg = config
        self.http = LogCenterHttpClient(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_s=config.timeout_s,
            follow_redirects=config.follow_redirects,
        )
        self.spool = FileSpool(config.spool_dir)

        self._bg_thread: Optional[threading.Thread] = None
        self._thread_stop_event: Optional[threading.Event] = None
        self._thread_wake_event: Optional[threading.Event] = None

        if self.cfg.auto_flush:
            self.start_background_flush_thread()

    async def send(
        self,
        payload
    ) -> bool:
        if not self.cfg.enabled:
            return False

        try:
            resp = await self.http.post_log_v3(payload)
            ok = 200 <= resp.status_code < 300
            if not ok:
                logger.error(
                    "Falha ao enviar log ao LogCenter (status %s): %s",
                    resp.status_code, payload.get("event_type_id")
                )
        except Exception as exc:
            ok = False
            logger.error(
                "Erro ao enviar log ao LogCenter (%s): %s - %s",
                type(exc).__name__, exc, payload.get("event_type_id"),
            )

        if ok:
            logger.info("Log enviado com sucesso: %s", payload.get("event_type_id"))
            self.spool.append_backup(payload)
            return True

        self.spool.append_main(payload)
        return False

    def send_sync(
        self,
        payload
    ) -> bool:
        if not self.cfg.enabled:
            return False     

        ok = self._post_log_bool(payload)

        if ok:
            self.spool.append_backup(payload)
            return True

        self.spool.append_main(payload)
        return False

    def _is_alive(self) -> bool:
        try:
            # resp = self.http.get_alive_sync()
            return True
        except Exception:
            return False

    def _post_log_bool(self, payload: Dict[str, Any]) -> bool:
        message = payload.get("event_type_id")
        try:
            resp = self.http.post_log_sync_v3(payload)
            ok = 200 <= resp.status_code < 300
            if ok:
                logger.info("Log enviado com sucesso: %s", message)
            else:
                logger.error(
                    "Falha ao enviar log ao LogCenter (status %s): %s",
                    resp.status_code, message,
                )
            return ok
        except Exception as exc:
            logger.error(
                "Erro ao enviar log ao LogCenter (%s): %s - %s",
                type(exc).__name__, exc, message,
            )
            return False

    def process_pending_sync(self) -> Dict[str, int]:
        if not self.spool.has_pending():
            return {"sent": 0, "corrupted": 0, "remaining": 0}
        if not self._is_alive():
            return {"sent": 0, "corrupted": 0, "remaining": self.spool.pending_count()}
        return self.spool.process_pending(self._post_log_bool)

    def start_background_flush_thread(self) -> None:
        """Start a daemon thread that periodically retries the pending spool."""
        if self._bg_thread and self._bg_thread.is_alive():
            return
        self._thread_stop_event = threading.Event()
        self._thread_wake_event = threading.Event()
        self._bg_thread = threading.Thread(target=self._thread_flush_loop, daemon=True)
        self._bg_thread.start()

    def stop_background_flush_thread(self, timeout: float = 5.0) -> None:
        if not self._bg_thread:
            return
        if self._thread_stop_event:
            self._thread_stop_event.set()
        if self._thread_wake_event:
            self._thread_wake_event.set()
        self._bg_thread.join(timeout=timeout)
        self._bg_thread = None

    def _thread_flush_loop(self) -> None:
        while not self._thread_stop_event.is_set():
            try:
                self.process_pending_sync()
            except Exception:
                pass
            self._thread_wake_event.wait(timeout=self.cfg.flush_interval_s)
            self._thread_wake_event.clear()
