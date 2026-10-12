import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from . import database as db
from .config import DOWNLOAD_DIR

def format_iso_to_ical_utc(iso_str: str) -> str:
    """Converts ISO 8601 string (e.g. 2026-10-23T22:00:00.000Z) to iCalendar UTC format (20261023T220000Z)."""
    if not iso_str:
        return ""
    clean = iso_str.replace("-", "").replace(":", "").replace(".000", "")
    if "T" in clean and not clean.endswith("Z"):
        clean += "Z"
    return clean

def generate_deadlines_ics() -> str:
    """Generates an RFC 5545 VCALENDAR feed string containing all pending coursework deadlines."""
    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tasks = db.get_tasks(completed=False)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Blackboard Automate Deadlines//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Blackboard Coursework Deadlines",
        "X-WR-TIMEZONE:UTC",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H"
    ]

    for t in tasks:
        due = t.get("due_date")
        if not due:
            continue

        dt_val = format_iso_to_ical_utc(due)
        if not dt_val:
            continue

        uid = f"{t['id']}@blackboard.automate"
        cname = t.get("course_name") or "Course"
        title = t.get("title") or "Task"
        desc = (t.get("description") or "").replace("\r\n", "\\n").replace("\n", "\\n").replace(",", "\\,")

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_str}",
            f"DTSTART:{dt_val}",
            f"DTEND:{dt_val}",
            f"SUMMARY:🎯 {title}",
            f"DESCRIPTION:{desc}",
            "LOCATION:Blackboard",
            "STATUS:CONFIRMED",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "DESCRIPTION:Deadline in 2 days!",
            "TRIGGER:-P2D",
            "END:VALARM",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "DESCRIPTION:Deadline in 4 hours!",
            "TRIGGER:-PT4H",
            "END:VALARM",
            "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)

def generate_timetable_ics(events: List[Dict[str, Any]]) -> str:
    """Generates an RFC 5545 VCALENDAR feed string for semester lectures and labs."""
    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Blackboard Automate Timetable//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Blackboard Timetable",
        "X-WR-TIMEZONE:Europe/Dublin"
    ]

    for ev in events:
        sr, er = ev.get("startDate"), ev.get("endDate")
        if not sr or not er:
            continue
        ds = format_iso_to_ical_utc(sr)
        de = format_iso_to_ical_utc(er)
        uid = f"{uuid.uuid4()}@timetable.blackboard"
        summary = (ev.get("title") or "Class").replace(",", "\\,")
        desc = (ev.get("description") or "").replace("\n", "\\n").replace(",", "\\,")
        loc = (ev.get("location") or "").replace(",", "\\,")

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_str}",
            f"DTSTART:{ds}",
            f"DTEND:{de}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            f"LOCATION:{loc}",
            "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)

def save_calendars_to_disk(timetable_events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    """Writes calendar files to the download directory for local subscription or manual import."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}

    deadlines_content = generate_deadlines_ics()
    deadlines_file = DOWNLOAD_DIR / "Assignments_and_Deadlines.ics"
    with open(deadlines_file, "w", encoding="utf-8") as f:
        f.write(deadlines_content)
    paths["deadlines"] = str(deadlines_file)

    if timetable_events:
        tt_content = generate_timetable_ics(timetable_events)
        tt_file = DOWNLOAD_DIR / "Semester_Timetable.ics"
        with open(tt_file, "w", encoding="utf-8") as f:
            f.write(tt_content)
        paths["timetable"] = str(tt_file)

    return paths
