"""
LogCenter SDK - Test Script

Covers (mocked, always run):
  - LogCenterConfig (code and env-var based)
  - FileSpool (append, count, pop_batch, trim, thread safety)
  - LogCenterSender.send_spool()       - store without sending
  - LogCenterSender.flush_spool_sync() - sync flush
  - LogCenterSender.flush_spool()      - async flush
  - LogCenterSender.send_sync()        - sync immediate send
  - LogCenterSender.send()             - async immediate send
  - flush_threshold_count auto-flush trigger
  - start/stop_background_flush_thread()
  - auto_flush config flag

Live tests (run only when LogCenter credentials are supplied):
  - send_sync() against real API
  - send() async against real API
  - send_spool() + flush_spool_sync() against real API
  - send_spool() + background flush thread against real API

Usage:
  # Mocked tests only
  python test_sdk.py

  # With a real LogCenter instance (reads .env if present)
  python test_sdk.py --url https://my.logcenter.io --project-id myproj --api-key mykey

  # Or set env vars and run without flags
  LOGCENTER_BASE_URL=... LOGCENTER_PROJECT_ID=... python test_sdk.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent))

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from logcenter_sdk import LogCenterConfig, LogCenterSender
from logcenter_sdk.spool import FileSpool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results: List[tuple] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    suffix = f" - {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    results.append((name, condition, detail))


def skip(name: str, reason: str = "") -> None:
    suffix = f" - {reason}" if reason else ""
    print(f"  [{SKIP}] {name}{suffix}")


def section(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


def make_config(tmp_dir: Path, **kwargs) -> LogCenterConfig:
    defaults = dict(
        base_url="http://localhost:9999",
        project_id="test-project",
        api_key="test-key",
        spool_dir=tmp_dir,
        spool_filename="test_spool.jsonl",
        flush_interval_s=60.0,
    )
    defaults.update(kwargs)
    return LogCenterConfig(**defaults)


def make_ok_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    return resp


def make_err_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 500
    return resp


# ---------------------------------------------------------------------------
# Mocked tests
# ---------------------------------------------------------------------------

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

    # send_fn raising an exception must behave exactly like send_fn returning
    # False: current item stops the loop, stays pending, later items untried.
    spool.append_main({"level": "INFO", "message": "will send"})
    spool.append_main({"level": "INFO", "message": "will raise"})
    spool.append_main({"level": "INFO", "message": "never attempted 2"})

    raise_call_order: List[str] = []

    def send_second_raises(item: Dict[str, Any]) -> bool:
        raise_call_order.append(item["message"])
        if item["message"] == "will raise":
            raise RuntimeError("send_fn misbehaving")
        return True

    result4 = spool.process_pending(send_second_raises)
    check("send_fn exception: sent=1", result4["sent"] == 1, str(result4))
    check("send_fn exception: remaining=2", result4["remaining"] == 2)
    check("send_fn exception: never attempted the third",
          raise_call_order == ["will send", "will raise"])
    check("send_fn exception: failed + untried stay pending", spool.pending_count() == 2)

    # Clear the two still-pending items from the exception test above so they
    # don't interfere with the concurrency invariant counted below.
    spool.main_path.write_text("", encoding="utf-8")

    errors: List[Exception] = []

    NUM_WRITER_THREADS = 4
    ITEMS_PER_WRITER = 20

    def writer():
        for i in range(ITEMS_PER_WRITER):
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

    # backup_before captures whatever is already in the backup file at this
    # point (dynamically, so it stays correct regardless of what earlier
    # sub-tests in this function put there) - a broken lock would corrupt
    # this count via lost or duplicated lines even without raising errors.
    backup_before = spool.backup_count()

    threads = [threading.Thread(target=writer) for _ in range(NUM_WRITER_THREADS)]
    threads += [threading.Thread(target=processor) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("no errors under concurrent access", len(errors) == 0,
          f"{len(errors)} errors" if errors else "")

    # The processor threads may not have drained everything before joining
    # (process_pending is called a fixed number of times, not until empty).
    # Drain whatever is left with a final full-success pass, then verify the
    # invariant: every item the writers appended ended up in backup exactly
    # once - no lost or duplicated lines from a broken lock.
    final_drain = spool.process_pending(send_all_ok)
    expected_total_sent = NUM_WRITER_THREADS * ITEMS_PER_WRITER
    check("concurrency invariant: pending_count is 0 after final drain",
          spool.pending_count() == 0)
    check("concurrency invariant: backup_count matches items appended by writers",
          spool.backup_count() - backup_before == expected_total_sent,
          f"backup_count={spool.backup_count()} backup_before={backup_before} "
          f"expected_total_sent={expected_total_sent} final_drain={final_drain}")

    # -- Boundary conditions -------------------------------------------

    def send_all_fail(item: Dict[str, Any]) -> bool:
        return False

    # 1. Immediate first-item failure: nothing should be sent, nothing about
    #    main_path's content should change.
    spool.append_main({"n": "first"})
    spool.append_main({"n": "second"})
    spool.append_main({"n": "third"})
    original_main_content = spool.main_path.read_text(encoding="utf-8")

    result_first_fail = spool.process_pending(send_all_fail)
    check("boundary: immediate failure sent=0", result_first_fail["sent"] == 0,
          str(result_first_fail))
    check("boundary: immediate failure remaining=3", result_first_fail["remaining"] == 3)
    check("boundary: immediate failure leaves main_path unchanged",
          spool.main_path.read_text(encoding="utf-8") == original_main_content)

    spool.main_path.write_text("", encoding="utf-8")

    # 2. Multiple corrupted lines in one pass.
    corrupted_before = spool.corrupted_count()
    spool.main_path.write_text(
        "not valid json 1\n"
        "not valid json 2\n"
        + json.dumps({"n": "valid"}) + "\n",
        encoding="utf-8",
    )
    result_multi_corrupt = spool.process_pending(send_all_ok)
    check("boundary: multiple corrupted lines corrupted=2",
          result_multi_corrupt["corrupted"] == 2, str(result_multi_corrupt))
    check("boundary: multiple corrupted lines sent=1", result_multi_corrupt["sent"] == 1)
    check("boundary: corrupted_count reflects both lines",
          spool.corrupted_count() - corrupted_before == 2)
    check("boundary: multiple corrupted lines pending_count=0", spool.pending_count() == 0)

    # 3. Blank line interleaved between two valid JSON lines.
    spool.main_path.write_text(
        json.dumps({"n": "a"}) + "\n"
        "\n"
        + json.dumps({"n": "b"}) + "\n",
        encoding="utf-8",
    )
    corrupted_before_blank = spool.corrupted_count()
    result_blank = spool.process_pending(send_all_ok)
    check("boundary: blank line does not error, sent=2", result_blank["sent"] == 2,
          str(result_blank))
    check("boundary: blank line not counted as corrupted",
          spool.corrupted_count() == corrupted_before_blank)

    # 4. process_pending on a genuinely empty main file.
    empty_spool = FileSpool(tmp_dir / "empty")
    result_empty = empty_spool.process_pending(send_all_ok)
    check("boundary: empty file returns sent=0/corrupted=0/remaining=0",
          result_empty == {"sent": 0, "corrupted": 0, "remaining": 0},
          str(result_empty))


def test_send_spool(tmp_dir: Path) -> None:
    section("send_spool() - store without network")

    cfg = make_config(tmp_dir)
    sender = LogCenterSender(cfg)

    sender.send_spool("INFO", "stored message 1", tags=["tag1"])
    sender.send_spool("ERROR", "stored message 2", data={"key": "val"})
    count = sender.spool.count()
    check("send_spool stores to spool", count == 2, f"count={count}")

    items, _ = sender.spool.pop_batch(10)
    check("stored payload has correct level", items[0]["level"] == "INFO")
    check("stored payload has correct status", items[0]["status"] == "OK")
    check("stored payload has tags", items[0].get("tags") == ["tag1"])
    check("ERROR level infers ERROR status", items[1]["status"] == "ERROR")
    check("stored payload has data", items[1].get("data") == {"key": "val"})

    cfg_disabled = make_config(tmp_dir, enabled=False, spool_filename="disabled.jsonl")
    sender_off = LogCenterSender(cfg_disabled)
    result = sender_off.send_spool("INFO", "should not store")
    check("send_spool returns False when disabled", result is False)
    check("disabled sender does not write to spool", sender_off.spool.count() == 0)


def test_flush_spool_sync(tmp_dir: Path) -> None:
    section("flush_spool_sync() - synchronous flush")

    cfg = make_config(tmp_dir, spool_filename="flush_sync.jsonl")
    sender = LogCenterSender(cfg)

    sender.send_spool("INFO", "msg A")
    sender.send_spool("INFO", "msg B")
    sender.send_spool("INFO", "msg C")

    with patch.object(sender.http, "post_log_sync", return_value=make_ok_response()):
        result = sender.flush_spool_sync()

    check("flush_spool_sync sent=3", result["sent"] == 3, str(result))
    check("flush_spool_sync failed=0", result["failed"] == 0)
    check("flush_spool_sync remaining=0", result["remaining"] == 0)
    check("spool is empty after flush", sender.spool.count() == 0)

    sender.send_spool("INFO", "will send")
    sender.send_spool("INFO", "will fail")
    sender.send_spool("INFO", "never reached")

    responses = [make_ok_response(), make_err_response()]
    call_count = 0

    def side_effect(payload):
        nonlocal call_count
        resp = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        return resp

    with patch.object(sender.http, "post_log_sync", side_effect=side_effect):
        result2 = sender.flush_spool_sync()

    check("partial failure: sent=1", result2["sent"] == 1, str(result2))
    check("partial failure: failed=1", result2["failed"] == 1)
    check("partial failure: failed item re-queued", result2["remaining"] >= 1)

    cfg2 = make_config(tmp_dir, spool_filename="exc_test.jsonl")
    sender2 = LogCenterSender(cfg2)
    sender2.send_spool("WARN", "exception test")

    with patch.object(sender2.http, "post_log_sync", side_effect=Exception("timeout")):
        result3 = sender2.flush_spool_sync()

    check("exception during flush is handled", result3["failed"] == 1)
    check("exception: message re-queued", result3["remaining"] == 1)


def test_flush_spool_async(tmp_dir: Path) -> None:
    section("flush_spool() - async flush")

    async def run():
        cfg = make_config(tmp_dir, spool_filename="flush_async.jsonl")
        sender = LogCenterSender(cfg)

        sender.send_spool("DEBUG", "async msg 1")
        sender.send_spool("DEBUG", "async msg 2")

        async def async_post(payload):
            return make_ok_response()

        with patch.object(sender.http, "post_log", side_effect=async_post):
            result = await sender.flush_spool()

        check("async flush sent=2", result["sent"] == 2, str(result))
        check("async flush remaining=0", result["remaining"] == 0)

    asyncio.run(run())


def test_send_sync(tmp_dir: Path) -> None:
    section("send_sync() - sync immediate send")

    cfg = make_config(tmp_dir, spool_filename="send_sync.jsonl")
    sender = LogCenterSender(cfg)

    async def async_ok(payload):
        return make_ok_response()

    with patch.object(sender.http, "post_log", side_effect=async_ok):
        result = sender.send_sync("INFO", "sync message")
    check("send_sync returns True on success", result is True)

    async def async_fail(payload):
        return make_err_response()

    with patch.object(sender.http, "post_log", side_effect=async_fail):
        result2 = sender.send_sync("ERROR", "sync fail")
    check("send_sync returns False on failure", result2 is False)
    check("send_sync spools on failure", sender.spool.count() == 1)


def test_send_async(tmp_dir: Path) -> None:
    section("send() - async immediate send")

    async def run():
        cfg = make_config(tmp_dir, spool_filename="send_async.jsonl")
        sender = LogCenterSender(cfg)

        async def async_ok(payload):
            return make_ok_response()

        with patch.object(sender.http, "post_log", side_effect=async_ok):
            ok = await sender.send("INFO", "async message", request_id="req-123")
        check("send() returns True on success", ok is True)

        async def async_fail(payload):
            return make_err_response()

        with patch.object(sender.http, "post_log", side_effect=async_fail):
            ok2 = await sender.send("CRITICAL", "async failure")
        check("send() returns False on failure", ok2 is False)
        check("send() spools on failure", sender.spool.count() == 1)

        async def async_exc(payload):
            raise ConnectionError("refused")

        with patch.object(sender.http, "post_log", side_effect=async_exc):
            ok3 = await sender.send("WARN", "connection error")
        check("send() handles exception gracefully", ok3 is False)

    asyncio.run(run())


def test_flush_threshold(tmp_dir: Path) -> None:
    section("flush_threshold_count - auto-trigger on count")

    cfg = make_config(tmp_dir, spool_filename="threshold.jsonl", flush_threshold_count=3)
    sender = LogCenterSender(cfg)

    flush_calls: List[int] = []

    def fake_flush_sync(**kwargs):
        sender.spool.pop_batch(100)
        flush_calls.append(1)
        return {"sent": 1, "failed": 0, "remaining": 0}

    with patch.object(sender, "flush_spool_sync", side_effect=fake_flush_sync):
        sender.send_spool("INFO", "msg 1")
        sender.send_spool("INFO", "msg 2")
        check("no flush before threshold", len(flush_calls) == 0)

        sender.send_spool("INFO", "msg 3")
        time.sleep(0.1)

    check("flush triggered at threshold", len(flush_calls) >= 1,
          f"flush_calls={len(flush_calls)}")


def test_background_flush_thread(tmp_dir: Path) -> None:
    section("start/stop_background_flush_thread()")

    cfg = make_config(tmp_dir, spool_filename="bg_thread.jsonl", flush_interval_s=0.1)
    sender = LogCenterSender(cfg)

    flush_calls: List[int] = []
    original_flush = sender.flush_spool_sync

    def counting_flush(**kwargs):
        flush_calls.append(1)
        return original_flush(**kwargs)

    with patch.object(sender, "flush_spool_sync", side_effect=counting_flush):
        sender.start_background_flush_thread()
        check("thread is alive after start",
              sender._bg_thread is not None and sender._bg_thread.is_alive())

        sender.start_background_flush_thread()  # no-op

        time.sleep(0.4)
        sender.stop_background_flush_thread(timeout=2.0)

    check("background thread stopped",
          sender._bg_thread is None or not sender._bg_thread.is_alive())
    check("flush was called by background thread", len(flush_calls) >= 2,
          f"flush called {len(flush_calls)} times")

    cfg2 = make_config(tmp_dir, spool_filename="wake.jsonl", flush_interval_s=60.0)
    sender2 = LogCenterSender(cfg2)
    wake_calls: List[int] = []

    def wake_flush(**kwargs):
        wake_calls.append(1)
        return {"sent": 0, "failed": 0, "remaining": 0}

    with patch.object(sender2, "flush_spool_sync", side_effect=wake_flush):
        sender2.start_background_flush_thread()
        time.sleep(0.05)
        sender2._thread_wake_event.set()
        time.sleep(0.1)
        sender2.stop_background_flush_thread(timeout=2.0)

    check("wake signal causes immediate flush", len(wake_calls) >= 2,
          f"calls={len(wake_calls)}")


def test_auto_flush_config(tmp_dir: Path) -> None:
    section("auto_flush=True config flag")

    cfg = make_config(tmp_dir, spool_filename="auto.jsonl",
                      auto_flush=True, flush_interval_s=60.0)
    sender = LogCenterSender(cfg)

    check("background thread auto-started",
          sender._bg_thread is not None and sender._bg_thread.is_alive())
    sender.stop_background_flush_thread(timeout=2.0)
    check("thread stopped cleanly",
          sender._bg_thread is None or not sender._bg_thread.is_alive())


# ---------------------------------------------------------------------------
# Live tests (require real LogCenter credentials)
# ---------------------------------------------------------------------------

def live_config(tmp_dir: Path, live: Dict[str, str], **kwargs) -> LogCenterConfig:
    defaults: Dict[str, Any] = dict(
        base_url=live["url"],
        project_id=live["project_id"],
        api_key=live.get("api_key"),
        spool_dir=tmp_dir,
        spool_filename="live_spool.jsonl",
        flush_interval_s=5.0,
    )
    defaults.update(kwargs)
    return LogCenterConfig(**defaults)


def test_live_send_sync(tmp_dir: Path, live: Dict[str, str]) -> None:
    section("[LIVE] send_sync() - immediate sync send")

    cfg = live_config(tmp_dir, live)
    sender = LogCenterSender(cfg)

    ok = sender.send_sync("INFO", "test_live_send_sync: INFO message",
                          tags=["test", "sdk"], data={"source": "test_sdk.py"})
    check("send_sync INFO succeeds", ok is True)

    ok2 = sender.send_sync("ERROR", "test_live_send_sync: ERROR message",
                           data={"source": "test_sdk.py"})
    check("send_sync ERROR succeeds", ok2 is True)

    ok3 = sender.send_sync("WARNING", "test_live_send_sync: WARNING message")
    check("send_sync WARNING succeeds", ok3 is True)


def test_live_send_async(tmp_dir: Path, live: Dict[str, str]) -> None:
    section("[LIVE] send() - immediate async send")

    async def run():
        cfg = live_config(tmp_dir, live)
        sender = LogCenterSender(cfg)

        ok = await sender.send("DEBUG", "test_live_send_async: DEBUG message",
                               tags=["test", "async"], data={"source": "test_sdk.py"})
        check("send() DEBUG succeeds", ok is True)

        ok2 = await sender.send("CRITICAL", "test_live_send_async: CRITICAL message",
                                data={"source": "test_sdk.py"})
        check("send() CRITICAL succeeds", ok2 is True)

    asyncio.run(run())


def test_live_spool_and_flush(tmp_dir: Path, live: Dict[str, str]) -> None:
    section("[LIVE] send_spool() + flush_spool_sync()")

    cfg = live_config(tmp_dir, live, spool_filename="live_flush.jsonl")
    sender = LogCenterSender(cfg)

    sender.send_spool("INFO", "test_live_spool_and_flush: queued msg 1",
                      data={"source": "test_sdk.py", "seq": 1})
    sender.send_spool("WARN", "test_live_spool_and_flush: queued msg 2",
                      data={"source": "test_sdk.py", "seq": 2})
    sender.send_spool("ERROR", "test_live_spool_and_flush: queued msg 3",
                      data={"source": "test_sdk.py", "seq": 3})

    queued = sender.spool.count()
    check("3 messages queued before flush", queued == 3, f"queued={queued}")

    result = sender.flush_spool_sync()
    check("flush_spool_sync sent all", result["sent"] == 3, str(result))
    check("flush_spool_sync no failures", result["failed"] == 0)
    check("spool empty after flush", result["remaining"] == 0)


def test_live_background_flush(tmp_dir: Path, live: Dict[str, str]) -> None:
    section("[LIVE] send_spool() + background flush thread")

    cfg = live_config(tmp_dir, live,
                      spool_filename="live_bg.jsonl",
                      flush_interval_s=2.0)
    sender = LogCenterSender(cfg)

    sender.send_spool("INFO", "test_live_background_flush: bg msg 1",
                      data={"source": "test_sdk.py"})
    sender.send_spool("INFO", "test_live_background_flush: bg msg 2",
                      data={"source": "test_sdk.py"})

    check("messages queued before thread start", sender.spool.count() == 2)

    sender.start_background_flush_thread()
    check("background thread started", sender._bg_thread.is_alive())

    # wait for the background thread to flush (interval is 2s)
    deadline = time.time() + 10.0
    while sender.spool.count() > 0 and time.time() < deadline:
        time.sleep(0.25)

    sender.stop_background_flush_thread(timeout=3.0)
    check("spool drained by background thread", sender.spool.count() == 0,
          f"remaining={sender.spool.count()}")


def test_live_threshold_flush(tmp_dir: Path, live: Dict[str, str]) -> None:
    section("[LIVE] flush_threshold_count - auto-flush to real API")

    cfg = live_config(tmp_dir, live,
                      spool_filename="live_thresh.jsonl",
                      flush_threshold_count=3)
    sender = LogCenterSender(cfg)

    sender.send_spool("INFO", "test_live_threshold_flush: msg 1",
                      data={"source": "test_sdk.py"})
    sender.send_spool("INFO", "test_live_threshold_flush: msg 2",
                      data={"source": "test_sdk.py"})
    check("no flush before threshold", sender.spool.count() == 2)

    sender.send_spool("INFO", "test_live_threshold_flush: msg 3 (triggers flush)",
                      data={"source": "test_sdk.py"})

    # wait for the one-shot thread to finish
    deadline = time.time() + 10.0
    while sender.spool.count() > 0 and time.time() < deadline:
        time.sleep(0.25)

    check("spool drained by threshold flush", sender.spool.count() == 0,
          f"remaining={sender.spool.count()}")


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LogCenter SDK test script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Live tests run only when --url and --project-id are provided\n"
            "(or via LOGCENTER_BASE_URL / LOGCENTER_PROJECT_ID env vars).\n"
        ),
    )
    parser.add_argument(
        "--url",
        default=os.getenv("LOGCENTER_BASE_URL", ""),
        metavar="URL",
        help="LogCenter base URL (env: LOGCENTER_BASE_URL)",
    )
    parser.add_argument(
        "--project-id",
        default=os.getenv("LOGCENTER_PROJECT_ID", ""),
        metavar="ID",
        help="LogCenter project ID (env: LOGCENTER_PROJECT_ID)",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("LOGCENTER_API_KEY", ""),
        metavar="KEY",
        help="LogCenter API key (env: LOGCENTER_API_KEY)",
    )
    parser.add_argument(
        "--live-only",
        action="store_true",
        help="Skip mocked tests and run only live tests",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    live: Optional[Dict[str, str]] = None
    if args.url and args.project_id:
        live = {
            "url": args.url.rstrip("/"),
            "project_id": args.project_id,
            "api_key": args.api_key,
        }

    mode = "LIVE ONLY" if args.live_only else ("MOCKED + LIVE" if live else "MOCKED")
    print(f"\nLogCenter SDK - Test Script  [{mode}]")
    print("=" * 60)

    if live:
        print(f"  URL:        {live['url']}")
        print(f"  Project ID: {live['project_id']}")
        print(f"  API Key:    {'(set)' if live.get('api_key') else '(not set)'}")

    tmp = Path(tempfile.mkdtemp(prefix="logcenter_test_"))
    try:
        mocked_tests = [
            ("Config",                  lambda: test_config()),
            ("FileSpool",               lambda: test_spool(tmp / "spool")),
            ("send_spool",              lambda: test_send_spool(tmp / "send_spool")),
            ("flush_spool_sync",        lambda: test_flush_spool_sync(tmp / "flush_sync")),
            ("flush_spool (async)",     lambda: test_flush_spool_async(tmp / "flush_async")),
            ("send_sync",               lambda: test_send_sync(tmp / "send_sync")),
            ("send (async)",            lambda: test_send_async(tmp / "send_async")),
            ("flush_threshold_count",   lambda: test_flush_threshold(tmp / "threshold")),
            ("background_flush_thread", lambda: test_background_flush_thread(tmp / "bg")),
            ("auto_flush config",       lambda: test_auto_flush_config(tmp / "auto")),
        ]

        live_tests = [
            ("live: send_sync",          lambda: test_live_send_sync(tmp / "live1", live)),
            ("live: send async",         lambda: test_live_send_async(tmp / "live2", live)),
            ("live: spool + flush_sync", lambda: test_live_spool_and_flush(tmp / "live3", live)),
            ("live: background flush",   lambda: test_live_background_flush(tmp / "live4", live)),
            ("live: threshold flush",    lambda: test_live_threshold_flush(tmp / "live5", live)),
        ]

        tests_to_run = []
        if not args.live_only:
            tests_to_run += mocked_tests
        if live:
            tests_to_run += live_tests
        elif args.live_only:
            print("\n  No credentials supplied. Provide --url and --project-id to run live tests.")
            sys.exit(1)

        for name, fn in tests_to_run:
            try:
                fn()
            except Exception:
                print(f"\n  [EXCEPTION] in {name}:")
                traceback.print_exc()

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  |  {failed} FAILED:")
        for name, ok, detail in results:
            if not ok:
                print(f"    - {name}" + (f" ({detail})" if detail else ""))
    else:
        print(" - all tests passed!")
    print()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
