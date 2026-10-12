import re
import uuid
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from . import database as db
from .config import LLM_PROVIDER, LLM_API_KEY, OLLAMA_URL

DATE_PATTERNS = [
    # 2026-10-23 or 2026-10-23 23:59
    r'\b\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2})?\b',
    # 23/10/2026 or 23/10
    r'\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b',
    # Friday 24th October at 5pm / Oct 24th, 2026
    r'(?:(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s*)?(?:\d{1,2}(?:st|nd|rd|th)?\s+)?(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)(?:\s+\d{1,2}(?:st|nd|rd|th)?)?(?:,?\s*\d{4})?(?:\s+(?:at|by|before)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?',
    # by Friday 5pm / by end of week 4
    r'(?:by|before|due)\s+(?:end\s+of\s+)?(?:week\s+\d+|Monday|Tuesday|Wednesday|Thursday|Friday|tomorrow|next\s+week)(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?'
]

ACTION_KEYWORDS = [
    r'\bdue\b', r'\bsubmit\b', r'\bsubmission\b', r'\bhomework\b',
    r'\bassignment\b', r'\blab\s+(?:report|spec|exercise)\b', r'\bupload\b',
    r'\bquiz\b', r'\btest\b', r'\bexam\b', r'\bdeadline\b',
    r'\bhand\s+in\b', r'\bdeliverable\b', r'\bprepare\b', r'\breading\b'
]

def extract_assignment_task(item: Dict[str, Any], course_id: str, course_name: str) -> Optional[Dict[str, Any]]:
    """Converts a Blackboard assignment content tree item into a structured task."""
    title = item.get("title") or "Assignment"
    due_date = item.get("dueDate")
    item_id = item.get("id") or str(uuid.uuid4())
    task_id = f"bb_assign_{item_id}"

    description = f"Official Blackboard deliverable for {course_name}.\nLocation: {item.get('path', '')}"
    db.upsert_task(
        tid=task_id,
        cid=course_id,
        title=f"{course_name}: {title}",
        description=description,
        due_date=due_date,
        source_type="assignment",
        source_id=item_id,
        priority="high"
    )
    return {
        "id": task_id,
        "title": f"{course_name}: {title}",
        "due_date": due_date,
        "source_type": "assignment"
    }

def extract_tasks_from_announcement_text(announcement: Dict[str, Any], course_name: str) -> List[Dict[str, Any]]:
    """
    De-noised task extractor: Analyzes announcement as a single unit and creates at most
    ONE high-confidence actionable task only if an explicit deadline or mandatory action is present.
    """
    aid = announcement.get("id", str(uuid.uuid4()))
    cid = announcement.get("course_id")
    title = announcement.get("title", "")
    content = announcement.get("markdown_body") or announcement.get("raw_html") or ""

    lines = [p.strip() for p in re.split(r'\n+|\.\s+', content) if len(p.strip()) > 10]
    best_action_line = None
    found_date_str = None

    # Check whole announcement text (title + body) for high priority / urgency flags
    full_text_lower = f"{title} {content}".lower()
    is_high_priority = any(w in full_text_lower for w in ["urgent", "penalty", "penalties", "graded", "mandatory", "must submit", "required"])

    # Scan lines for action items and deadlines
    for line in lines:
        has_action = any(re.search(kw, line, re.IGNORECASE) for kw in ACTION_KEYWORDS)
        if not has_action:
            continue

        for pattern in DATE_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match and len(match.group(0).strip()) > 2:
                found_date_str = match.group(0).strip()
                break

        line_lower = line.lower()
        has_explicit_due = any(w in line_lower for w in ["due", "submit", "submission", "deadline", "hand in", "deliverable"])

        if has_explicit_due or found_date_str or any(w in line_lower for w in ["urgent", "penalty", "mandatory", "must submit"]):
            best_action_line = line
            break

    # Only create a task if an explicit actionable requirement is found
    if not best_action_line:
        # Check if announcement title itself contains strong deadline signal
        title_lower = title.lower()
        if any(w in title_lower for w in ["due", "deadline", "submission", "assignment", "deliverable"]):
            best_action_line = content[:150] if content else title
        else:
            return []

    # Clean title
    clean_line = re.sub(r'[*_#`]', '', best_action_line).strip()
    if len(clean_line) > 80:
        clean_line = clean_line[:77] + "..."

    task_title = f"{course_name}: {title}" if len(title) > 5 else f"{course_name}: {clean_line}"
    task_id = f"ann_task_{aid}"
    desc = f"Announcement: \"{title}\"\n\nAction Item:\n\"{best_action_line}\""
    if found_date_str:
        desc += f"\n\nDetected Deadline: {found_date_str}"

    priority = "high" if is_high_priority else "medium"

    db.upsert_task(
        tid=task_id,
        cid=cid,
        title=task_title,
        description=desc,
        due_date=None,
        source_type="announcement",
        source_id=aid,
        priority=priority
    )

    return [{
        "id": task_id,
        "title": task_title,
        "context": best_action_line,
        "priority": priority
    }]

def extract_study_task(course_id: str, course_name: str, note_title: str, file_path: str) -> Optional[Dict[str, Any]]:
    """Creates a study/review action item for newly converted lecture notes."""
    tid = f"study_{hashlib.md5(file_path.encode()).hexdigest()[:12]}"
    task_title = f"📖 Review: {note_title}"
    desc = f"Study material for {course_name}.\nLocation: {file_path}"

    db.upsert_task(
        tid=tid,
        cid=course_id,
        title=f"{course_name}: {task_title}",
        description=desc,
        due_date=None,
        source_type="study",
        source_id=file_path,
        priority="low"
    )
    return {"id": tid, "title": task_title, "source_type": "study"}

def run_task_extraction_for_course(course: Dict[str, Any], tree_items: List[Dict[str, Any]], announcements: List[Dict[str, Any]]) -> Dict[str, int]:
    """Runs full task discovery across both assignment trees and course announcements."""
    cid = course["id"]
    cname = course["name"]
    stats = {"assignment_tasks": 0, "announcement_tasks": 0}

    # 1. Official assignment deadlines
    for item in tree_items:
        if item.get("type") == "assignment":
            extract_assignment_task(item, cid, cname)
            stats["assignment_tasks"] += 1

    # 2. Announcement tasks
    for ann in announcements:
        ann_tasks = extract_tasks_from_announcement_text(ann, cname)
        stats["announcement_tasks"] += len(ann_tasks)

    return stats
