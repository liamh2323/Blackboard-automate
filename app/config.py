import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

IS_FROZEN = getattr(sys, "frozen", False)
IS_WINDOWS = sys.platform == "win32"

if IS_FROZEN:
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    EXE_DIR = Path(sys.executable).resolve().parent
    # Use portable data folder next to .exe if it already exists, otherwise LOCALAPPDATA on Windows
    if (EXE_DIR / "data").exists() or not IS_WINDOWS:
        BASE_DIR = EXE_DIR
    else:
        local_app_data = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        BASE_DIR = Path(local_app_data) / "BlackboardAutomate"
else:
    RESOURCE_DIR = Path(__file__).resolve().parent.parent
    BASE_DIR = RESOURCE_DIR

# Try to load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        load_dotenv()
except ImportError:
    pass

# Static frontend directory (works in both normal mode and PyInstaller _MEIPASS)
_candidate_static = RESOURCE_DIR / "app" / "static"
STATIC_DIR = _candidate_static if _candidate_static.exists() else (Path(__file__).resolve().parent / "static")

# Blackboard Settings
BASE_URL = os.getenv("BLACKBOARD_BASE_URL", "https://tcd.blackboard.com").rstrip("/")
SAML_PATH = os.getenv("BLACKBOARD_SAML_PATH", "/auth-saml/saml/login?apId=_3413_1&redirectUrl=https%3A%2F%2Ftcd.blackboard.com%2Fultra%2Fcourse")
PROFILE_PATH = os.path.expanduser(os.getenv("BROWSER_PROFILE_PATH", "~/.blackboard_playwright_profile"))
TERM_FILTER = os.getenv("CURRENT_TERM_FILTER", "")
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "auto").lower()  # 'auto', 'msedge', 'chrome', 'chromium'

# Default download directory: on frozen Windows builds default to ~/Downloads/Blackboard for easy access
if IS_FROZEN and IS_WINDOWS and not os.getenv("DOWNLOAD_DIR"):
    _default_dl = Path.home() / "Downloads" / "Blackboard"
else:
    _default_dl = BASE_DIR / "downloads"

# Directories
DOWNLOAD_DIR = Path(os.path.expanduser(os.getenv("DOWNLOAD_DIR", str(_default_dl)))).resolve()
DATA_DIR = Path(os.path.expanduser(os.getenv("DATA_DIR", str(BASE_DIR / "data")))).resolve()
DATABASE_PATH = DATA_DIR / "blackboard.db"

# Server & Sync Settings
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
SYNC_INTERVAL_HOURS = float(os.getenv("SYNC_INTERVAL_HOURS", "4"))
ENABLE_CALENDAR = os.getenv("ENABLE_CALENDAR_SYNC", "true").lower() in ("true", "1", "yes")

# Download & File Filter Settings
# By default, MP4 videos are skipped during sync to prevent long download times
SKIP_MP4_DOWNLOADS = os.getenv("SKIP_MP4_DOWNLOADS", "true").lower() in ("true", "1", "yes")
if os.getenv("DOWNLOAD_VIDEOS", "").lower() in ("true", "1", "yes") or os.getenv("DOWNLOAD_MP4", "").lower() in ("true", "1", "yes"):
    SKIP_MP4_DOWNLOADS = False

# Optional AI Task Extraction
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()  # 'gemini', 'openai', 'ollama', 'none'
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Ensure required runtime directories exist
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


def load_persisted_settings():
    """Loads user-configured settings from the SQLite app_settings table into runtime config."""
    global DOWNLOAD_DIR, BASE_URL, TERM_FILTER, SKIP_MP4_DOWNLOADS, BROWSER_CHANNEL
    try:
        from . import database as db
        saved_dl = db.get_setting("user_download_dir")
        if saved_dl:
            p = Path(os.path.expanduser(saved_dl)).resolve()
            p.mkdir(parents=True, exist_ok=True)
            DOWNLOAD_DIR = p

        saved_url = db.get_setting("user_blackboard_url")
        if saved_url:
            BASE_URL = saved_url.strip().rstrip("/")

        saved_term = db.get_setting("user_term_filter")
        if saved_term is not None:
            TERM_FILTER = saved_term.strip()

        saved_skip_mp4 = db.get_setting("user_skip_mp4")
        if saved_skip_mp4 is not None:
            SKIP_MP4_DOWNLOADS = str(saved_skip_mp4).lower() in ("true", "1", "yes")

        saved_channel = db.get_setting("user_browser_channel")
        if saved_channel:
            BROWSER_CHANNEL = saved_channel.strip().lower()
    except Exception:
        pass


def get_runtime_settings() -> Dict[str, Any]:
    """Returns current user-configurable application settings."""
    load_persisted_settings()
    return {
        "download_dir": str(DOWNLOAD_DIR),
        "blackboard_url": BASE_URL,
        "term_filter": TERM_FILTER,
        "skip_mp4_downloads": SKIP_MP4_DOWNLOADS,
        "browser_channel": BROWSER_CHANNEL,
        "is_windows": IS_WINDOWS,
        "is_frozen": IS_FROZEN,
    }


def update_runtime_settings(
    download_dir: Optional[str] = None,
    blackboard_url: Optional[str] = None,
    term_filter: Optional[str] = None,
    skip_mp4_downloads: Optional[bool] = None,
    browser_channel: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates and persists user settings in SQLite and applies them immediately."""
    global DOWNLOAD_DIR, BASE_URL, TERM_FILTER, SKIP_MP4_DOWNLOADS, BROWSER_CHANNEL
    from . import database as db

    if download_dir is not None and download_dir.strip():
        target = Path(os.path.expanduser(download_dir.strip())).resolve()
        target.mkdir(parents=True, exist_ok=True)
        DOWNLOAD_DIR = target
        db.set_setting("user_download_dir", str(target))

    if blackboard_url is not None and blackboard_url.strip():
        BASE_URL = blackboard_url.strip().rstrip("/")
        db.set_setting("user_blackboard_url", BASE_URL)

    if term_filter is not None:
        TERM_FILTER = term_filter.strip()
        db.set_setting("user_term_filter", TERM_FILTER)

    if skip_mp4_downloads is not None:
        SKIP_MP4_DOWNLOADS = bool(skip_mp4_downloads)
        db.set_setting("user_skip_mp4", "true" if SKIP_MP4_DOWNLOADS else "false")

    if browser_channel is not None and browser_channel.strip():
        BROWSER_CHANNEL = browser_channel.strip().lower()
        db.set_setting("user_browser_channel", BROWSER_CHANNEL)

    return get_runtime_settings()

