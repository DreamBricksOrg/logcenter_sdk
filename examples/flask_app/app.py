from __future__ import annotations

import atexit
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from logcenter_sdk import LogCenterConfig, LogCenterSender

load_dotenv()

cfg = LogCenterConfig(
    base_url=os.getenv("LOGCENTER_BASE_URL", "http://localhost:9999"),
    project_id=os.getenv("LOGCENTER_PROJECT_ID", "test-project"),
    api_key=os.getenv("LOGCENTER_API_KEY") or None,
    spool_dir=Path(os.getenv("LOGCENTER_SPOOL_DIR", "./spool_data")),
    flush_interval_s=float(os.getenv("LOGCENTER_FLUSH_INTERVAL_S", "5")),
    auto_flush=os.getenv("LOGCENTER_AUTO_FLUSH", "true").lower() in ("1", "true", "yes"),
)

sender = LogCenterSender(cfg)
atexit.register(sender.stop_background_flush_thread)

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify(
        {
            "app": "flask_app",
            "base_url": cfg.base_url,
            "spool_dir": str(cfg.spool_dir),
            "flush_interval_s": cfg.flush_interval_s,
            "auto_flush": cfg.auto_flush,
        }
    )


@app.post("/log")
def log():
    body = request.get_json(silent=True) or {}
    level = body.get("level", "INFO")
    message = body.get("message", "log de teste (flask)")
    ok = sender.send_sync(
        level,
        message,
        tags=body.get("tags"),
        data=body.get("data"),
        request_id=body.get("request_id"),
    )
    return jsonify({"sent_immediately": ok, "spool": _spool_status()})


@app.get("/status")
def status():
    return jsonify(_spool_status())


@app.post("/flush-now")
def flush_now():
    result = sender.process_pending_sync()
    return jsonify({"result": result, "spool": _spool_status()})


def _spool_status():
    return {
        "pending": sender.spool.pending_count(),
        "backup": sender.spool.backup_count(),
        "corrupted": sender.spool.corrupted_count(),
    }


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "5001")), debug=True, use_reloader=False)
