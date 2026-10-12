import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import DATABASE_PATH

@contextmanager
def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS courses (
            id TEXT PRIMARY KEY,
            code TEXT,
            name TEXT NOT NULL,
            folder TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            last_synced_at TEXT
        );

        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            remote_path TEXT,
            filename TEXT NOT NULL,
            local_path TEXT NOT NULL,
            file_size INTEGER,
            content_hash TEXT,
            is_converted INTEGER DEFAULT 0,
            markdown_path TEXT,
            downloaded_at TEXT,
            FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT,
            raw_html TEXT,
            markdown_body TEXT,
            FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            course_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            source_type TEXT DEFAULT 'assignment',
            source_id TEXT,
            completed INTEGER DEFAULT 0,
            priority TEXT DEFAULT 'medium',
            created_at TEXT,
            FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            status TEXT NOT NULL,
            new_files INTEGER DEFAULT 0,
            converted_files INTEGER DEFAULT 0,
            new_tasks INTEGER DEFAULT 0,
            log_summary TEXT
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_files_course ON files (course_id);
        CREATE INDEX IF NOT EXISTS idx_announcements_course ON announcements (course_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_course ON tasks (course_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks (due_date);
        """)

# --- Course Helpers ---

def upsert_course(cid: str, code: str, name: str, folder: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO courses (id, code, name, folder, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                code=excluded.code,
                name=excluded.name,
                folder=excluded.folder
        """, (cid, code, name, folder))

def update_course_synced(cid: str):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE courses SET last_synced_at=? WHERE id=?", (now, cid))

def toggle_course_active(cid: str, is_active: bool):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE courses SET is_active=? WHERE id=?", (1 if is_active else 0, cid))

def get_courses(only_active: bool = False) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM courses"
        if only_active:
            query += " WHERE is_active = 1"
        query += " ORDER BY name ASC"
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]

# --- File Helpers ---

def upsert_file(fid: str, cid: str, remote_path: str, filename: str, local_path: str,
                file_size: Optional[int], content_hash: Optional[str]) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM files WHERE id=?", (fid,))
        exists = cursor.fetchone() is not None
        cursor.execute("""
            INSERT INTO files (id, course_id, remote_path, filename, local_path, file_size, content_hash, downloaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                local_path=excluded.local_path,
                file_size=excluded.file_size,
                content_hash=excluded.content_hash
        """, (fid, cid, remote_path, filename, local_path, file_size, content_hash, now))
        return not exists

def mark_file_converted(fid: str, markdown_path: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE files SET is_converted=1, markdown_path=? WHERE id=?", (markdown_path, fid))

def get_unconverted_files(limit: int = 100) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM files WHERE is_converted=0 AND filename LIKE '%.pdf' LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_files_by_course(cid: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM files WHERE course_id=? ORDER BY filename ASC", (cid,))
        return [dict(row) for row in cursor.fetchall()]

# --- Announcement Helpers ---

def upsert_announcement(aid: str, cid: str, title: str, created_at: str, raw_html: str, markdown_body: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO announcements (id, course_id, title, created_at, raw_html, markdown_body)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                raw_html=excluded.raw_html,
                markdown_body=excluded.markdown_body
        """, (aid, cid, title, created_at, raw_html, markdown_body))

def get_announcements(cid: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if cid:
            cursor.execute("""
                SELECT a.*, c.name as course_name
                FROM announcements a
                JOIN courses c ON a.course_id = c.id
                WHERE a.course_id = ?
                ORDER BY a.created_at DESC LIMIT ?
            """, (cid, limit))
        else:
            cursor.execute("""
                SELECT a.*, c.name as course_name
                FROM announcements a
                JOIN courses c ON a.course_id = c.id
                ORDER BY a.created_at DESC LIMIT ?
            """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

# --- Task Helpers ---

def upsert_task(tid: str, cid: Optional[str], title: str, description: Optional[str],
                due_date: Optional[str], source_type: str, source_id: Optional[str], priority: str = "medium") -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id=?", (tid,))
        exists = cursor.fetchone() is not None
        if not exists:
            cursor.execute("""
                INSERT INTO tasks (id, course_id, title, description, due_date, source_type, source_id, completed, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """, (tid, cid, title, description, due_date, source_type, source_id, priority, now))
        else:
            cursor.execute("""
                UPDATE tasks SET
                    course_id=COALESCE(?, course_id),
                    title=?,
                    description=?,
                    due_date=?,
                    priority=?
                WHERE id=?
            """, (cid, title, description, due_date, priority, tid))
        return not exists

def toggle_task_completed(tid: str, completed: bool):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET completed=? WHERE id=?", (1 if completed else 0, tid))

def delete_task(tid: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id=?", (tid,))

def update_task(tid: str, title: Optional[str] = None, description: Optional[str] = None,
                due_date: Optional[str] = None, priority: Optional[str] = None,
                course_id: Optional[str] = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        fields = []
        params = []
        if title is not None:
            fields.append("title=?")
            params.append(title)
        if description is not None:
            fields.append("description=?")
            params.append(description)
        if due_date is not None:
            fields.append("due_date=?")
            params.append(due_date)
        if priority is not None:
            fields.append("priority=?")
            params.append(priority)
        if course_id is not None:
            fields.append("course_id=?")
            params.append(course_id)
        if fields:
            params.append(tid)
            cursor.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=?", params)

def cleanup_legacy_announcement_tasks():
    """Removes fragmented legacy announcement tasks (e.g. ann_task_*_0, ann_task_*_1)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id GLOB 'ann_task_*_*'")

def get_tasks(completed: Optional[bool] = None, cid: Optional[str] = None,
              source_type: Optional[str] = None, priority: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT t.*, c.name as course_name, c.code as course_code
            FROM tasks t
            LEFT JOIN courses c ON t.course_id = c.id
            WHERE 1=1
        """
        params = []
        if completed is not None:
            query += " AND t.completed = ?"
            params.append(1 if completed else 0)
        if cid:
            query += " AND t.course_id = ?"
            params.append(cid)
        if source_type:
            query += " AND t.source_type = ?"
            params.append(source_type)
        if priority:
            query += " AND t.priority = ?"
            params.append(priority)

        # Order by:
        # 1. Official assignment deadlines first, then priority (high -> medium -> low), then due date
        query += """ ORDER BY
            CASE WHEN t.source_type = 'assignment' THEN 0 ELSE 1 END,
            CASE t.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END,
            t.due_date ASC,
            t.created_at DESC
        """
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

# --- App Settings Helpers ---

def get_setting(key: str, default: Any = None) -> Any:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key=?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def set_setting(key: str, value: Any):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, str(value)))

# --- Sync Run Helpers ---

def start_sync_run() -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sync_runs (started_at, status) VALUES (?, 'running')", (now,))
        return cursor.lastrowid

def finish_sync_run(run_id: int, status: str, new_files: int, converted_files: int, new_tasks: int, log_summary: str):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE sync_runs
            SET ended_at=?, status=?, new_files=?, converted_files=?, new_tasks=?, log_summary=?
            WHERE id=?
        """, (now, status, new_files, converted_files, new_tasks, log_summary, run_id))

def get_dashboard_stats() -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM courses WHERE is_active=1")
        active_courses = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tasks WHERE completed=0")
        pending_tasks = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM files")
        total_files = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM files WHERE is_converted=1")
        converted_files = cursor.fetchone()[0]

        cursor.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1")
        last_run = cursor.fetchone()

        return {
            "active_courses": active_courses,
            "pending_tasks": pending_tasks,
            "total_files": total_files,
            "converted_files": converted_files,
            "last_sync": dict(last_run) if last_run else None
        }
