# FastAPI example - logcenter_sdk

App minimo pra testar manualmente o sender/spool refatorado, incluindo o
`LogCenterAuditMiddleware`.

## Setup

```bash
cd examples/fastapi_app
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../../python
cp .env.example .env
```

Por padrao aponta pra `http://localhost:9999` (ninguem escutando ali), ou
seja, todo `send`/log do middleware vai falhar de propósito e cair no spool.

## Rodar

```bash
uvicorn main:app --reload --port 8001
```

Abre em `http://localhost:8001` (docs interativos em `/docs`).

## Testar

```bash
# manda um log direto (vai falhar contra localhost:9999 e ficar pendente)
curl -X POST http://localhost:8001/log -H "Content-Type: application/json" \
  -d '{"level":"ERROR","message":"teste 1"}'

# testa o middleware: excecao nao tratada -> log automatico
curl http://localhost:8001/boom

# testa o middleware: resposta 5xx -> log automatico
curl http://localhost:8001/five-hundred

# ve o estado da fila
curl http://localhost:8001/status
```

Depois de gerar alguns logs (via `/log`, `/boom` ou `/five-hundred`),
`pending` sobe. Pra ver o retry funcionando:

1. Aponte `LOGCENTER_BASE_URL` no `.env` pra um servidor que responda 200 em
   `/alive` e `/logs/` (um LogCenter real, ou um mock seu) e reinicie o app.
2. Espere `LOGCENTER_FLUSH_INTERVAL_S` segundos (5s por padrao, thread de
   fundo ligada via `auto_flush=true`) - `pending` deve zerar e `backup` subir.
3. Ou force uma tentativa imediata sem esperar o intervalo:
   ```bash
   curl -X POST http://localhost:8001/flush-now
   ```

Os arquivos ficam em `./spool_data/` (`data_logs.jsonl`,
`data_logs_backup.jsonl`, `data_logs_corrupted.jsonl`) - da pra abrir e olhar
direto o JSONL enquanto testa.

Nota: com `--reload` o uvicorn roda num processo worker separado; a thread de
background do sender vive dentro desse worker normalmente, sem problema.
