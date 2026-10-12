import os
from pathlib import Path

# Try to load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

# Blackboard Settings
BASE_URL = os.getenv("BLACKBOARD_BASE_URL", "https://tcd.blackboard.com").rstrip("/")
SAML_PATH = os.getenv("BLACKBOARD_SAML_PATH", "/auth-saml/saml/login?apId=_3413_1&redirectUrl=https%3A%2F%2Ftcd.blackboard.com%2Fultra%2Fcourse")
PROFILE_PATH = os.path.expanduser(os.getenv("BROWSER_PROFILE_PATH", "~/.blackboard_playwright_profile"))
TERM_FILTER = os.getenv("CURRENT_TERM_FILTER", "")
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")

# Directories
DOWNLOAD_DIR = Path(os.path.expanduser(os.getenv("DOWNLOAD_DIR", str(BASE_DIR / "downloads")))).resolve()
DATA_DIR = Path(os.path.expanduser(os.getenv("DATA_DIR", str(BASE_DIR / "data")))).resolve()
DATABASE_PATH = DATA_DIR / "blackboard.db"

# Server & Sync Settings
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
SYNC_INTERVAL_HOURS = float(os.getenv("SYNC_INTERVAL_HOURS", "4"))
ENABLE_CALENDAR = os.getenv("ENABLE_CALENDAR_SYNC", "true").lower() in ("true", "1", "yes")

# Optional AI Task Extraction
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower() # 'gemini', 'openai', 'ollama', 'none'
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Ensure required runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
