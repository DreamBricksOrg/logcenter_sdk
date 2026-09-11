# Sender/Spool 3-File Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-file, size-limited `FileSpool` with a 3-file model (`data_logs.jsonl` pending, `data_logs_backup.jsonl` delivered, `data_logs_corrupted.jsonl` malformed) and simplify `LogCenterSender` to a single try-HTTP-then-spool flow plus a background thread that retries pending items one at a time when `{base_url}/alive` returns 200.

**Architecture:** `spool.py` owns the 3 files and the line-by-line processing logic (`process_pending`, stops at first send failure). `sender.py` owns HTTP calls and orchestration (`send`/`send_sync` for immediate delivery, `process_pending_sync` + a background thread for retries). `client.py` gains a small `get_alive_sync` method. `config.py` drops fields the new model no longer needs (`spool_filename`, `spool_max_bytes`, `flush_batch_size`, `flush_threshold_count`).

**Tech Stack:** Python, `httpx` (existing), `threading` (existing), custom `check()`-based test script (`python/test_sdk.py`, no pytest in this repo).

**Spec:** `docs/superpowers/specs/2026-09-10-spool-refactor-design.md`

**Working directory for all commands below:** `C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk`

---

### Task 1: Simplify `LogCenterConfig`

**Files:**
- Modify: `python/logcenter_sdk/config.py`
- Test: `python/test_sdk.py` (`test_config`)

- [ ] **Step 1: Update `test_config` to check the new field set**

Replace the body of `test_config()` in `python/test_sdk.py`:

```python
def test_config() -> None:
    section("LogCenterConfig")

    cfg = LogCenterConfig(base_url="https://api.logcenter.io", project_id="proj-1")
    check("default timeout_s", cfg.timeout_s == 10.0)
    check("default flush_interval_s", cfg.flush_interval_s == 10.0)
    check("auto_flush default is False", cfg.auto_flush is False)
    check("no spool_max_bytes field", not hasattr(cfg, "spool_max_bytes"))
    check("no flush_threshold_count field", not hasattr(cfg, "flush_threshold_count"))
    check("no flush_batch_size field", not hasattr(cfg, "flush_batch_size"))
    check("no spool_filename field", not hasattr(cfg, "spool_filename"))

    env = {
        "LOGCENTER_BASE_URL": "https://env.logcenter.io",
        "LOGCENTER_PROJECT_ID": "proj-env",
        "LOGCENTER_API_KEY": "env-key",
        "LOGCENTER_AUTO_FLUSH": "true",
        "LOGCENTER_ENABLED": "1",
    }
    with patch.dict(os.environ, env, clear=False):
        cfg_env = LogCenterConfig.from_env()
    check("from_env base_url", cfg_env.base_url == "https://env.logcenter.io")
    check("from_env auto_flush", cfg_env.auto_flush is True)

    try:
        LogCenterConfig.from_env()
        check("from_env raises on missing fields", False)
    except ValueError:
        check("from_env raises on missing fields", True)
```

- [ ] **Step 2: Run it to see it fail**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && python - <<'PY'
import sys
sys.path.insert(0, "python")
from test_sdk import test_config
test_config()
PY
```

Expected: prints `[FAIL] no spool_max_bytes field`, `[FAIL] no flush_threshold_count field`, `[FAIL] no flush_batch_size field`, `[FAIL] no spool_filename field` (the fields still exist on the current dataclass).

- [ ] **Step 3: Rewrite `config.py`**

Replace the full contents of `python/logcenter_sdk/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os


