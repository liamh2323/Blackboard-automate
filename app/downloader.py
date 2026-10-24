import os
import re
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from . import database as db
from . import config
from .converter import convert_file_record

def is_mp4_file(filename: str, mime_type: Optional[str] = None, url: Optional[str] = None) -> bool:
    """Checks whether a file represents an MP4 video based on its extension, MIME type, or URL."""
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in (".mp4", ".m4v"):
            return True
    if mime_type and any(m in mime_type.lower() for m in ["video/mp4", "video/x-m4v"]):
        return True
    if url:
        url_path = url.split("?")[0].lower()
        if url_path.endswith(".mp4") or url_path.endswith(".m4v"):
            return True
    return False

def sanitize_name(name: str) -> str:
    """Removes invalid filesystem characters and trims whitespace."""
    clean = re.sub(r'[/\\:*?"<>|]', '_', name)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:100]

def get_file_hash(filepath: Path) -> str:
    """Computes SHA-256 hash of a file on disk."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def index_existing_files(base_folder: Path) -> Dict[str, Dict]:
    """Indexes local files by lowercased filename, filesize, and SHA-256 hash for fast deduplication."""
    index = {"by_name": {}, "by_size": {}, "by_hash": {}}
    if not base_folder.exists():
        return index

    for root, _, files in os.walk(base_folder):
        for f in files:
            if f.startswith(".") or f.endswith(".md"):
                continue
            full_path = Path(root) / f
            try:
                size = full_path.stat().st_size
                index["by_name"][f.lower()] = full_path
                index["by_size"].setdefault(size, []).append(full_path)
                if size < 100 * 1024 * 1024:
                    index["by_hash"][get_file_hash(full_path)] = full_path
            except Exception:
                pass
    return index

LECTURE_NAME_PATTERNS = [
    re.compile(r"\bslides?\b"),           # "Week 4 Slides", "slides.pdf"
    re.compile(r"\blec[\s_-]*\d+"),       # "lec3", "Lec_03"
    re.compile(r"(?:^|[\s_-])l\d{1,2}\b"),  # "BUU22570 - L1", "CS101_L04"
    re.compile(r"\bwk[\s_-]*\d+"),        # "wk2", "Wk_05"
]
# Note: a bare "lecture" is deliberately not matched here, since readings are often
# titled per lecture (e.g. "Lecture 1 - Economist article"). The folder-level rule
# further down still routes "lecture" paths to lectures/.

def looks_like_lecture(text: str) -> bool:
    """True if a filename or item title clearly identifies lecture slides."""
    return any(p.search(text) for p in LECTURE_NAME_PATTERNS)

def choose_destination_folder(course_folder: Path, remote_path: str, filename: str) -> Path:
    """Sorts file into logical subcategory folder based on path and file name."""
    lp = (remote_path or "").lower()
    lf = filename.lower()
    # The last path segment is the item's own title (e.g. "Week 4 Slides"), which is
    # more specific than its parent folders (e.g. "Readings & Slides").
    item_title = lp.rsplit(">", 1)[-1].strip()

    if "lab" in lp or "lab" in lf:
        target = course_folder / "labs"
    elif "tutorial" in lp or "tutorial" in lf:
        target = course_folder / "tutorials"
    elif looks_like_lecture(lf) or looks_like_lecture(item_title):
        target = course_folder / "lectures"
    elif any(k in lp for k in ["assignment", "assessment", "coursework"]) or any(k in lf for k in ["assignment", "homework", "task"]):
        target = course_folder / "assignments"
    elif any(k in lp for k in ["reading", "paper", "book", "resource", "bibliography"]):
        target = course_folder / "readings"
    elif any(k in lp for k in ["exam", "past paper", "solution", "test"]) or any(k in lf for k in ["exam", "sample-exam"]):
        target = course_folder / "exams"
    elif any(k in lp for k in ["lecture", "slide", "week", "topic", "notes", "module"]):
        target = course_folder / "lectures"
    else:
        target = course_folder

    target.mkdir(parents=True, exist_ok=True)
    return target

def download_and_process_file(page, base_url: str, course_id: str, course_folder: Path,
                             item: Dict[str, Any], existing_index: Dict[str, Dict],
                             logger=print, skip_mp4: Optional[bool] = None) -> Tuple[bool, str]:
    """
    Downloads a single file from Blackboard, applies deduplication, registers in DB,
    and runs PDF to Markdown conversion.
    Returns: (is_new_download, status_message)
    """
    fname = item.get("fileName")
    furl = item.get("permanentUrl")
    fsize = item.get("fileSize")
    rpath = item.get("path", "")
    mime_type = item.get("mimeType")
    item_id = item.get("id") or hashlib.md5(f"{course_id}_{fname}_{furl}".encode()).hexdigest()

    if not fname or not furl:
        return False, "skipped_missing_info"

    clean_fname = sanitize_name(fname)

    # Check if MP4 video download should be skipped
    should_skip = config.SKIP_MP4_DOWNLOADS if skip_mp4 is None else skip_mp4
    if should_skip and is_mp4_file(clean_fname, mime_type, furl):
        logger(f"  ⏭️ Skipped MP4 video: {clean_fname}")
        return False, "skipped_mp4"

    dest_dir = choose_destination_folder(course_folder, rpath, clean_fname)
    dest_file = dest_dir / clean_fname

    # Tier 1 Deduplication: match name & size
    if clean_fname.lower() in existing_index["by_name"]:
        existing_path = existing_index["by_name"][clean_fname.lower()]
        if fsize and existing_path.exists() and existing_path.stat().st_size == fsize:
            # Register in database if not already
            db.upsert_file(
                fid=item_id, cid=course_id, remote_path=rpath,
                filename=clean_fname, local_path=str(existing_path),
                file_size=fsize, content_hash=None
            )
            return False, "deduped_tier1"

    # Fetch file bytes from Blackboard
    try:
        full_dl = furl if furl.startswith("http") else f"{base_url}{furl}"
        res = page.request.get(full_dl)
        if res.status != 200:
            return False, f"http_{res.status}"
        body = res.body()
    except Exception as e:
        return False, f"error_{e}"

    dl_hash = hashlib.sha256(body).hexdigest()

    # Tier 2 Deduplication: match SHA-256 hash
    if dl_hash in existing_index["by_hash"]:
        existing_path = existing_index["by_hash"][dl_hash]
        db.upsert_file(
            fid=item_id, cid=course_id, remote_path=rpath,
            filename=clean_fname, local_path=str(existing_path),
            file_size=len(body), content_hash=dl_hash
        )
        return False, "deduped_tier2"

    # Save to disk
    try:
        with open(dest_file, "wb") as out_f:
            out_f.write(body)
    except Exception as e:
        return False, f"write_error_{e}"

    # Index newly downloaded file
    existing_index["by_name"][clean_fname.lower()] = dest_file
    existing_index["by_hash"][dl_hash] = dest_file

    # Save in DB
    is_new = db.upsert_file(
        fid=item_id, cid=course_id, remote_path=rpath,
        filename=clean_fname, local_path=str(dest_file),
        file_size=len(body), content_hash=dl_hash
    )

    # Convert to Markdown automatically if applicable
    from .converter import SUPPORTED_CONVERTIBLE_EXTENSIONS
    if dest_file.suffix.lower() in SUPPORTED_CONVERTIBLE_EXTENSIONS:
        file_record = {
            "id": item_id,
            "local_path": str(dest_file)
        }
        convert_file_record(file_record)

    logger(f"  📥 Downloaded & indexed: {clean_fname}")
    return True, "downloaded"
