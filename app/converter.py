import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from bs4 import BeautifulSoup
import markdownify

from . import database as db
from .config import BASE_DIR

# Ensure markitdown package from local repo is on sys.path
MARKITDOWN_SRC = BASE_DIR / "markitdown" / "packages" / "markitdown" / "src"
if MARKITDOWN_SRC.exists() and str(MARKITDOWN_SRC) not in sys.path:
    sys.path.insert(0, str(MARKITDOWN_SRC))

try:
    from markitdown import MarkItDown
    _md_converter = MarkItDown()
except Exception as e:
    _md_converter = None

def html_to_markdown(html_content: str) -> str:
    """Converts raw HTML (such as announcements or description fields) to clean Markdown."""
    if not html_content or not html_content.strip():
        return ""
    try:
        # Pre-clean HTML with BeautifulSoup to remove scripts/styles
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        cleaned_html = str(soup)
        md = markdownify.markdownify(cleaned_html, heading_style="ATX", autolinks=True)
        return md.strip()
    except Exception:
        # Fallback to plain text if markdownify encounters malformed tokens
        return BeautifulSoup(html_content, "html.parser").get_text().strip()

def convert_pdf_to_markdown(pdf_path: Path, output_md_path: Optional[Path] = None) -> Optional[Path]:
    """
    Converts a PDF file to a Markdown document saved side-by-side.
    Uses MarkItDown with a pdfplumber fallback.
    """
    if not pdf_path.exists():
        return None

    if output_md_path is None:
        output_md_path = pdf_path.with_suffix(".md")

    # If markdown already exists and has content, avoid re-converting
    if output_md_path.exists() and output_md_path.stat().st_size > 0:
        return output_md_path

    markdown_text = None

    # Primary converter: MarkItDown
    if _md_converter is not None:
        try:
            res = _md_converter.convert(str(pdf_path))
            markdown_text = res.text_content
        except Exception as e:
            markdown_text = None

    # Fallback converter: pdfplumber direct text extraction
    if not markdown_text:
        try:
            import pdfplumber
            pages_md = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for idx, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        pages_md.append(f"<!-- Page {idx + 1} -->\n{text.strip()}")
            if pages_md:
                markdown_text = f"# {pdf_path.stem}\n\n" + "\n\n---\n\n".join(pages_md)
        except Exception:
            pass

    if markdown_text and markdown_text.strip():
        try:
            output_md_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_md_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            return output_md_path
        except Exception:
            return None

    return None

def convert_file_record(file_row: Dict[str, Any]) -> bool:
    """Converts a database file record if it's a PDF and not yet converted."""
    local_path_str = file_row.get("local_path")
    if not local_path_str:
        return False

    local_path = Path(local_path_str)
    if not local_path.exists():
        return False

    if local_path.suffix.lower() == ".pdf":
        md_path = convert_pdf_to_markdown(local_path)
        if md_path:
            db.mark_file_converted(file_row["id"], str(md_path))
            return True

    return False

def convert_all_pending_files() -> int:
    """Finds all unconverted PDFs in the database and generates markdown for them."""
    pending = db.get_unconverted_files(limit=200)
    converted_count = 0
    for row in pending:
        if convert_file_record(row):
            converted_count += 1
    return converted_count
