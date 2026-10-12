import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable, List, Dict, Any, Optional

from playwright.sync_api import sync_playwright

from .config import (
    BASE_URL, SAML_PATH, PROFILE_PATH, DOWNLOAD_DIR,
    TERM_FILTER, HEADLESS, ENABLE_CALENDAR
)
from . import database as db
from .auth import is_session_valid
from .downloader import sanitize_name, index_existing_files, download_and_process_file
from .converter import html_to_markdown
from .tasks import run_task_extraction_for_course
from .calendar import save_calendars_to_disk

def fetch_enrolled_courses(page, logger=print) -> List[Dict[str, Any]]:
    """Discovers all enrolled courses from Blackboard REST API and syncs them to DB."""
    logger("🔍 Discovering enrolled courses from Blackboard...")
    res_me = page.request.get(f"{BASE_URL}/learn/api/v1/users/me")
    if res_me.status != 200:
        logger(f"❌ Failed to query current user profile (HTTP {res_me.status})")
        return []

    user_id = res_me.json().get("id")
    memberships_url = f"{BASE_URL}/learn/api/v1/users/{user_id}/memberships?expand=course.effectiveAvailability,course.permissions,courseRole&includeCount=true&limit=100"
    res = page.request.get(memberships_url)
    if res.status != 200:
        logger(f"❌ Failed to query course memberships (HTTP {res.status})")
        return []

    results = res.json().get("results", [])
    courses = []

    for item in results:
        c_info = item.get("course", {})
        cid = item.get("courseId")
        code = c_info.get("courseId", "")
        name = c_info.get("name", "")

        if TERM_FILTER and TERM_FILTER not in code:
            continue

        folder_name = sanitize_name(name)
        course_folder = DOWNLOAD_DIR / folder_name
        course_folder.mkdir(parents=True, exist_ok=True)

        db.upsert_course(cid, code, name, str(course_folder))
        courses.append({
            "id": cid,
            "code": code,
            "name": name,
            "folder": course_folder
        })

    logger(f"✅ Discovered {len(courses)} enrolled courses.")
    return courses

def fetch_course_tree(page, course_id: str, parent_id: str = "ROOT", path: str = "") -> List[Dict[str, Any]]:
    """Recursively walks Blackboard course contents folder tree."""
    url = f"{BASE_URL}/learn/api/v1/courses/{course_id}/contents/{parent_id}/children"
    res = page.request.get(url)
    if res.status != 200:
        return []

    items = res.json().get("results", []) if isinstance(res.json(), dict) else res.json()
    collected = []

    for item in items:
        title = item.get("title", "")
        item_id = item.get("id")
        handler = item.get("contentHandler", "")
        current_path = f"{path} > {title}" if path else title
        cd = item.get("contentDetail", {})

        if "resource/x-bb-file" in cd:
            finfo = cd["resource/x-bb-file"].get("file", {})
            collected.append({
                "type": "file",
                "id": item_id,
                "title": title,
                "path": current_path,
                "fileName": finfo.get("fileName"),
                "fileSize": finfo.get("fileSize"),
                "mimeType": finfo.get("mimeType"),
                "permanentUrl": finfo.get("permanentUrl") or finfo.get("viewerUrl")
            })
        elif "resource/x-bb-assignment" in cd:
            collected.append({
                "type": "assignment",
                "id": item_id,
                "title": title,
                "path": current_path,
                "dueDate": item.get("dueDate")
            })

        if any(k in handler for k in ["folder", "lesson", "learningmodule"]):
            collected.extend(fetch_course_tree(page, course_id, item_id, current_path))

    return collected

def fetch_course_announcements(page, course_id: str) -> List[Dict[str, Any]]:
    """Fetches all recent course announcements."""
    ann_url = f"{BASE_URL}/learn/api/v1/courses/{course_id}/announcements"
    res = page.request.get(ann_url)
    if res.status != 200:
        return []

    raw_items = res.json().get("results", [])
    announcements = []

    for a in raw_items:
        aid = a.get("id") or str(hash(a.get("title", "") + a.get("created", "")))
        title = a.get("title", "Announcement")
        created = a.get("created")
        body_html = a.get("body", "")
        body_md = html_to_markdown(body_html)

        db.upsert_announcement(aid, course_id, title, created, body_html, body_md)
        announcements.append({
            "id": aid,
            "course_id": course_id,
            "title": title,
            "created_at": created,
            "raw_html": body_html,
            "markdown_body": body_md
        })

    return announcements

