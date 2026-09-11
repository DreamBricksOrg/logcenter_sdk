# Flask example - logcenter_sdk

App minimo pra testar manualmente o sender/spool refatorado.

## Setup

```bash
cd examples/flask_app
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../../python
cp .env.example .env
```

Edite `.env` se quiser apontar pra um LogCenter real. Por padrao aponta pra
`http://localhost:9999` (ninguem escutando ali), ou seja, todo `send_sync`
vai falhar de propósito e cair no spool - bom pra testar a fila.

## Rodar

```bash
python app.py
```

Sobe em `http://localhost:5001`.

## Testar

```bash
# manda um log (vai falhar contra localhost:9999 e ficar pendente)
curl -X POST http://localhost:5001/log -H "Content-Type: application/json" \
  -d '{"level":"ERROR","message":"teste 1"}'

# ve o estado da fila
curl http://localhost:5001/status
```

Depois de mandar alguns logs, `pending` sobe. Pra ver o retry funcionando:

1. Suba um servidor fake que responda 200 em `/alive` e `/logs/` (ou aponte
   `LOGCENTER_BASE_URL` no `.env` pra um LogCenter real que voce tenha) e
   reinicie o app.
2. Espere `LOGCENTER_FLUSH_INTERVAL_S` segundos (5s por padrao, thread de
   fundo ligada via `auto_flush=true`) - `pending` deve zerar e `backup` subir.
3. Ou force uma tentativa imediata sem esperar o intervalo:
   ```bash
   curl -X POST http://localhost:5001/flush-now
   ```

Os arquivos ficam em `./spool_data/` (`data_logs.jsonl`,
`data_logs_backup.jsonl`, `data_logs_corrupted.jsonl`) - da pra abrir e olhar
direto o JSONL enquanto testa.
