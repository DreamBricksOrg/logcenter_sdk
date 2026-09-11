from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from logcenter_sdk import LogCenterAuditMiddleware, LogCenterConfig, LogCenterSender

load_dotenv()

# Mostra no console os logs da propria SDK (envio com sucesso, linha sendo
# processada no retry, erro e qual erro). Sem isso a SDK fica silenciosa
# (ela registra um NullHandler por padrao). Uvicorn nao mexe no root logger,
# entao isso convive normal com os logs de acesso do uvicorn.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

cfg = LogCenterConfig(
    base_url=os.getenv("LOGCENTER_BASE_URL", "http://localhost:9999"),
    project_id=os.getenv("LOGCENTER_PROJECT_ID", "test-project"),
    api_key=os.getenv("LOGCENTER_API_KEY") or None,
    spool_dir=Path(os.getenv("LOGCENTER_SPOOL_DIR", "./spool_data")),
    flush_interval_s=float(os.getenv("LOGCENTER_FLUSH_INTERVAL_S", "5")),
    auto_flush=os.getenv("LOGCENTER_AUTO_FLUSH", "true").lower() in ("1", "true", "yes"),
)

logcenter = LogCenterSender(cfg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    logcenter.stop_background_flush_thread()


app = FastAPI(title="logcenter_sdk fastapi example", lifespan=lifespan)
app.add_middleware(LogCenterAuditMiddleware, sender=logcenter)


class LogIn(BaseModel):
    level: str = "INFO"
    message: str = "log de teste (fastapi)"
    tags: list[str] | None = None
    data: dict | None = None
    request_id: str | None = None


@app.get("/")
async def index():
    return {
        "app": "fastapi_app",
        "base_url": cfg.base_url,
        "spool_dir": str(cfg.spool_dir),
        "flush_interval_s": cfg.flush_interval_s,
        "auto_flush": cfg.auto_flush,
    }


@app.post("/log")
async def log(body: LogIn):
    ok = await logcenter.send(
        body.level,
        body.message,
        tags=body.tags,
        data=body.data,
        request_id=body.request_id,
    )
    return {"sent_immediately": ok, "spool": _spool_status()}


@app.get("/status")
async def status():
    return _spool_status()


@app.post("/flush-now")
async def flush_now():
    result = logcenter.process_pending_sync()
    return {"result": result, "spool": _spool_status()}


@app.get("/boom")
async def boom():
    """Levanta uma excecao nao tratada - o middleware audita automaticamente."""
    raise RuntimeError("erro de teste (boom)")


@app.get("/five-hundred")
async def five_hundred():
    """Retorna 500 - o middleware audita respostas 5xx automaticamente."""
    from fastapi import Response

    return Response(status_code=500)


def _spool_status():
    return {
        "pending": logcenter.spool.pending_count(),
        "backup": logcenter.spool.backup_count(),
        "corrupted": logcenter.spool.corrupted_count(),
    }
