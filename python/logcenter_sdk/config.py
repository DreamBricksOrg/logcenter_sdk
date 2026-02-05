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
    def _load_env_file_values() -> Dict[str, str]:
        for filename in (".env", "env"):
            env_path = Path.cwd() / filename
            if not env_path.is_file():
                continue

            values: Dict[str, str] = {}
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if not key:
                    continue

                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
                    value = value[1:-1]

                values[key] = value

            return values

        return {}

    @staticmethod
    def _get_prefixed_value(values: Dict[str, str], prefix: str, key: str, default: Optional[str] = None) -> Optional[str]:
        env_key = f"{prefix}{key}"
        if env_key in values:
            return values[env_key]
        return os.getenv(env_key, default)

    @staticmethod
    def from_env(prefix: str = "LOGCENTER_") -> "LogCenterConfig":
        file_values = LogCenterConfig._load_env_file_values()

        base_url = (LogCenterConfig._get_prefixed_value(file_values, prefix, "BASE_URL", "") or "").rstrip("/")
        project_id = LogCenterConfig._get_prefixed_value(file_values, prefix, "PROJECT_ID", "") or ""
        api_key = LogCenterConfig._get_prefixed_value(file_values, prefix, "API_KEY")

        timeout_s = float(LogCenterConfig._get_prefixed_value(file_values, prefix, "TIMEOUT_S", "10") or "10")
        spool_dir = Path(LogCenterConfig._get_prefixed_value(file_values, prefix, "SPOOL_DIR", ".logcenter") or ".logcenter")
        spool_max_bytes = int(
            LogCenterConfig._get_prefixed_value(file_values, prefix, "SPOOL_MAX_BYTES", str(25 * 1024 * 1024))
            or str(25 * 1024 * 1024)
        )
        flush_batch_size = int(LogCenterConfig._get_prefixed_value(file_values, prefix, "FLUSH_BATCH_SIZE", "200") or "200")
        flush_interval_s = float(
            LogCenterConfig._get_prefixed_value(file_values, prefix, "FLUSH_INTERVAL_S", "10") or "10"
        )
        enabled = (LogCenterConfig._get_prefixed_value(file_values, prefix, "ENABLED", "true") or "true").lower() in (
            "1",
            "true",
            "yes",
            "y",
        )

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