def run_sync(log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    Main entry point for synchronizing courses, materials, announcements, and tasks.
    """
    logs: List[str] = []

    def logger(msg: str):
        formatted = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        logs.append(formatted)
        print(formatted)
        if log_callback:
            try:
                log_callback(formatted)
            except Exception:
                pass

    logger("🚀 Starting Blackboard Academic Synchronization Engine...")
    db.init_db()
    run_id = db.start_sync_run()

    stats = {
        "new_files": 0,
        "deduped_files": 0,
        "failed_files": 0,
        "new_tasks": 0,
        "announcements": 0
    }

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_PATH,
                headless=HEADLESS
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            # Navigate to session or SAML entry
            try:
                target_url = f"{BASE_URL}{SAML_PATH}" if SAML_PATH.startswith("/") else SAML_PATH
                page.goto(target_url)
                page.wait_for_selector("h4, .base-personal-avatar, #main-heading", timeout=15000)
            except Exception:
                pass

            if not is_session_valid(page):
                logger("❌ Session is not authenticated! Please click 'Login' to authorize with 2FA.")
                ctx.close()
                db.finish_sync_run(run_id, "failed", 0, 0, 0, "\n".join(logs))
                return {"status": "error", "message": "Authentication required", "logs": logs}

            # Enumerate courses
            all_courses = fetch_enrolled_courses(page, logger=logger)
            active_course_rows = db.get_courses(only_active=True)
            active_ids = {c["id"] for c in active_course_rows}

            # Filter to active courses
            courses_to_sync = [c for c in all_courses if c["id"] in active_ids] if active_ids else all_courses

            logger(f"📚 Syncing {len(courses_to_sync)} active courses...")

            for course in courses_to_sync:
                cid = course["id"]
                cname = course["name"]
                cfolder = Path(course["folder"])
                logger(f"📂 [{cname}] Crawling content and announcements...")

                # 1. Announcements
                anns = fetch_course_announcements(page, cid)
                stats["announcements"] += len(anns)

                # 2. Course Tree Items
                tree_items = fetch_course_tree(page, cid)

                # 3. Tasks & Deadline Extraction
                task_stats = run_task_extraction_for_course(course, tree_items, anns)
                stats["new_tasks"] += task_stats["assignment_tasks"] + task_stats["announcement_tasks"]

                # 4. Files Download & Markdown Conversion
                existing_index = index_existing_files(cfolder)
                for item in tree_items:
                    if item.get("type") != "file":
                        continue
                    downloaded, status = download_and_process_file(
                        page=page,
                        base_url=BASE_URL,
                        course_id=cid,
                        course_folder=cfolder,
                        item=item,
                        existing_index=existing_index,
                        logger=logger
                    )
                    if downloaded:
                        stats["new_files"] += 1
                    elif "deduped" in status:
                        stats["deduped_files"] += 1
                    elif "error" in status or "http" in status:
                        stats["failed_files"] += 1

                db.update_course_synced(cid)

            # 5. Calendar Fetch
            cal_events = []
            if ENABLE_CALENDAR:
                logger("📅 Syncing semester calendar and deadlines...")
                cal_url = f"{BASE_URL}/learn/api/v1/calendars/calendarItems?since={datetime.now().year}-01-01T00:00:00.000Z&until={datetime.now().year}-12-31T23:59:59.000Z"
                cal_res = page.request.get(cal_url)
                if cal_res.status == 200:
                    cal_events = cal_res.json().get("results", [])

            ctx.close()

        # Save .ics calendar files
        if ENABLE_CALENDAR:
            cal_paths = save_calendars_to_disk(cal_events)
            logger(f"✅ Generated updated .ics calendar feeds: {list(cal_paths.keys())}")

        summary = (
            f"Sync Complete: {stats['new_files']} downloaded, "
            f"{stats['deduped_files']} deduped, {stats['new_tasks']} tasks found."
        )
        logger(f"🎉 {summary}")
        db.finish_sync_run(run_id, "success", stats["new_files"], stats["new_files"], stats["new_tasks"], "\n".join(logs))

        return {"status": "success", "stats": stats, "logs": logs}

    except Exception as e:
        logger(f"❌ Error during sync execution: {e}")
        db.finish_sync_run(run_id, "failed", stats["new_files"], 0, stats["new_tasks"], "\n".join(logs))
        return {"status": "error", "message": str(e), "logs": logs}
