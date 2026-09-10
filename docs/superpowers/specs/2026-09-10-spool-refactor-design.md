# Refactor: sender/spool para 3 arquivos JSONL

Status: aprovado para plano de implementação
Data: 2026-09-10

## Objetivo

Substituir o `FileSpool` atual (1 arquivo, append + pop_batch + trim por tamanho) por um
modelo de 3 arquivos que dá visibilidade total do que foi entregue, o que está pendente,
e o que está corrompido — sem descarte silencioso de logs.

## Arquivos (em `config.spool_dir`)

- `data_logs.jsonl` — fila de pendentes. Uma linha sai daqui só quando é enviada com
  sucesso (vai para o backup) ou quando é corrompida/mal formada (vai para o corrupted).
  Sem limite de tamanho — nunca descarta uma linha só por espaço.
- `data_logs_backup.jsonl` — histórico de todo log entregue com sucesso, seja no envio
  direto (`send`/`send_sync`) ou no reenvio da fila (`process_pending`). Append-only,
  sem limite de tamanho.
- `data_logs_corrupted.jsonl` — linhas que não deram para parsear como JSON durante o
  processamento da fila. Append-only, sem limite de tamanho.

## Componentes

### `spool.py`

Reformula `FileSpool` para expor:

- `append_main(item: dict) -> None` — serializa e grava uma linha em `data_logs.jsonl`
  (sob lock).
- `append_backup(item: dict) -> None` — grava uma linha (já serializada ou dict) em
  `data_logs_backup.jsonl` (sob lock).
- `has_pending() -> bool` — `data_logs.jsonl` tem ao menos uma linha?
- `process_pending(send_fn: Callable[[dict], bool]) -> dict` — lê todas as linhas de
  `data_logs.jsonl`. Para cada linha, na ordem (mais antiga primeiro):
  1. Tenta `json.loads`. Falhou → grava a linha crua em `data_logs_corrupted.jsonl`,
     remove da fila principal, continua para a próxima linha.
  2. Parseou → chama `send_fn(item)`.
     - Retornou sucesso → grava em `data_logs_backup.jsonl`, remove da fila, continua.
     - Retornou falha → **para o loop** (essa linha e todas as seguintes permanecem em
       `data_logs.jsonl` intactas, na mesma ordem, para a próxima tentativa).
  3. Reescreve `data_logs.jsonl` uma única vez no final com o que sobrou.
  - Retorna um resumo: `{"sent": int, "corrupted": int, "remaining": int}`.
- Lock único (`threading.Lock`) protegendo `append_main`, `append_backup` e
  `process_pending`, para chamadas de log concorrentes com o flush em background não
  corromperem os arquivos.

Removido: `pop_batch`, `_trim_to_fit`, `max_bytes`, `SpoolStats` (ou simplificado — ver
plano de implementação).

### `sender.py`

- `send()` (async) / `send_sync()` (sync): fluxo único.
  1. Tenta HTTP direto (`self.http.post_log` / `post_log_sync`).
  2. Sucesso (2xx) → grava a mesma linha em `data_logs_backup.jsonl`
     (`spool.append_backup`) → retorna sucesso.
  3. Qualquer erro (exceção de rede/timeout/DNS, erro de configuração como api_key ou
     project_id ausente, base_url inválida, ou status não-2xx) → grava em
     `data_logs.jsonl` (`spool.append_main`) → retorna falha.
- Removido `send_spool()` (modo "store-only") — o fluxo único acima já cobre o caso de
  uso.
- Thread de fundo (reaproveita `start_background_flush_thread` /
  `stop_background_flush_thread`): a cada `flush_interval_s`:
  1. Se `spool.has_pending()` é falso, não faz nada nesse ciclo.
  2. Senão, faz `GET f"{config.base_url}/alive"` (timeout curto). Status 200 → chama
     `spool.process_pending(self.http.post_log_sync)`. Qualquer outro status ou exceção
     → não processa, tenta de novo no próximo ciclo.
- Removido: `flush_threshold_count`, `_trigger_threshold_flush`, `flush_spool`,
  `flush_spool_sync` (nomes antigos somem — a lógica migra para o loop acima),
  `start_background_flush`/`_bg_loop` (variante asyncio, não usada pelo novo fluxo).

### `config.py`

- Remove `spool_max_bytes`, `flush_batch_size`, `flush_threshold_count` (não fazem mais
  sentido no novo modelo).
- Mantém `spool_dir`, `flush_interval_s`, `auto_flush`.
- Novos nomes de arquivo fixos (`data_logs.jsonl`, `data_logs_backup.jsonl`,
  `data_logs_corrupted.jsonl`) — não precisam ser configuráveis (spec não pediu).

### `middleware.py`

Sem mudança de interface — continua chamando `sender.send(...)`.

## Fluxo de dados

```
log() chamado
   │
   ├─ tenta HTTP direto
   │     ├─ sucesso ─────────────► append_backup(item)
   │     └─ qualquer erro ───────► append_main(item)   [fica em data_logs.jsonl]
   │
Thread de fundo (a cada flush_interval_s)
   │
   ├─ has_pending? não ──► nada
   └─ has_pending? sim
         ├─ GET {base_url}/alive == 200?
         │     não ──► nada, tenta próximo ciclo
         │     sim ──► process_pending():
         │              linha por linha (mais antiga primeiro):
         │                json inválido ──► data_logs_corrupted.jsonl
         │                envio ok ────────► data_logs_backup.jsonl
         │                envio falhou ────► PARA (essa + resto ficam em data_logs.jsonl)
```

## Testes

`test_sdk.py` é reescrito para as novas responsabilidades:

- Spool: `append_main`, `append_backup`, `has_pending`, `process_pending` (sucesso,
  falha no meio, linha corrompida, fila vazia, thread-safety com lock).
- Sender: `send`/`send_sync` (sucesso grava backup, falha grava main, exceção de config
  grava main), thread de fundo (alive 200 processa, alive != 200 não processa, sem
  pendentes não faz GET).

## Fora de escopo

- Rotação/compactação de `data_logs_backup.jsonl` e `data_logs_corrupted.jsonl` (ficam
  sem limite; se crescer demais no futuro, é outra tarefa).
- Suporte a múltiplos processos escrevendo no mesmo spool (lock continua sendo só
  intra-processo, igual hoje).
- Nomes de arquivo configuráveis.
