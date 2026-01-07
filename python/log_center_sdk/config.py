from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional
import os


@dataclass(frozen=True)
class LogCenterConfig:
    base_url: str
    project_id: str
    api_key: Optional[str] = None

    timeout_s: float = 10.0
    follow_redirects: bool = True

    # spool (offline queue)
    spool_dir: Path = field(default_factory=lambda: Path(os.getenv("LOGCENTER_SPOOL_DIR", ".logcenter")))
    spool_filename: str = "spool.jsonl"
    spool_max_bytes: int = 25 * 1024 * 1024  # 25MB
    flush_batch_size: int = 200
    flush_interval_s: float = 10.0

    enabled: bool = True

    @staticmethod
    def from_env(prefix: str = "LOGCENTER_") -> "LogCenterConfig":
        base_url = (os.getenv(f"{prefix}BASE_URL") or "").rstrip("/")
        project_id = os.getenv(f"{prefix}PROJECT_ID") or ""
        api_key = os.getenv(f"{prefix}API_KEY")

        timeout_s = float(os.getenv(f"{prefix}TIMEOUT_S", "10"))
        spool_dir = Path(os.getenv(f"{prefix}SPOOL_DIR", ".logcenter"))
        spool_max_bytes = int(os.getenv(f"{prefix}SPOOL_MAX_BYTES", str(25 * 1024 * 1024)))
        flush_batch_size = int(os.getenv(f"{prefix}FLUSH_BATCH_SIZE", "200"))
        flush_interval_s = float(os.getenv(f"{prefix}FLUSH_INTERVAL_S", "10"))
        enabled = os.getenv(f"{prefix}ENABLED", "true").lower() in ("1", "true", "yes", "y")

        if not base_url or not project_id:
            raise ValueError("Missing LOGCENTER_BASE_URL or LOGCENTER_PROJECT_ID")

        return LogCenterConfig(
            base_url=base_url,
            project_id=project_id,
            api_key=api_key,
            timeout_s=timeout_s,
            spool_dir=spool_dir,
            spool_max_bytes=spool_max_bytes,
            flush_batch_size=flush_batch_size,
            flush_interval_s=flush_interval_s,
            enabled=enabled,
        )
