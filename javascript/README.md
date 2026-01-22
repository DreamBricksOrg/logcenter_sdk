# LogCenter SDK (Node.js)

SDK oficial para envio de logs ao **LogCenter**, pronto para **ESM + CJS**, com foco em **resiliência, padronização e observabilidade**.

## Principais recursos

* Envio de logs via `POST /logs/` (**com `/` no final** para evitar `307`)
* **Spool offline** em arquivo `.jsonl` (controlado por chamada com `spoolOnFail`)
* `flushSpool()` manual e `startBackgroundFlush()` automático
* Middleware de auditoria para **Express**
* Exemplos prontos: **Express**, **Next.js (App Router – Route Handler)** e **Worker**

---

## Instalação

```bash
npm i logcenter-sdk
```

---

## Contrato enviado (compatível com LogCreate)

```json
{
  "project_id": "ObjectId",
  "status": "OK | ERROR | ...",
  "level": "INFO | WARN | ERROR | ...",
  "message": "string",
  "timestamp": "ISO-8601 (Z)",
  "tags": ["string"],
  "data": { "any": "value" },
  "request_id": "string | null"
}
```

### Regras importantes

* `timestamp` é **top-level**
* Se `status` não for informado, o SDK define automaticamente:

  * `OK` para níveis não críticos
  * `ERROR` para `ERROR | CRITICAL | FATAL`
* Campos extras são ignorados pela API

---

## Uso básico

```ts
import { LogCenterConfig, LogCenterSender } from "logcenter-sdk";

const cfg = new LogCenterConfig({
  baseUrl: process.env.LOG_API!,           // ex: https://logcenter.suaempresa.com
  projectId: process.env.LOG_PROJECT_ID!,  // ObjectId (hex)
  apiKey: process.env.LOG_API_KEY,         // opcional
  enabled: true,
});

const sender = new LogCenterSender(cfg);

await sender.send("INFO", "App startup", {
  tags: ["startup"],
  data: {
    env: process.env.NODE_ENV,
    version: "0.1.0-dev.0",
  },
  spoolOnFail: false, // desativa fila offline para este envio
});
```

---

## Configuração via variáveis de ambiente (opcional)

```bash
export LOGCENTER_BASE_URL="https://logcenter.suaempresa.com"
export LOGCENTER_PROJECT_ID="69374094b758aa497f59cf1b"
export LOGCENTER_API_KEY="..."
```

```ts
import { LogCenterConfig, LogCenterSender } from "logcenter-sdk";

const cfg = LogCenterConfig.fromEnv("LOGCENTER_");
const sender = new LogCenterSender(cfg);
```

---

## Spool offline (fila em arquivo)

Por padrão, se um `send()` falhar, o SDK grava o payload no spool local:

```
.logcenter/spool.jsonl
```

Controle por chamada:

* `spoolOnFail: true` (default) → salva no arquivo se falhar
* `spoolOnFail: false` → não salva

### Flush manual

```ts
const res = await sender.flushSpool(10);
console.log(res); // { sent, failed, remaining }
```

### Flush em background

```ts
sender.startBackgroundFlush();

// no shutdown
await sender.stopBackgroundFlush();
```

---

## Middleware de auditoria (Express)

Registra automaticamente:

* `HTTP 5xx response`
* `Unhandled exception in request`

```ts
import express from "express";
import { LogCenterConfig, LogCenterSender } from "logcenter-sdk";
import { logcenterAuditMiddleware } from "logcenter-sdk/express";

const sender = new LogCenterSender(
  new LogCenterConfig({
    baseUrl: process.env.LOG_API!,
    projectId: process.env.LOG_PROJECT_ID!,
    apiKey: process.env.LOG_API_KEY,
  })
);

const app = express();
app.use(logcenterAuditMiddleware(sender));

app.get("/health", (_req, res) => res.json({ ok: true }));
app.listen(3000);
```

---

## Exemplos incluídos

* `examples/express/server.ts`
* `examples/nextjs-app-router/route.ts`
* `examples/worker/worker.ts`

---

## Build e publicação

```bash
npm run build
npm login
npm publish --access public
```

> ⚠️ Qualquer alteração exige **bump de versão** (ex: `0.1.0-dev.1`).

---

## Estrutura pública

```text
src/
├── index.ts
├── config.ts
├── sender.ts
├── spool.ts
└── express.ts
```

```ts
// src/index.ts
export { LogCenterConfig } from "./config.js";
export { LogCenterSender } from "./sender.js";
```

---

## Licença

MIT — veja o arquivo `LICENSE`.
