# LogCenter SDK (Python)

SDK oficial para envio de logs ao **LogCenter**, projetado para ser utilizado como biblioteca em qualquer aplicação da empresa, sem replicação de código e com foco em **resiliência, padronização e observabilidade**.

---

## ✨ Principais Características

-   Envio de logs estruturados para o LogCenter
-   Compatível com o **LogCenter V2**
-   **Offline-first**: logs são armazenados localmente em caso de falha de rede
-   Retry automático com backoff exponencial
-   Envio em lote (batch)
-   Totalmente compatível com os filtros do `/dash`
-   Pode rodar em background (thread dedicada)
-   Uso simples, sem acoplamento com frameworks

---

## 📦 Instalação

```bash
pip install logcenter-sdk
```

---

## 🔧 Configuração Básica

```python
from logcenter_sdk import LogSender, LogSenderConfigconfig = LogSenderConfig(    log_api="https://logcenter.suaempresa.com",    project_id="69374094b758aa497f59cf1b",    upload_delay=10,)log_sender = LogSender(config)
```

Também é possível configurar via variáveis de ambiente:

```bash
export LOG_API=https://logcenter.suaempresa.comexport PROJECT_ID=69374094b758aa497f59cf1b
```

```python
from logcenter_sdk import create_log_sender_from_envlog_sender = create_log_sender_from_env()
```

---

## 🧾 Contrato de Dados (LogCreate)

O SDK envia logs compatíveis com o schema oficial da API:

```json
{  "project_id": "string (Mongo ObjectId)",  "status": "string",  "level": "INFO | WARN | ERROR | ...",  "message": "string",  "timestamp": "ISO-8601 (opcional)",  "tags": ["string"],  "data": { "any": "value" },  "request_id": "string | null"}
```

### Regras Importantes

-   `timestamp` é **top-level**
-   Se `timestamp` não for enviado, o servidor preencherá automaticamente
-   Campos extras são ignorados pela API
-   O SDK sempre envia dados compatíveis com esse contrato

---

## 🚀 Enviando Logs

### Exemplo básico

```python
log_sender.log(    message="Usuário logado com sucesso",    level="INFO",    tags=["auth", "backend"],    data={        "user_id": 123,        "campaign": "BlackFriday"    },    request={"id": "req-abc-123"})
```

### Enviando log com timestamp explícito

```python
log_sender.log(    message="Evento com timestamp exato",    level="INFO",    timestamp="2025-12-08T21:16:12Z",    tags=["special", "equality-test"],    data={"marker": "TS_EQ"})
```

> Isso permite filtros exatos como `?timestamp=2025-12-08T21:16:12Z` no dashboard.

---

## 🌐 Modo Offline & Resiliência

O SDK é **offline-first por design**.

### Como funciona

-   Todo log é **salvo localmente antes do envio**
    
-   Se a API estiver indisponível:
    
    -   o log permanece no arquivo local
    -   o SDK tenta reenviar automaticamente
-   Quando a conexão retorna:
    
    -   os logs pendentes são reenviados em lote

### Estrutura de arquivos

```text
logs/├── datalogs.csv        # logs pendentes└── datalogs_backup.csv # logs enviados com sucesso
```

Nenhum log é perdido.

---

## 🔁 Envio em Background

O SDK pode rodar um worker em background para envio contínuo:

```python
log_sender.start_background_sender()
```

Para parar:

```python
log_sender.stop_background_sender()
```

Também pode ser usado como context manager:

```python
with log_sender:    log_sender.log("Aplicação iniciada")
```

---

## 📊 Compatibilidade com Dashboard (/dash)

Todos os logs enviados pelo SDK são **100% compatíveis** com os filtros do dashboard.

### Exemplos de filtros suportados

```http
?level=ERROR?level__in=INFO,ERROR?message__regex=timeout|cache?data.campaign=Christmas?data.region=BR
```

### Filtros por data

```http
?timestamp__gte=2025-12-08T20:00:00Z&amp;timestamp__lte=2025-12-08T22:00:00Z
```

### Igualdade exata de timestamp

```http
?timestamp=2025-12-08T21:16:12Z
```

---

## ⚠️ Atenção (Campos Legados)

Campos antigos **não devem mais ser usados**:

❌ Antigo

✅ Atual

`project`

`project_id`

`request`

`request_id`

`timestamp` dentro de `data`

`timestamp` top-level

---

## 📈 Estatísticas do SDK

```python
stats = log_sender.get_stats()
```

Exemplo de retorno:

```json
{  "pending_logs": 3,  "running": true,  "config": {    "project_id": "...",    "upload_delay": 10,    "batch_size": 100,    "enable_async": true  }}
```

---

## 🧪 Ambientes Indicados

-   Backend services
-   Workers
-   APIs
-   Jobs batch
-   Scripts de automação
-   Aplicações Flask / FastAPI / Django

---

## 📌 Versão

```
0.1.6-dev
```

> Versão alinhada com LogCenter V2, filtros avançados e dashboard unificado.

---

## 🛣️ Roadmap (não implementado ainda)

-   Integração opcional com `structlog`
-   Buffer
-   Compressão de batches
-   SDK JS / Node.js