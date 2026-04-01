from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import LogCenterConfig
from .client import LogCenterHttpClient
from .spool import FileSpool


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LogCenterSender:
    """
    - send(): tenta enviar
    - se falhar, guarda no spool
    - flush_spool(): tenta reenviar spool em lotes
    - start_background_flush(): flush periódico
    """

    def __init__(self, config: LogCenterConfig):
        self.cfg = config
        self.http = LogCenterHttpClient(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_s=config.timeout_s,
            follow_redirects=config.follow_redirects,
        )
        self.spool = FileSpool(config.spool_dir, config.spool_filename, config.spool_max_bytes)

        self._bg_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

        self._bg_thread: Optional[threading.Thread] = None
        self._thread_stop_event: Optional[threading.Event] = None
        self._thread_wake_event: Optional[threading.Event] = None
        self._oneshot_thread: Optional[threading.Thread] = None

        if self.cfg.auto_flush:
            self.start_background_flush_thread()

    def _build_payload(
        self,
        level: str,
        message: str,
        *,
        timestamp: Optional[str] = None,
        tags: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        lvl = (level or "INFO").upper()
        ts = timestamp or _utc_iso()
        if status is None:
            status = "ERROR" if lvl in ("ERROR", "CRITICAL", "FATAL") else "OK"

        payload: Dict[str, Any] = {
            "project_id": project_id or self.cfg.project_id,
            "level": lvl,
            "message": message,
            "timestamp": ts,
            "status": status,
        }
        if tags:
            payload["tags"] = tags
        if data:
            payload["data"] = data
        if request_id:
            payload["request_id"] = request_id
        return payload

    async def send(
        self,
        level: str,
        message: str,
        *,
        timestamp: Optional[str] = None,
        tags: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        spool_on_fail: bool = True,
    ) -> bool:
        if not self.cfg.enabled:
            return False

        payload = self._build_payload(
            level,
            message,
            timestamp=timestamp,
            tags=tags,
            data=data,
            request_id=request_id,
            status=status,
            project_id=project_id,
        )

        try:
            resp = await self.http.post_log(payload)
            ok = 200 <= resp.status_code < 300
            if ok:
                return True
        except Exception:
            ok = False

        if spool_on_fail:
            self.spool.append(payload)
        return False

    def send_spool(
        self,
        level: str,
        message: str,
        *,
        timestamp: Optional[str] = None,
        tags: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        spool_on_fail: bool = True,
    ):
        if not self.cfg.enabled:
            return False

        payload = self._build_payload(
            level,
            message,
            timestamp=timestamp,
            tags=tags,
            data=data,
            request_id=request_id,
            status=status,
            project_id=project_id,
        )
        
        self.spool.append(payload)

        if self.cfg.flush_threshold_count > 0 and self.spool.count() >= self.cfg.flush_threshold_count:
            self._trigger_threshold_flush()

    def send_sync(self, *args, **kwargs) -> bool:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            loop.create_task(self.send(*args, **kwargs))
            return True

        return asyncio.run(self.send(*args, **kwargs))

    async def flush_spool(self, *, max_batches: int = 10) -> Dict[str, Any]:
        """
        Tenta reenviar itens do spool.
        - Se um item falhar, recoloca no spool e para (pra não entrar em loop infinito).
        """
        sent = 0
        failed = 0

        for _ in range(max_batches):
            batch, remaining = self.spool.pop_batch(self.cfg.flush_batch_size)
            if not batch:
                break

            for payload in batch:
                try:
                    resp = await self.http.post_log(payload)
                    ok = 200 <= resp.status_code < 300
                except Exception:
                    ok = False

                if ok:
                    sent += 1
                    continue

                failed += 1
                self.spool.append(payload)
                return {"sent": sent, "failed": failed, "remaining": self.spool.stats().queued}

        return {"sent": sent, "failed": failed, "remaining": self.spool.stats().queued}

    async def _bg_loop(self) -> None:
        backoff = self.cfg.flush_interval_s
        while not self._stop_event.is_set():
            res = await self.flush_spool(max_batches=5)
            if res["failed"] > 0:
                backoff = min(backoff * 2, 120.0)
            else:
                backoff = self.cfg.flush_interval_s

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass

    def flush_spool_sync(self, *, max_batches: int = 10) -> Dict[str, Any]:
        """Synchronous flush of the spool. Safe to call from any thread or sync context."""
        sent = 0
        failed = 0

        for _ in range(max_batches):
            batch, remaining = self.spool.pop_batch(self.cfg.flush_batch_size)
            if not batch:
                break

            for payload in batch:
                try:
                    resp = self.http.post_log_sync(payload)
                    ok = 200 <= resp.status_code < 300
                except Exception:
                    ok = False

                if ok:
                    sent += 1
                    continue

                failed += 1
                self.spool.append(payload)
                return {"sent": sent, "failed": failed, "remaining": self.spool.count()}

        return {"sent": sent, "failed": failed, "remaining": self.spool.count()}

    def _trigger_threshold_flush(self) -> None:
        """Wake the background flush or spawn a one-shot thread when the threshold is crossed."""
        if self._bg_thread and self._bg_thread.is_alive():
            if self._thread_wake_event:
                self._thread_wake_event.set()
            return

        if self._bg_task and not self._bg_task.done():
            # Async background loop is running; it will flush on its own schedule
            return

        # No background flush running — one-shot daemon thread
        if self._oneshot_thread and self._oneshot_thread.is_alive():
            return
        self._oneshot_thread = threading.Thread(target=self.flush_spool_sync, daemon=True)
        self._oneshot_thread.start()

    def start_background_flush_thread(self) -> None:
        """Start a daemon thread that periodically flushes the spool. Works in sync apps."""
        if self._bg_thread and self._bg_thread.is_alive():
            return
        self._thread_stop_event = threading.Event()
        self._thread_wake_event = threading.Event()
        self._bg_thread = threading.Thread(target=self._thread_flush_loop, daemon=True)
        self._bg_thread.start()

    def stop_background_flush_thread(self, timeout: float = 5.0) -> None:
        """Stop the background flush thread."""
        if not self._bg_thread:
            return
        if self._thread_stop_event:
            self._thread_stop_event.set()
        if self._thread_wake_event:
            self._thread_wake_event.set()
        self._bg_thread.join(timeout=timeout)
        self._bg_thread = None

    def _thread_flush_loop(self) -> None:
        backoff = self.cfg.flush_interval_s
        while not self._thread_stop_event.is_set():
            res = self.flush_spool_sync(max_batches=5)
            if res["failed"] > 0:
                backoff = min(backoff * 2, 120.0)
            else:
                backoff = self.cfg.flush_interval_s
            self._thread_wake_event.wait(timeout=backoff)
            self._thread_wake_event.clear()

    def start_background_flush(self) -> None:
        if self._bg_task and not self._bg_task.done():
            return
        self._stop_event = asyncio.Event()
        self._bg_task = asyncio.create_task(self._bg_loop())

    async def stop_background_flush(self) -> None:
        if not self._bg_task:
            return
        if self._stop_event:
            self._stop_event.set()
        try:
            await self._bg_task
        finally:
            self._bg_task = None
