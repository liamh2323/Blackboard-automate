import asyncio
import threading
from typing import Optional, Callable

from .config import SYNC_INTERVAL_HOURS
from . import sync

_sync_lock = threading.Lock()
_is_syncing = False
_scheduler_task: Optional[asyncio.Task] = None

def is_sync_active() -> bool:
    return _is_syncing

def execute_sync_job(log_callback: Optional[Callable[[str], None]] = None):
    global _is_syncing
    if not _sync_lock.acquire(blocking=False):
        if log_callback:
            log_callback("⚠️ Sync already in progress, skipping duplicate request.")
        return {"status": "busy", "message": "Sync already running"}

    _is_syncing = True
    try:
        return sync.run_sync(log_callback=log_callback)
    finally:
        _is_syncing = False
        _sync_lock.release()

async def scheduler_loop(interval_hours: float = SYNC_INTERVAL_HOURS):
    """Periodic background worker loop."""
    interval_seconds = max(300, int(interval_hours * 3600)) # minimum 5 min
    print(f"⏰ Background sync scheduler enabled (Interval: every {interval_hours} hours).")

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            print("⏰ Triggering scheduled background sync...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, execute_sync_job)
        except asyncio.CancelledError:
            print("🛑 Background sync scheduler stopped.")
            break
        except Exception as e:
            print(f"⚠️ Scheduler error: {e}")

def start_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(scheduler_loop())

def stop_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
