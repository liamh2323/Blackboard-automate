import os
import re
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from . import database as db
from .converter import convert_file_record

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

def choose_destination_folder(course_folder: Path, remote_path: str, filename: str) -> Path:
    """Sorts file into logical subcategory folder based on path and file name."""
    lp = (remote_path or "").lower()
    lf = filename.lower()

    if "lab" in lp or "lab" in lf:
        target = course_folder / "labs"
    elif "tutorial" in lp or "tutorial" in lf:
        target = course_folder / "tutorials"
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
                             logger=print) -> Tuple[bool, str]:
    """
    Downloads a single file from Blackboard, applies deduplication, registers in DB,
    and runs PDF to Markdown conversion.
    Returns: (is_new_download, status_message)
    """
    fname = item.get("fileName")
    furl = item.get("permanentUrl")
    fsize = item.get("fileSize")
    rpath = item.get("path", "")
    item_id = item.get("id") or hashlib.md5(f"{course_id}_{fname}_{furl}".encode()).hexdigest()

    if not fname or not furl:
        return False, "skipped_missing_info"

    clean_fname = sanitize_name(fname)
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

    # Convert to Markdown if it's a PDF
    if dest_file.suffix.lower() == ".pdf":
        file_record = {
            "id": item_id,
            "local_path": str(dest_file)
        }
        convert_file_record(file_record)

    logger(f"  📥 Downloaded & indexed: {clean_fname}")
    return True, "downloaded"
