# Configurando o logcenter_sdk no Flask e no FastAPI

Guia rápido de integração. Pra exemplos completos e rodáveis, veja
`examples/flask_app/` (Flask) e `examples/fastapi_app/` (FastAPI) na raiz do
repositório — cada um tem `start.ps1`, `.env.example` e um `README.md` próprio.

---

## `send()` vs `send_sync()`

Os dois fazem exatamente a mesma coisa: tentam o envio HTTP direto; sucesso
grava em `data_logs_backup.jsonl`; qualquer falha (status não-2xx, erro de
rede, config inválida) grava em `data_logs.jsonl` (pendente, pra retry depois).
A única diferença é sync vs async:

| Método | Tipo | Cliente HTTP | Onde usar |
|---|---|---|---|
| `send()` | `async def` | `httpx.AsyncClient` | Código async — **FastAPI**, o `LogCenterAuditMiddleware`, qualquer handler `async def` |
| `send_sync()` | `def` | `httpx.Client` (bloqueante) | Código sync — **Flask**, scripts, workers sem event loop |

Regra prática:
- Dentro de uma rota `async def` (FastAPI) → `await logcenter.send(...)`.
- Dentro de uma rota sync (Flask) → `logcenter.send_sync(...)`.
- **Nunca** chame `send_sync()` dentro de um handler async (bloqueia o event
  loop) nem `send()` fora de um contexto async sem `await`.

---

## Instalação

```bash
pip install -e path/para/o/repo/python
# ou, se publicado: pip install logcenter-sdk
```

---

## Flask (sync)

```python
import os
from pathlib import Path

from flask import Flask, jsonify, request
from logcenter_sdk import LogCenterConfig, LogCenterSender

cfg = LogCenterConfig(
    base_url=os.getenv("LOGCENTER_BASE_URL"),
    project_id=os.getenv("LOGCENTER_PROJECT_ID"),
    api_key=os.getenv("LOGCENTER_API_KEY"),
    spool_dir=Path(os.getenv("LOGCENTER_SPOOL_DIR", ".logcenter")),
)

logcenter = LogCenterSender(cfg)  # auto_flush=True por padrão: thread de
                                  # retry em background já sobe sozinha aqui

app = Flask(__name__)


@app.post("/pedido")
def criar_pedido():
    # ... sua lógica ...
    logcenter.send_sync(
        "INFO",
        "Pedido criado",
        tags=["pedidos"],
        data={"pedido_id": 123},
    )
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(port=5000)
```

Encerrando a thread de background de forma limpa (opcional, útil em dev com
reload):

```python
import atexit

atexit.register(logcenter.stop_background_flush_thread)
```

---

## FastAPI (async)

```python
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from logcenter_sdk import LogCenterAuditMiddleware, LogCenterConfig, LogCenterSender

cfg = LogCenterConfig(
    base_url=os.getenv("LOGCENTER_BASE_URL"),
    project_id=os.getenv("LOGCENTER_PROJECT_ID"),
    api_key=os.getenv("LOGCENTER_API_KEY"),
    spool_dir=Path(os.getenv("LOGCENTER_SPOOL_DIR", ".logcenter")),
)

logcenter = LogCenterSender(cfg)  # auto_flush=True por padrão


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    logcenter.stop_background_flush_thread()


app = FastAPI(lifespan=lifespan)

# Opcional: audita automaticamente excecoes nao tratadas e respostas 5xx
app.add_middleware(LogCenterAuditMiddleware, sender=logcenter)


@app.post("/pedido")
async def criar_pedido():
    # ... sua lógica ...
    await logcenter.send(
        "INFO",
        "Pedido criado",
        tags=["pedidos"],
        data={"pedido_id": 123},
    )
    return {"ok": True}
```

Note que `LogCenterAuditMiddleware` recebe o sender no parâmetro `sender=` (o
nome do parâmetro é fixo na assinatura da classe), mesmo você chamando a
variável local de `logcenter`.

---

## Variáveis de ambiente

Em vez de montar `LogCenterConfig(...)` na mão, dá pra usar
`LogCenterConfig.from_env()`:

```bash
export LOGCENTER_BASE_URL="https://seu-logcenter"
export LOGCENTER_PROJECT_ID="..."
export LOGCENTER_API_KEY="..."
```

```python
from logcenter_sdk import LogCenterConfig, LogCenterSender

cfg = LogCenterConfig.from_env()
logcenter = LogCenterSender(cfg)
```

Campos e variáveis correspondentes: `LOGCENTER_BASE_URL`,
`LOGCENTER_PROJECT_ID`, `LOGCENTER_API_KEY`, `LOGCENTER_TIMEOUT_S`,
`LOGCENTER_SPOOL_DIR`, `LOGCENTER_FLUSH_INTERVAL_S`, `LOGCENTER_AUTO_FLUSH`,
`LOGCENTER_ENABLED`.

---

## Ver os logs da SDK no console

Por padrão a SDK fica silenciosa (usa um `NullHandler`). Pra ver no console
quando um log é enviado, qual linha está sendo reprocessada e qual erro
ocorreu numa falha, configure o `logging` da sua aplicação:

```python
import logging

logging.basicConfig(level=logging.INFO)
```

Isso mostra mensagens dos loggers `logcenter_sdk.sender` e
`logcenter_sdk.spool`. Veja os exemplos completos em `examples/*/app.py` /
`examples/*/main.py`.

---

## Mais detalhes

Comportamento completo do spool (3 arquivos, retry em background, alive
check) está documentado no `README.md` principal da SDK, seção
"🔁 Spool (fila offline)".
