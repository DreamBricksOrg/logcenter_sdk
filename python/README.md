# LogCenter SDK (Python)

SDK oficial para envio de logs ao **LogCenter**, projetado para ser utilizado como biblioteca em aplicações Python da empresa, com foco em **padronização, observabilidade e baixo acoplamento**.

> ⚠️ **Importante**: `send()` / `send_sync()` tentam o envio HTTP direto e, em **qualquer falha** (status não-2xx, erro de rede, config inválida), gravam o payload em `data_logs.jsonl` — isso é automático e incondicional, não há parâmetro para desativar. O reenvio desses itens pendentes **é automático por padrão**: `LogCenterConfig.auto_flush` já vem `True`, então a thread de background inicia sozinha na criação do `LogCenterSender`. Para desligar esse comportamento, use `LogCenterConfig(auto_flush=False, ...)` — nesse caso os itens pendentes só se acumulam em `data_logs.jsonl` até você chamar `sender.start_background_flush_thread()` ou `sender.process_pending_sync()` manualmente.

## 🚨 Breaking changes (a partir da 0.2.0)

Se você está atualizando de uma versão anterior à `0.2.0`, os seguintes itens **não existem mais**:

-   Métodos `send_spool()`, `flush_spool()` / `flush_spool_sync()` e o par assíncrono sem argumentos `start_background_flush()` / `stop_background_flush()`
-   Parâmetro `spool_on_fail`
-   Campos de `LogCenterConfig`: `spool_filename`, `spool_max_bytes`, `flush_batch_size`, `flush_threshold_count`

Além disso, `LogCenterConfig(auto_flush=...)` agora tem **default `True`** (antes era
`False`) — a thread de reenvio em background liga sozinha ao criar o `LogCenterSender`.
Pra manter o comportamento antigo (retry só quando você chamar explicitamente), passe
`auto_flush=False`.