@dataclass(frozen=True)
class LogCenterConfig:
    base_url: str
    project_id: str
    api_key: Optional[str] = None

    timeout_s: float = 10.0
    follow_redirects: bool = True

    # spool (offline queue) - always data_logs.jsonl / data_logs_backup.jsonl /
    # data_logs_corrupted.jsonl inside spool_dir, see spool.py
    spool_dir: Path = field(default_factory=lambda: Path(os.getenv("LOGCENTER_SPOOL_DIR", ".logcenter")))
    flush_interval_s: float = 10.0
    auto_flush: bool = False  # auto-start background flush thread on init

    enabled: bool = True

    @staticmethod
    def from_env(prefix: str = "LOGCENTER_") -> "LogCenterConfig":
        base_url = (os.getenv(f"{prefix}BASE_URL") or "").rstrip("/")
        project_id = os.getenv(f"{prefix}PROJECT_ID") or ""
        api_key = os.getenv(f"{prefix}API_KEY")

        timeout_s = float(os.getenv(f"{prefix}TIMEOUT_S", "10"))
        spool_dir = Path(os.getenv(f"{prefix}SPOOL_DIR", ".logcenter"))
        flush_interval_s = float(os.getenv(f"{prefix}FLUSH_INTERVAL_S", "10"))
        auto_flush = os.getenv(f"{prefix}AUTO_FLUSH", "false").lower() in ("1", "true", "yes", "y")
        enabled = os.getenv(f"{prefix}ENABLED", "true").lower() in ("1", "true", "yes", "y")

        if not base_url or not project_id:
            raise ValueError("Missing LOGCENTER_BASE_URL or LOGCENTER_PROJECT_ID")

        return LogCenterConfig(
            base_url=base_url,
            project_id=project_id,
            api_key=api_key,
            timeout_s=timeout_s,
            spool_dir=spool_dir,
            flush_interval_s=flush_interval_s,
            auto_flush=auto_flush,
            enabled=enabled,
        )
```

- [ ] **Step 4: Run it again to see it pass**

Run the same command as Step 2.
Expected: every line printed is `[PASS] ...`, no `[FAIL]`.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && git add python/logcenter_sdk/config.py python/test_sdk.py && git commit -m "$(cat <<'EOF'
refactor: drop obsolete spool sizing/threshold fields from LogCenterConfig

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q8P9Jx4YfG4mtiMdoCmmWF
EOF
)"
```

---

### Task 2: Rewrite `FileSpool` for the 3-file model

**Files:**
- Modify: `python/logcenter_sdk/spool.py`
- Test: `python/test_sdk.py` (`test_spool`)

- [ ] **Step 1: Replace `test_spool`**

```python
def test_spool(tmp_dir: Path) -> None:
    section("FileSpool")

    spool = FileSpool(tmp_dir)

    check("no pending initially", spool.has_pending() is False)
    check("pending_count is 0 initially", spool.pending_count() == 0)

    spool.append_main({"level": "INFO", "message": "msg1"})
    spool.append_main({"level": "WARN", "message": "msg2"})
    spool.append_main({"level": "ERROR", "message": "msg3"})
    check("has_pending after appends", spool.has_pending() is True)
    check("pending_count after 3 appends", spool.pending_count() == 3)

    spool.append_backup({"level": "INFO", "message": "delivered"})
    check("backup_count after append_backup", spool.backup_count() == 1)

    def send_all_ok(item: Dict[str, Any]) -> bool:
        return True

    result = spool.process_pending(send_all_ok)
    check("process_pending sent=3", result["sent"] == 3, str(result))
    check("process_pending corrupted=0", result["corrupted"] == 0)
    check("process_pending remaining=0", result["remaining"] == 0)
    check("pending_count is 0 after full success", spool.pending_count() == 0)
    check("backup_count has original + 3 sent", spool.backup_count() == 4)

    spool.append_main({"level": "INFO", "message": "will send"})
    spool.append_main({"level": "INFO", "message": "will fail"})
    spool.append_main({"level": "INFO", "message": "never attempted"})

    call_order: List[str] = []

    def send_second_fails(item: Dict[str, Any]) -> bool:
        call_order.append(item["message"])
        return item["message"] != "will fail"

    result2 = spool.process_pending(send_second_fails)
    check("stop-on-failure: sent=1", result2["sent"] == 1, str(result2))
    check("stop-on-failure: remaining=2", result2["remaining"] == 2)
    check("stop-on-failure: never attempted the third", call_order == ["will send", "will fail"])
    check("stop-on-failure: failed + untried stay pending", spool.pending_count() == 2)

    spool.main_path.write_text("not valid json\n", encoding="utf-8")
    result3 = spool.process_pending(send_all_ok)
    check("corrupted line: corrupted=1", result3["corrupted"] == 1, str(result3))
    check("corrupted line: sent=0", result3["sent"] == 0)
    check("corrupted line: pending_count is 0", spool.pending_count() == 0)
    check("corrupted line: corrupted_count is 1", spool.corrupted_count() == 1)

    errors: List[Exception] = []

    def writer():
        for i in range(20):
            try:
                spool.append_main({"n": i})
            except Exception as e:
                errors.append(e)

    def processor():
        for _ in range(10):
            try:
                spool.process_pending(send_all_ok)
                time.sleep(0.001)
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    threads += [threading.Thread(target=processor) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("no errors under concurrent access", len(errors) == 0,
          f"{len(errors)} errors" if errors else "")
```

