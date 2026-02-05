# LogCenter SDK (Python)

SDK oficial para envio de logs ao **LogCenter**, projetado para ser utilizado como biblioteca em aplicações Python da empresa, com foco em **padronização, observabilidade e baixo acoplamento**.

> ⚠️ **Importante**: a versão atual **NÃO é offline-first por padrão**. O spool (fila em arquivo) existe no SDK, mas **só é usado se você optar por isso**. Por default, o SDK tenta enviar e falha silenciosamente se a API estiver indisponível.

---

## ✨ Principais Características

-   Envio de logs estruturados para o LogCenter (V2)
-   Contrato compatível com o schema oficial `LogCreate`
-   Uso independente de framework (FastAPI, Flask, Django, workers, scripts, etc.)
-   Suporte a **middleware ASGI** para auditoria automática
-   Timestamp controlável (inclusive igualdade exata no `/dash`)
-   Integração simples via código ou variáveis de ambiente
-   **Spool opcional em arquivo** (desativável por chamada)

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

## 🔁 Spool (fila offline) – **opcional**

O SDK possui suporte a spool em arquivo (`jsonl`), mas **não é obrigatório usar**.

### Comportamento padrão

-   O SDK tenta enviar o log
-   Se falhar, **NÃO spoola**, a menos que você permita

### Habilitando spool por chamada

```python
await sender.send(
    level="ERROR",
    message="Falha crítica",
    spool_on_fail=True,
)
```

### Reenvio manual do spool

```python
await sender.flush_spool()
```

### Background flush (opcional)

```python
sender.start_background_flush()
```

Encerramento:

```python
await sender.stop_background_flush()
```

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
    
-   NÃO exige spool
    

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
0.1.0-dev
```

Alinhado com LogCenter V2 e dashboard unificado.

---

## 🛣️ Roadmap

-   Integração opcional com `structlog`
-   Métricas internas do SDK
-   Compressão de batches
-   Buffer