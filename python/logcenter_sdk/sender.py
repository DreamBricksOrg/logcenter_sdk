from __future__ import annotations

import asyncio
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
        self._stop_event = asyncio.Event()

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

    def start_background_flush(self) -> None:
        if self._bg_task and not self._bg_task.done():
            return
        self._stop_event = asyncio.Event()
        self._bg_task = asyncio.create_task(self._bg_loop())

    async def stop_background_flush(self) -> None:
        if not self._bg_task:
            return
        self._stop_event.set()
        try:
            await self._bg_task
        finally:
            self._bg_task = None