- [ ] **Step 2: Run it to see it fail**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && python - <<'PY'
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "python")
tmp = Path(tempfile.mkdtemp())
from test_sdk import test_spool
test_spool(tmp)
PY
```

Expected: `TypeError: __init__() missing 2 required positional arguments: 'filename' and 'max_bytes'` (current `FileSpool` still takes the old 3-arg constructor).

- [ ] **Step 3: Rewrite `spool.py`**

Replace the full contents of `python/logcenter_sdk/spool.py`:

```python
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict


MAIN_FILENAME = "data_logs.jsonl"
BACKUP_FILENAME = "data_logs_backup.jsonl"
CORRUPTED_FILENAME = "data_logs_corrupted.jsonl"


class FileSpool:
    """
    data_logs.jsonl        - pendentes, aguardando envio
    data_logs_backup.jsonl - todo log entregue com sucesso (direto ou via retry)
    data_logs_corrupted.jsonl - linhas que nao deram para parsear como JSON

    Nenhum dos tres arquivos tem limite de tamanho.
    """

    def __init__(self, spool_dir: Path):
        self.spool_dir = spool_dir
        self.main_path = spool_dir / MAIN_FILENAME
        self.backup_path = spool_dir / BACKUP_FILENAME
        self.corrupted_path = spool_dir / CORRUPTED_FILENAME
        self._lock = threading.Lock()

        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.main_path.touch(exist_ok=True)
        self.backup_path.touch(exist_ok=True)
        self.corrupted_path.touch(exist_ok=True)

    def _append_line(self, path: Path, item: Dict[str, Any]) -> None:
        raw = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        with path.open("a", encoding="utf-8") as f:
            f.write(raw + "\n")

    def _count_lines(self, path: Path) -> int:
        try:
            with path.open("r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def append_main(self, item: Dict[str, Any]) -> None:
        with self._lock:
            self._append_line(self.main_path, item)

    def append_backup(self, item: Dict[str, Any]) -> None:
        with self._lock:
            self._append_line(self.backup_path, item)

    def has_pending(self) -> bool:
        try:
            return self.main_path.stat().st_size > 0
        except Exception:
            return False

    def pending_count(self) -> int:
        return self._count_lines(self.main_path)

    def backup_count(self) -> int:
        return self._count_lines(self.backup_path)

    def corrupted_count(self) -> int:
        return self._count_lines(self.corrupted_path)

    def process_pending(self, send_fn: Callable[[Dict[str, Any]], bool]) -> Dict[str, int]:
        """
        Processa data_logs.jsonl da linha mais antiga para a mais nova.
        - linha invalida (nao parseia como JSON) -> data_logs_corrupted.jsonl, segue.
        - send_fn(item) retorna True -> data_logs_backup.jsonl, segue.
        - send_fn(item) retorna False -> para o loop; essa linha e as seguintes
          permanecem em data_logs.jsonl, na mesma ordem, para a proxima tentativa.
        send_fn nao deve lancar excecao - deve capturar e retornar False.
        """
        with self._lock:
            try:
                lines = self.main_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                return {"sent": 0, "corrupted": 0, "remaining": 0}

            sent = 0
            corrupted = 0
            stop_index = len(lines)

            for i, line in enumerate(lines):
                if not line.strip():
                    continue

                try:
                    item = json.loads(line)
                except Exception:
                    self._append_line(self.corrupted_path, {"raw": line})
                    corrupted += 1
                    continue

                if send_fn(item):
                    self._append_line(self.backup_path, item)
                    sent += 1
                else:
                    stop_index = i
                    break

            remaining_lines = lines[stop_index:]
            if remaining_lines:
                self.main_path.write_text("\n".join(remaining_lines) + "\n", encoding="utf-8")
            else:
                self.main_path.write_text("", encoding="utf-8")

            return {"sent": sent, "corrupted": corrupted, "remaining": len(remaining_lines)}
```

- [ ] **Step 4: Run it again to see it pass**

Run the same command as Step 2.
Expected: every line printed is `[PASS] ...`, no `[FAIL]`, no traceback.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && git add python/logcenter_sdk/spool.py python/test_sdk.py && git commit -m "$(cat <<'EOF'
refactor: rewrite FileSpool as 3-file pending/backup/corrupted model

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q8P9Jx4YfG4mtiMdoCmmWF
EOF
)"
```

---

### Task 3: Sender direct send path (`send` / `send_sync`) + alive check on the HTTP client

**Files:**
- Modify: `python/logcenter_sdk/client.py`
- Modify: `python/logcenter_sdk/sender.py`
- Test: `python/test_sdk.py` (`make_config`, `test_send_sync`, `test_send_async`)

- [ ] **Step 1: Update `make_config` and replace `test_send_sync` / `test_send_async`**

In `python/test_sdk.py`, replace `make_config`:

```python
def make_config(tmp_dir: Path, **kwargs) -> LogCenterConfig:
    defaults = dict(
        base_url="http://localhost:9999",
        project_id="test-project",
        api_key="test-key",
        spool_dir=tmp_dir,
        flush_interval_s=60.0,
    )
    defaults.update(kwargs)
    return LogCenterConfig(**defaults)
```

Replace `test_send_sync`:

```python
def test_send_sync(tmp_dir: Path) -> None:
    section("send_sync() - sync immediate send")

    cfg = make_config(tmp_dir)
    sender = LogCenterSender(cfg)

    with patch.object(sender.http, "post_log_sync", return_value=make_ok_response()):
        result = sender.send_sync("INFO", "sync message")
    check("send_sync returns True on success", result is True)
    check("send_sync success goes to backup", sender.spool.backup_count() == 1)
    check("send_sync success does not spool to main", sender.spool.pending_count() == 0)

    with patch.object(sender.http, "post_log_sync", return_value=make_err_response()):
        result2 = sender.send_sync("ERROR", "sync fail")
    check("send_sync returns False on failure", result2 is False)
    check("send_sync failure spools to main", sender.spool.pending_count() == 1)

    with patch.object(sender.http, "post_log_sync", side_effect=Exception("boom")):
        result3 = sender.send_sync("WARN", "sync exception")
    check("send_sync handles exception gracefully", result3 is False)
    check("send_sync exception spools to main", sender.spool.pending_count() == 2)
```

Replace `test_send_async`:

```python
def test_send_async(tmp_dir: Path) -> None:
    section("send() - async immediate send")

    async def run():
        cfg = make_config(tmp_dir)
        sender = LogCenterSender(cfg)

        async def async_ok(payload):
            return make_ok_response()

        with patch.object(sender.http, "post_log", side_effect=async_ok):
            ok = await sender.send("INFO", "async message", request_id="req-123")
        check("send() returns True on success", ok is True)
        check("send() success goes to backup", sender.spool.backup_count() == 1)

        async def async_fail(payload):
            return make_err_response()

        with patch.object(sender.http, "post_log", side_effect=async_fail):
            ok2 = await sender.send("CRITICAL", "async failure")
        check("send() returns False on failure", ok2 is False)
        check("send() failure spools to main", sender.spool.pending_count() == 1)

        async def async_exc(payload):
            raise ConnectionError("refused")

        with patch.object(sender.http, "post_log", side_effect=async_exc):
            ok3 = await sender.send("WARN", "connection error")
        check("send() handles exception gracefully", ok3 is False)
        check("send() exception spools to main", sender.spool.pending_count() == 2)

    asyncio.run(run())
```

- [ ] **Step 2: Run both to see them fail**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && python - <<'PY'
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "python")
tmp = Path(tempfile.mkdtemp())
from test_sdk import test_send_sync, test_send_async
test_send_sync(tmp / "sync")
test_send_async(tmp / "async")
PY
```

Expected: `AttributeError: 'LogCenterConfig' object has no attribute 'spool_filename'` (current `LogCenterSender.__init__` still builds `FileSpool(config.spool_dir, config.spool_filename, config.spool_max_bytes)`, and `config` no longer has those fields after Task 1).

- [ ] **Step 3: Add `get_alive_sync` to `client.py`**

In `python/logcenter_sdk/client.py`, add this method to `LogCenterHttpClient`, after `post_log_sync`:

```python
    def get_alive_sync(self) -> httpx.Response:
        url = f"{self.base_url}/alive"
        with httpx.Client(timeout=self.timeout, follow_redirects=self.follow_redirects) as client:
            return client.get(url, headers=self.headers())
