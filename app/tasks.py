import re
import uuid
import json
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
    """Uses regex & linguistic heuristic matching to detect action items from announcement text."""
    aid = announcement.get("id", str(uuid.uuid4()))
    cid = announcement.get("course_id")
    title = announcement.get("title", "")
    content = announcement.get("markdown_body") or announcement.get("raw_html") or ""

    lines = [p.strip() for p in re.split(r'\n+|\.\s+', content) if len(p.strip()) > 10]
    extracted = []

    for idx, line in enumerate(lines):
        has_action = any(re.search(kw, line, re.IGNORECASE) for kw in ACTION_KEYWORDS)
        if not has_action:
            continue

        # Check for date or deadline reference
        found_date_str = None
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match and len(match.group(0).strip()) > 2:
                found_date_str = match.group(0).strip()
                break

        # If action + date or explicit "due" phrase is present
        if has_action and (found_date_str or "due" in line.lower() or "submit" in line.lower() or "deadline" in line.lower()):
            clean_title = re.sub(r'[*_#`]', '', line).strip()
            if len(clean_title) > 90:
                clean_title = clean_title[:87] + "..."

            task_id = f"ann_task_{aid}_{idx}"
            desc = f"Extracted from announcement: \"{title}\"\n\nContext:\n\"{line}\""
            if found_date_str:
                desc += f"\n\nDetected deadline: {found_date_str}"

            # Guess priority
            priority = "high" if any(w in line.lower() for w in ["urgent", "penalty", "graded", "mandatory", "must submit"]) else "medium"

            db.upsert_task(
                tid=task_id,
                cid=cid,
                title=f"{course_name}: {clean_title}",
                description=desc,
                due_date=None, # Human readable date is preserved in description
                source_type="announcement",
                source_id=aid,
                priority=priority
            )
            extracted.append({
                "id": task_id,
                "title": f"{course_name}: {clean_title}",
                "context": line,
                "priority": priority
            })

    return extracted

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
