import asyncio
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, Any

from .config import SYNC_INTERVAL_HOURS
from . import sync
from . import database as db

_sync_lock = threading.Lock()
_is_syncing = False
_scheduler_task: Optional[asyncio.Task] = None
_next_sync_time: Optional[datetime] = None
_last_sync_time: Optional[datetime] = None

# Default settings
_auto_sync_enabled: bool = True
_interval_hours: float = SYNC_INTERVAL_HOURS

def is_sync_active() -> bool:
    return _is_syncing

def execute_sync_job(log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    global _is_syncing, _last_sync_time
    if not _sync_lock.acquire(blocking=False):
        if log_callback:
            log_callback("⚠️ Sync already in progress, skipping duplicate request.")
        return {"status": "busy", "message": "Sync already running"}

    _is_syncing = True
    try:
        res = sync.run_sync(log_callback=log_callback)
        _last_sync_time = datetime.now(timezone.utc)
        return res
    finally:
        _is_syncing = False
        _sync_lock.release()

def load_scheduler_preferences():
    global _auto_sync_enabled, _interval_hours
    try:
        saved_enabled = db.get_setting("auto_sync_enabled")
        if saved_enabled is not None:
            _auto_sync_enabled = str(saved_enabled).lower() in ("true", "1", "yes")

        saved_interval = db.get_setting("auto_sync_interval_hours")
        if saved_interval is not None:
            _interval_hours = float(saved_interval)
    except Exception:
        pass

def get_scheduler_info() -> Dict[str, Any]:
    load_scheduler_preferences()
    stats = db.get_dashboard_stats()
    last_sync = stats.get("last_sync")
    last_iso = last_sync.get("ended_at") if last_sync else None

    return {
        "is_syncing": _is_syncing,
        "auto_sync_enabled": _auto_sync_enabled,
        "interval_hours": _interval_hours,
        "next_sync_time": _next_sync_time.isoformat() if _next_sync_time else None,
        "last_sync_time": last_iso or (_last_sync_time.isoformat() if _last_sync_time else None)
    }

def configure_scheduler(enabled: Optional[bool] = None, interval_hours: Optional[float] = None) -> Dict[str, Any]:
    global _auto_sync_enabled, _interval_hours
    if enabled is not None:
        _auto_sync_enabled = enabled
        db.set_setting("auto_sync_enabled", "true" if enabled else "false")

    if interval_hours is not None:
        _interval_hours = max(0.5, float(interval_hours))
        db.set_setting("auto_sync_interval_hours", str(_interval_hours))

    # Restart scheduler with new configuration
    stop_scheduler()
    start_scheduler()
    return get_scheduler_info()

async def scheduler_loop():
    """Background loop that executes an initial sync on launch and periodic intervals thereafter."""
    global _next_sync_time
    load_scheduler_preferences()

    print(f"⏰ Auto-sync scheduler active (Enabled: {_auto_sync_enabled}, Interval: every {_interval_hours}h).")

    # Initial sync grace period: 10 seconds after server launch
    if _auto_sync_enabled:
        _next_sync_time = datetime.now(timezone.utc) + timedelta(seconds=10)
        try:
            await asyncio.sleep(10)
            if _auto_sync_enabled and not _is_syncing:
                print("⚡ Triggering startup initial auto-sync...")
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, execute_sync_job)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"⚠️ Startup sync notice: {e}")

    # Periodic loop
    while True:
        try:
            load_scheduler_preferences()
            interval_sec = max(300, int(_interval_hours * 3600))

            if not _auto_sync_enabled:
                _next_sync_time = None
                await asyncio.sleep(10)
                continue

            _next_sync_time = datetime.now(timezone.utc) + timedelta(seconds=interval_sec)

            # Sleep in 5-second chunks so configuration changes are responsive
            elapsed = 0
            while elapsed < interval_sec:
                await asyncio.sleep(5)
                elapsed += 5
                if not _auto_sync_enabled:
                    break

            if _auto_sync_enabled and not _is_syncing:
                print("⏰ Triggering periodic scheduled background sync...")
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, execute_sync_job)

        except asyncio.CancelledError:
            print("🛑 Background sync scheduler stopped.")
            break
        except Exception as e:
            print(f"⚠️ Scheduler loop error: {e}")
            await asyncio.sleep(30)

def start_scheduler():
    global _scheduler_task
    try:
        loop = asyncio.get_running_loop()
        if _scheduler_task is None or _scheduler_task.done():
            _scheduler_task = loop.create_task(scheduler_loop())
    except RuntimeError:
        # No running event loop in current thread
        pass

def stop_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