```

- [ ] **Step 4: Rewrite `sender.py`**

Replace the full contents of `python/logcenter_sdk/sender.py`:

```python
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import LogCenterConfig
from .client import LogCenterHttpClient
from .spool import FileSpool


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LogCenterSender:
    """
    - send() / send_sync(): tenta HTTP direto. Sucesso -> data_logs_backup.jsonl.
      Qualquer erro (rede, config, status nao-2xx) -> data_logs.jsonl.
    - background thread: a cada flush_interval_s, se houver pendentes e
      {base_url}/alive responder 200, reprocessa data_logs.jsonl um item por vez
      (spool.py para no primeiro erro de envio).
    """

    def __init__(self, config: LogCenterConfig):
        self.cfg = config
        self.http = LogCenterHttpClient(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_s=config.timeout_s,
            follow_redirects=config.follow_redirects,
        )
        self.spool = FileSpool(config.spool_dir)

        self._bg_thread: Optional[threading.Thread] = None
        self._thread_stop_event: Optional[threading.Event] = None
        self._thread_wake_event: Optional[threading.Event] = None

        if self.cfg.auto_flush:
            self.start_background_flush_thread()

    def _build_payload(
        self,
        level: str,
        message: str,
        *,
        timestamp: Optional[str] = None,
        tags: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        lvl = (level or "INFO").upper()
        ts = timestamp or _utc_iso()
        if status is None:
            status = "ERROR" if lvl in ("ERROR", "CRITICAL", "FATAL") else "OK"

        payload: Dict[str, Any] = {
            "project_id": project_id or self.cfg.project_id,
            "level": lvl,
            "message": message,
            "timestamp": ts,
            "status": status,
        }
        if tags:
            payload["tags"] = tags
        if data:
            payload["data"] = data
        if request_id:
            payload["request_id"] = request_id
        return payload

    async def send(
        self,
        level: str,
        message: str,
        *,
        timestamp: Optional[str] = None,
        tags: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> bool:
        if not self.cfg.enabled:
            return False

        payload = self._build_payload(
            level, message, timestamp=timestamp, tags=tags, data=data,
            request_id=request_id, status=status, project_id=project_id,
        )

        try:
            resp = await self.http.post_log(payload)
            ok = 200 <= resp.status_code < 300
        except Exception:
            ok = False

        if ok:
            self.spool.append_backup(payload)
            return True

        self.spool.append_main(payload)
        return False

    def send_sync(
        self,
        level: str,
        message: str,
        *,
        timestamp: Optional[str] = None,
        tags: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> bool:
        if not self.cfg.enabled:
            return False

        payload = self._build_payload(
            level, message, timestamp=timestamp, tags=tags, data=data,
            request_id=request_id, status=status, project_id=project_id,
        )

        try:
            resp = self.http.post_log_sync(payload)
            ok = 200 <= resp.status_code < 300
        except Exception:
            ok = False

        if ok:
            self.spool.append_backup(payload)
            return True

        self.spool.append_main(payload)
        return False

    def _is_alive(self) -> bool:
        try:
            resp = self.http.get_alive_sync()
            return resp.status_code == 200
        except Exception:
            return False

    def _post_log_bool(self, payload: Dict[str, Any]) -> bool:
        try:
            resp = self.http.post_log_sync(payload)
            return 200 <= resp.status_code < 300
        except Exception:
            return False

    def process_pending_sync(self) -> Dict[str, int]:
        if not self.spool.has_pending():
            return {"sent": 0, "corrupted": 0, "remaining": 0}
        if not self._is_alive():
            return {"sent": 0, "corrupted": 0, "remaining": self.spool.pending_count()}
        return self.spool.process_pending(self._post_log_bool)

    def start_background_flush_thread(self) -> None:
        """Start a daemon thread that periodically retries the pending spool."""
        if self._bg_thread and self._bg_thread.is_alive():
            return
        self._thread_stop_event = threading.Event()
        self._thread_wake_event = threading.Event()
        self._bg_thread = threading.Thread(target=self._thread_flush_loop, daemon=True)
        self._bg_thread.start()

    def stop_background_flush_thread(self, timeout: float = 5.0) -> None:
        if not self._bg_thread:
            return
        if self._thread_stop_event:
            self._thread_stop_event.set()
        if self._thread_wake_event:
            self._thread_wake_event.set()
        self._bg_thread.join(timeout=timeout)
        self._bg_thread = None

    def _thread_flush_loop(self) -> None:
        while not self._thread_stop_event.is_set():
            self.process_pending_sync()
            self._thread_wake_event.wait(timeout=self.cfg.flush_interval_s)
            self._thread_wake_event.clear()
```

Note: `send_sync` now calls `http.post_log_sync` directly instead of wrapping the async `send()` through `asyncio.run` — simpler and avoids event-loop edge cases; behavior for callers is unchanged (still returns `bool`, still spools on failure).

- [ ] **Step 5: Run the tests again to see them pass**

Run the same command as Step 2.
Expected: every line printed is `[PASS] ...`, no `[FAIL]`, no traceback.

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && git add python/logcenter_sdk/client.py python/logcenter_sdk/sender.py python/test_sdk.py && git commit -m "$(cat <<'EOF'
refactor: single try-http-then-spool flow for send()/send_sync(), add alive check

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q8P9Jx4YfG4mtiMdoCmmWF
EOF
)"
```

---

### Task 4: Background retry (`process_pending_sync` + background thread tests)

**Files:**
- Test: `python/test_sdk.py` (new `test_process_pending_sync`, rewritten `test_background_flush_thread`)

`sender.py` already has `process_pending_sync`, `start_background_flush_thread`, `stop_background_flush_thread` from Task 3 — this task is test-only, verifying that logic end-to-end.

- [ ] **Step 1: Add `test_process_pending_sync` and replace `test_background_flush_thread`**

Add this new function to `python/test_sdk.py`, right after `test_send_async`:

```python
def test_process_pending_sync(tmp_dir: Path) -> None:
    section("process_pending_sync() - background retry")

    cfg = make_config(tmp_dir)
    sender = LogCenterSender(cfg)

    result = sender.process_pending_sync()
    check("no-op when nothing pending", result == {"sent": 0, "corrupted": 0, "remaining": 0})

    with patch.object(sender.http, "post_log_sync", return_value=make_err_response()):
        sender.send_sync("INFO", "queued 1")
        sender.send_sync("INFO", "queued 2")
    check("2 messages pending after failed sends", sender.spool.pending_count() == 2)

    with patch.object(sender.http, "get_alive_sync", return_value=make_err_response()):
        result2 = sender.process_pending_sync()
    check("not alive: nothing processed", result2["sent"] == 0)
    check("not alive: remaining still 2", result2["remaining"] == 2)

    with patch.object(sender.http, "get_alive_sync", return_value=make_ok_response()), \
         patch.object(sender.http, "post_log_sync", return_value=make_ok_response()):
        result3 = sender.process_pending_sync()
    check("alive: both messages sent", result3["sent"] == 2, str(result3))
    check("alive: nothing pending after", sender.spool.pending_count() == 0)
    check("alive: backup has both", sender.spool.backup_count() == 2)
```

Replace `test_background_flush_thread`:

```python
def test_background_flush_thread(tmp_dir: Path) -> None:
    section("start/stop_background_flush_thread()")

    cfg = make_config(tmp_dir, flush_interval_s=0.1)
    sender = LogCenterSender(cfg)

    call_count: List[int] = []

    def counting_process():
        call_count.append(1)
        return {"sent": 0, "corrupted": 0, "remaining": 0}

    with patch.object(sender, "process_pending_sync", side_effect=counting_process):
        sender.start_background_flush_thread()
        check("thread is alive after start",
              sender._bg_thread is not None and sender._bg_thread.is_alive())

        sender.start_background_flush_thread()  # no-op

        time.sleep(0.4)
        sender.stop_background_flush_thread(timeout=2.0)

    check("background thread stopped",
          sender._bg_thread is None or not sender._bg_thread.is_alive())
    check("process_pending_sync was called by background thread", len(call_count) >= 2,
          f"called {len(call_count)} times")
```

- [ ] **Step 2: Run them**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && python - <<'PY'
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "python")
tmp = Path(tempfile.mkdtemp())
from test_sdk import test_process_pending_sync, test_background_flush_thread
test_process_pending_sync(tmp / "pending")
test_background_flush_thread(tmp / "bg")
PY
```

Expected: every line printed is `[PASS] ...`, no `[FAIL]` (this task is test-only since Task 3 already implemented the code these tests exercise; this is a verification step, not red/green).

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && git add python/test_sdk.py && git commit -m "$(cat <<'EOF'
test: cover process_pending_sync and rewritten background flush thread

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q8P9Jx4YfG4mtiMdoCmmWF
EOF
)"
```

---

### Task 5: Remove obsolete tests, update docstring and test registry

**Files:**
- Modify: `python/test_sdk.py`

- [ ] **Step 1: Delete obsolete test functions**

Delete these functions entirely from `python/test_sdk.py` (they exercise APIs removed in Tasks 1-3: `send_spool`, `flush_spool_sync`, `flush_spool`, `flush_threshold_count`):
- `test_send_spool`
- `test_flush_spool_sync`
- `test_flush_spool_async`
- `test_flush_threshold`
- `test_live_spool_and_flush`
- `test_live_background_flush`
- `test_live_threshold_flush`

- [ ] **Step 2: Update `live_config`**

Replace `live_config`:

```python
def live_config(tmp_dir: Path, live: Dict[str, str], **kwargs) -> LogCenterConfig:
    defaults: Dict[str, Any] = dict(
        base_url=live["url"],
        project_id=live["project_id"],
        api_key=live.get("api_key"),
        spool_dir=tmp_dir,
        flush_interval_s=5.0,
    )
    defaults.update(kwargs)
    return LogCenterConfig(**defaults)
```

- [ ] **Step 3: Update the module docstring**

Replace lines 1-31 of `python/test_sdk.py` (the module docstring):

```python
"""
LogCenter SDK - Test Script

Covers (mocked, always run):
  - LogCenterConfig (code and env-var based)
  - FileSpool (append_main, append_backup, has_pending, pending_count,
    process_pending: success, stop-on-failure, corrupted line, thread safety)
  - LogCenterSender.send_sync()            - sync immediate send (spools on failure)
  - LogCenterSender.send()                 - async immediate send (spools on failure)
  - LogCenterSender.process_pending_sync() - alive check + one-by-one retry
  - start/stop_background_flush_thread()
  - auto_flush config flag

Live tests (run only when LogCenter credentials are supplied):
  - send_sync() against real API
  - send() async against real API

Usage:
  # Mocked tests only
  python test_sdk.py

  # With a real LogCenter instance (reads .env if present)
  python test_sdk.py --url https://my.logcenter.io --project-id myproj --api-key mykey

  # Or set env vars and run without flags
  LOGCENTER_BASE_URL=... LOGCENTER_PROJECT_ID=... python test_sdk.py
"""
```

- [ ] **Step 4: Update the test registries in `main()`**

Replace the `mocked_tests` and `live_tests` lists inside `main()`:

```python
        mocked_tests = [
            ("Config",                  lambda: test_config()),
            ("FileSpool",               lambda: test_spool(tmp / "spool")),
            ("send_sync",               lambda: test_send_sync(tmp / "send_sync")),
            ("send (async)",            lambda: test_send_async(tmp / "send_async")),
            ("process_pending_sync",    lambda: test_process_pending_sync(tmp / "process_pending")),
            ("background_flush_thread", lambda: test_background_flush_thread(tmp / "bg")),
            ("auto_flush config",       lambda: test_auto_flush_config(tmp / "auto")),
        ]

        live_tests = [
            ("live: send_sync",  lambda: test_live_send_sync(tmp / "live1", live)),
            ("live: send async", lambda: test_live_send_async(tmp / "live2", live)),
        ]
```

- [ ] **Step 5: Run the full mocked suite**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && python python/test_sdk.py
```

Expected: `Results: N/N passed - all tests passed!` (no `FAILED` section, no `[EXCEPTION]` block).

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && git add python/test_sdk.py && git commit -m "$(cat <<'EOF'
test: remove obsolete spool/flush-threshold tests, update docstring and registry

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q8P9Jx4YfG4mtiMdoCmmWF
EOF
)"
```

---

### Task 6: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full mocked suite one more time from a clean process**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && python python/test_sdk.py
```

Expected: `Results: N/N passed - all tests passed!`

- [ ] **Step 2: Grep the codebase for any leftover references to removed APIs**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && grep -rn "pop_batch\|send_spool\|flush_spool\|spool_max_bytes\|flush_threshold_count\|flush_batch_size\|spool_filename\|SpoolStats" python/ || echo "none found"
```

Expected: `none found`.

- [ ] **Step 3: If both checks pass, no further commit is needed** — Task 5's commit already reflects the final state.

---

### Task 7 (added during execution): Update `python/README.md` to match the new behavior

**Why:** Discovered during Task 6's grep — `python/README.md` documents `flush_spool()`, `start_background_flush()`/`stop_background_flush()` (async, no-arg), and a `spool_on_fail=True` per-call opt-in, all removed in Tasks 1-3. It also claims spooling is opt-in and failures are silent by default, which is now backwards: `send()`/`send_sync()` always spool to `data_logs.jsonl` on any failure, unconditionally. This was flagged by the Task 3 and Task 5 code-quality reviewers as a real gap, explicitly deferred to "the end of the refactor" — this is that point.

**Files:**
- Modify: `python/README.md`

- [ ] **Step 1: Update the top warning banner** (currently line 5) to reflect that spooling is now automatic/unconditional on failure, not opt-in.
- [ ] **Step 2: Remove the "Spool opcional em arquivo (desativável por chamada)" bullet** from the features list (currently line 17) — there is no per-call opt-out anymore.
- [ ] **Step 3: Rewrite the "🔁 Spool (fila offline)" section** (currently lines 128-164) to describe the real current behavior: `send()`/`send_sync()` try HTTP first; on ANY failure the payload is appended to `data_logs.jsonl` inside `spool_dir` automatically (no `spool_on_fail` parameter exists). On success, the payload is appended to `data_logs_backup.jsonl`. A background thread (`start_background_flush_thread()` / `stop_background_flush_thread()`, or automatically if `LogCenterConfig(auto_flush=True)`) periodically checks `{base_url}/alive` and, if it responds 200, retries pending items one at a time via `process_pending_sync()`, stopping at the first failure; malformed lines go to `data_logs_corrupted.jsonl`. Remove all references to `flush_spool()`, `start_background_flush()`/`stop_background_flush()` (the async no-arg pair), and `spool_on_fail`.
- [ ] **Step 4: Update the middleware section's "NÃO exige spool" bullet** (currently line 188) since spooling on failure is now unconditional, not something that can be disabled — rephrase to state that failed audit logs are automatically spooled like any other `send()` call.
- [ ] **Step 5: Verify no stale references remain**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && grep -n "flush_spool\|start_background_flush(\|stop_background_flush(\|spool_on_fail" python/README.md || echo "none found"
```

Expected: `none found` (the async no-arg `start_background_flush()`/`stop_background_flush()` must be gone; the new `start_background_flush_thread()`/`stop_background_flush_thread()` names are fine to keep/add).

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/db/Documents/db/prj/dreambricks/logcenter_sdk" && git add python/README.md && git commit -m "$(cat <<'EOF'
docs: update README to match the 3-file spool and always-spool-on-failure behavior

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q8P9Jx4YfG4mtiMdoCmmWF
EOF
)"
```
