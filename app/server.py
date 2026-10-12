import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import database as db
from . import scheduler
from . import auth
from . import calendar as cal_gen
from . import coverage
from .config import BASE_DIR, DOWNLOAD_DIR, HOST, PORT, ENABLE_CALENDAR

# Broadcast queue for real-time SSE logs
log_subscribers: List[asyncio.Queue] = []

def broadcast_log(msg: str):
    for q in list(log_subscribers):
        try:
            q.put_nowait(msg)
        except Exception:
            pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db.init_db()
    db.cleanup_legacy_announcement_tasks()
    scheduler.start_scheduler()
    yield
    # Shutdown
    scheduler.stop_scheduler()

app = FastAPI(title="Blackboard Automate", version="1.0.0", lifespan=lifespan)

# Request Models
class TaskCreate(BaseModel):
    title: str
    course_id: Optional[str] = None
    due_date: Optional[str] = None
    description: Optional[str] = None
    priority: str = "medium"

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    course_id: Optional[str] = None
    due_date: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None

class TaskToggle(BaseModel):
    completed: bool

class CourseToggle(BaseModel):
    is_active: bool

class SchedulerConfig(BaseModel):
    enabled: Optional[bool] = None
    interval_hours: Optional[float] = None

# --- API Endpoints ---

@app.get("/api/stats")
def get_stats():
    return db.get_dashboard_stats()

@app.get("/api/courses")
def list_courses():
    return db.get_courses()

@app.post("/api/courses/{course_id}/toggle")
def toggle_course(course_id: str, payload: CourseToggle):
    db.toggle_course_active(course_id, payload.is_active)
    return {"status": "ok", "course_id": course_id, "is_active": payload.is_active}

@app.get("/api/tasks")
def list_tasks(completed: Optional[bool] = None, course_id: Optional[str] = None,
               source_type: Optional[str] = None, priority: Optional[str] = None):
    return db.get_tasks(completed=completed, cid=course_id, source_type=source_type, priority=priority)

@app.post("/api/tasks")
def create_task(payload: TaskCreate):
    import uuid
    tid = f"manual_{uuid.uuid4().hex[:8]}"
    db.upsert_task(
        tid=tid,
        cid=payload.course_id,
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        source_type="manual",
        source_id=None,
        priority=payload.priority
    )
    return {"status": "created", "id": tid}

@app.put("/api/tasks/{task_id}")
def update_task_endpoint(task_id: str, payload: TaskUpdate):
    db.update_task(
        tid=task_id,
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        priority=payload.priority,
        course_id=payload.course_id
    )
    return {"status": "ok", "id": task_id}

@app.post("/api/tasks/{task_id}/complete")
def toggle_task(task_id: str, payload: TaskToggle):
    db.toggle_task_completed(task_id, payload.completed)
    return {"status": "ok", "id": task_id, "completed": payload.completed}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    db.delete_task(task_id)
    return {"status": "deleted", "id": task_id}

# --- Academic Study Coverage Endpoints ---

@app.get("/api/coverage")
def get_study_coverage(course_id: Optional[str] = None):
    return coverage.build_study_coverage_report(course_id=course_id)

@app.get("/api/announcements")
def list_announcements(course_id: Optional[str] = None, limit: int = 50):
    return db.get_announcements(cid=course_id, limit=limit)

@app.get("/api/files")
def list_files(course_id: Optional[str] = None):
    if course_id:
        return db.get_files_by_course(course_id)
    return db.get_connection().cursor().execute("SELECT * FROM files ORDER BY downloaded_at DESC LIMIT 100").fetchall()

@app.get("/api/file-content")
def get_file_content(path: str = Query(...)):
    target = Path(path).resolve()
    # Security check: ensure path is inside workspace or download directory
    allowed_roots = [BASE_DIR.resolve(), DOWNLOAD_DIR.resolve()]
    if not any(str(target).startswith(str(root)) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Access denied to requested file path.")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"filename": target.name, "path": str(target), "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sync/status")
def sync_status():
    return scheduler.get_scheduler_info()

@app.post("/api/scheduler/config")
def set_scheduler_config(payload: SchedulerConfig):
    return scheduler.configure_scheduler(enabled=payload.enabled, interval_hours=payload.interval_hours)

@app.post("/api/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    if scheduler.is_sync_active():
        return {"status": "busy", "message": "Sync is already in progress"}

    def run_job():
        scheduler.execute_sync_job(log_callback=broadcast_log)

    background_tasks.add_task(run_job)
    return {"status": "started", "message": "Sync started in background"}

@app.get("/api/sync/logs")
async def stream_logs():
    q: asyncio.Queue = asyncio.Queue()
    log_subscribers.append(q)

    async def event_generator():
        try:
            yield f"data: Connected to Blackboard sync log stream\n\n"
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            if q in log_subscribers:
                log_subscribers.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/auth/login")
def launch_login(background_tasks: BackgroundTasks):
    if auth.is_login_active():
        return {"status": "busy", "message": "Login window is already open"}
    if scheduler.is_sync_active():
        return {"status": "busy", "message": "Cannot open browser login while synchronization is in progress"}

    def run_login():
        auth.launch_interactive_login(logger=broadcast_log)

    background_tasks.add_task(run_login)
    return {"status": "started", "message": "Browser login opened"}

# --- Calendar Feeds ---

@app.get("/calendar/deadlines.ics")
def serve_deadlines_calendar():
    ics_text = cal_gen.generate_deadlines_ics()
    return Response(content=ics_text, media_type="text/calendar", headers={
        "Content-Disposition": "inline; filename=deadlines.ics",
        "Cache-Control": "no-cache, no-store, must-revalidate"
    })

# --- Mount Static Frontend ---
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
