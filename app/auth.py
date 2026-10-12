import time
from pathlib import Path
from typing import Tuple

from playwright.sync_api import sync_playwright

from .config import BASE_URL, PROFILE_PATH, SAML_PATH

def is_session_valid(page) -> bool:
    """Verifies whether the current Playwright page session is authenticated with Blackboard."""
    try:
        res = page.request.get(f"{BASE_URL}/learn/api/v1/users/me")
        return res.status == 200
    except Exception:
        return False

def check_login_status() -> Tuple[bool, str]:
    """Headless check of persistent browser session validity."""
    if not Path(PROFILE_PATH).exists():
        return False, "No saved session profile found. Please log in."

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_PATH,
                headless=True
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            valid = is_session_valid(page)
            ctx.close()
            if valid:
                return True, "Authenticated session active."
            return False, "Saved session has expired. Re-login required."
    except Exception as e:
        return False, f"Auth check failed: {e}"

import threading

_login_lock = threading.Lock()

def is_login_active() -> bool:
    return _login_lock.locked()

def launch_interactive_login(timeout_seconds: int = 300, logger=print) -> bool:
    """
    Opens an interactive Chromium window for the user to enter university SSO credentials
    and complete 2FA on their phone.
    """
    if not _login_lock.acquire(blocking=False):
        logger("⚠️ Login window is already open or in progress.")
        return False

    try:
        logger(f"Launching interactive browser login window for {BASE_URL}...")
        logger("Please log in using your university credentials and complete 2-Factor Authentication.")

        with sync_playwright() as p:
            try:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=PROFILE_PATH,
                    headless=False,
                    viewport={"width": 1280, "height": 850},
                    args=["--disable-blink-features=AutomationControlled"]
                )
            except Exception as e:
                logger(f"❌ Could not launch browser profile (it may already be in use): {e}")
                return False

            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(f"{BASE_URL}/ultra/course")
            except Exception:
                pass

            logged_in = False
            start_time = time.time()

            while time.time() - start_time < timeout_seconds:
                try:
                    curr_url = page.url
                    if ("ultra/course" in curr_url or "webapps" in curr_url) and "login" not in curr_url:
                        try:
                            page.wait_for_load_state("networkidle", timeout=2000)
                        except Exception:
                            pass
                        if is_session_valid(page):
                            logged_in = True
                            break
                except Exception:
                    # Page may have been closed by user
                    break
                time.sleep(1)

            try:
                ctx.close()
            except Exception:
                pass

            if logged_in:
                logger("✅ Authentication successful! Session profile saved.")
                return True
            else:
                logger("❌ Authentication timed out or was not completed.")
                return False
    finally:
        _login_lock.release()