Veja a seção [🔁 Spool (fila offline)](#-spool-fila-offline) abaixo para o comportamento atual equivalente.

---

## ✨ Principais Características

-   Envio de logs estruturados para o LogCenter (V2)
-   Contrato compatível com o schema oficial `LogCreate`
-   Uso independente de framework (FastAPI, Flask, Django, workers, scripts, etc.)
-   Suporte a **middleware ASGI** para auditoria automática
-   Timestamp controlável (inclusive igualdade exata no `/dash`)
-   Integração simples via código ou variáveis de ambiente
-   **Spool automático em arquivo** ao falhar o envio (`data_logs.jsonl`), com reenvio em background

---

## 📦 Instalação

```bash
pip install logcenter-sdk
```

---

## 🔧 Configuração

### Configuração via código (recomendada)

```python
from logcenter_sdk.config import LogCenterConfig
from logcenter_sdk.sender import LogCenterSender

cfg = LogCenterConfig(
    base_url="LOGCENTER_URL",
    project_id="LOGCENTER_PROJECT_ID",
    api_key="LOGCENTER_API_KEY",  # opcional
    enabled=True,
)

sender = LogCenterSender(cfg)
```

### Configuração via variáveis de ambiente

```bash
export LOGCENTER_BASE_URL="LOGCENTER_URL"
export LOGCENTER_PROJECT_ID="LOGCENTER_PROJECT_ID"
export LOGCENTER_API_KEY="LOGCENTER_API_KEY"
```

```python
from logcenter_sdk.config import LogCenterConfig
from logcenter_sdk.sender import LogCenterSender

cfg = LogCenterConfig.from_env()

sender = LogCenterSender(cfg)
```

---

## 🧾 Contrato de Dados (LogCreate)

O SDK envia logs compatíveis com o schema oficial da API:

```json
{
  "project_id": "string (Mongo ObjectId)",
  "status": "string",
  "level": "INFO | WARN | ERROR | ...",
  "message": "string",
  "timestamp": "ISO-8601 (opcional)",
  "tags": ["string"],
  "data": { "any": "value" },
  "request_id": "string | null"
}
```

### Regras importantes

-   `timestamp` é **top-level**
-   Se `timestamp` não for enviado, o SDK preenche automaticamente
-   Campos extras são ignorados pela API
-   O SDK **não envia `timestamp` dentro de `data`**

---

## 🚀 Enviando Logs

### Envio básico

```python
await sender.send(
    level="INFO",
    message="Usuário logado com sucesso",
    tags=["auth", "backend"],
    data={
        "user_id": 123,
        "campaign": "BlackFriday",
    },
)
```

### Timestamp explícito (igualdade exata no dashboard)

```python
await sender.send(
    level="INFO",
    message="Evento com timestamp exato",
    timestamp="2025-12-08T21:16:12Z",
    tags=["special", "equality-test"],
    data={"marker": "TS_EQ"},
)
```

Permite consultas como:

```http
?timestamp=2025-12-08T21:16:12Z
```

---

## 🔁 Spool (fila offline)

O SDK sempre grava em arquivo (`jsonl`), dentro de `config.spool_dir` (default `.logcenter`, ou `LOGCENTER_SPOOL_DIR`). Nenhum dos arquivos tem limite de tamanho.

### Comportamento automático ao enviar

-   `send()` / `send_sync()` tentam o envio HTTP direto.
-   Sucesso -> o payload é gravado em `data_logs_backup.jsonl` (histórico do que foi entregue).
-   Qualquer falha (status não-2xx, erro de rede, config inválida) -> o payload é gravado em `data_logs.jsonl` (pendente). Isso é incondicional, não existe parâmetro para desativar.
-   Linhas de `data_logs.jsonl` que não conseguem ser parseadas como JSON durante o reprocessamento são movidas para `data_logs_corrupted.jsonl`.

### Reenvio em background

Por padrão (`LogCenterConfig.auto_flush=True`), a thread de background já inicia
sozinha na criação do `LogCenterSender` — você não precisa chamar nada:

```python
sender = LogCenterSender(cfg)  # a thread de background já inicia aqui, dentro do __init__
```

A cada `config.flush_interval_s` segundos, se houver itens pendentes (`spool.has_pending()`), a thread faz `GET {base_url}/alive`; se a resposta for HTTP 200, ela reprocessa `data_logs.jsonl` um item por vez (`process_pending_sync()`), parando no primeiro item que falhar — esse item e os seguintes permanecem pendentes para a próxima rodada.

Para desligar esse comportamento automático:

```python
cfg = LogCenterConfig(
    base_url="LOGCENTER_URL",
    project_id="LOGCENTER_PROJECT_ID",
    auto_flush=False,
)
```

Com `auto_flush=False`, ninguém reenvia sozinho — controle a thread manualmente:

```python
# sender já criado como em "Configuração via código" (LogCenterSender(cfg))
sender.start_background_flush_thread()
...
sender.stop_background_flush_thread()
```

### Reenvio manual (sem thread de background)

Se preferir não rodar a thread, `sender.process_pending_sync()` faz uma única tentativa de reprocessar os itens pendentes (mesma lógica: checa `/alive`, para no primeiro erro).

---

## 🧱 Middleware ASGI (FastAPI / Starlette)

O SDK fornece um middleware de auditoria HTTP.

```python
from logcenter_sdk.middleware import LogCenterAuditMiddleware

app.add_middleware(
    LogCenterAuditMiddleware,
    sender=sender,
)
```

### O que o middleware faz

-   Loga automaticamente:
    
    -   exceções não tratadas
    -   respostas HTTP 5xx
-   NÃO interfere no fluxo da aplicação
    
-   Uma chamada de `send()` que falhe durante a auditoria é spoolada como qualquer outra — o middleware não trata isso de forma especial
    

---

## 📊 Compatibilidade com Dashboard (/dash)

Todos os logs enviados são compatíveis com os filtros atuais.

### Exemplos

```http
?level=ERROR?level__in=INFO,ERROR?message__regex=timeout|cache?data.campaign=Christmas?data.region=BR
```

### Janela de tempo

```http
?timestamp__gte=2025-12-08T20:00:00Z&amp;timestamp__lte=2025-12-08T22:00:00Z
```

---

## ⚠️ Campos Legados (NÃO usar)

Antigo

Correto

`project`

`project_id`

`request`

`request_id`

`timestamp` em `data`

`timestamp` top-level

---

## 🧪 Onde usar

-   APIs (FastAPI, Flask, Django)
-   Workers / consumers
-   Jobs batch
-   Scripts administrativos
-   Serviços internos

---

## 📌 Versão

```
0.2.0
```

Alinhado com LogCenter V2 e dashboard unificado.

---

## 🛣️ Roadmap

-   Integração opcional com `structlog`
-   Métricas internas do SDK
-   Compressão de batches
-   Buffer