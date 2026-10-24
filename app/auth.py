import time
import threading
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any

from playwright.sync_api import sync_playwright

from . import config

_login_lock = threading.Lock()


def get_browser_channel_candidates() -> List[Optional[str]]:
    """
    Returns ordered list of Playwright browser channels to try.
    On Windows, prioritizes built-in Microsoft Edge ('msedge') and Google Chrome ('chrome')
    so users do not need to download a separate 300MB Playwright Chromium binary.
    """
    pref = (config.BROWSER_CHANNEL or "auto").lower()
    if pref == "msedge":
        return ["msedge", "chrome", None]
    if pref == "chrome":
        return ["chrome", "msedge", None]
    if pref == "chromium":
        return [None, "msedge", "chrome"]

    # 'auto' mode
    if config.IS_WINDOWS:
        return ["msedge", "chrome", None]
    return [None, "chrome", "msedge"]


def launch_browser_context(
    playwright_instance,
    headless: bool = True,
    viewport: Optional[Dict[str, int]] = None,
    extra_args: Optional[List[str]] = None,
    logger=None,
):
    """
    Launches a persistent Chromium-based browser context using the first available channel
    (Microsoft Edge, Google Chrome, or bundled Playwright Chromium).
    """
    profile_dir = Path(config.PROFILE_PATH)
    profile_dir.mkdir(parents=True, exist_ok=True)

    candidates = get_browser_channel_candidates()
    last_error = None

    kwargs: Dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
    }
    if viewport:
        kwargs["viewport"] = viewport
    if extra_args:
        kwargs["args"] = extra_args

    for channel in candidates:
        try:
            call_kwargs = dict(kwargs)
            if channel is not None:
                call_kwargs["channel"] = channel
            ctx = playwright_instance.chromium.launch_persistent_context(**call_kwargs)
            return ctx
        except Exception as e:
            last_error = e
            continue

    # If all candidates failed, raise the last error with a helpful message
    raise RuntimeError(
        f"Could not launch Microsoft Edge, Google Chrome, or Chromium ({last_error}). "
        "Please ensure Microsoft Edge or Google Chrome is installed."
    )


def is_session_valid(page) -> bool:
    """Verifies whether the current Playwright page session is authenticated with Blackboard."""
    try:
        res = page.request.get(f"{config.BASE_URL}/learn/api/v1/users/me")
        return res.status == 200
    except Exception:
        return False


def check_login_status() -> Tuple[bool, str]:
    """Headless check of persistent browser session validity."""
    if not Path(config.PROFILE_PATH).exists():
        return False, "No saved session profile found. Please log in."

    try:
        with sync_playwright() as p:
            ctx = launch_browser_context(p, headless=True)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            valid = is_session_valid(page)
            ctx.close()
            if valid:
                return True, "Authenticated session active."
            return False, "Saved session has expired. Re-login required."
    except Exception as e:
        return False, f"Auth check failed: {e}"


def is_login_active() -> bool:
    return _login_lock.locked()


def launch_interactive_login(timeout_seconds: int = 300, logger=print) -> bool:
    """
    Opens an interactive browser window (Edge/Chrome/Chromium) for the user to enter
    university SSO credentials and complete 2FA on their phone.
    """
    if not _login_lock.acquire(blocking=False):
        logger("⚠️ Login window is already open or in progress.")
        return False

    try:
        config.load_persisted_settings()
        base_url = config.BASE_URL
        logger(f"Launching interactive browser login window for {base_url}...")
        logger("Please log in using your university credentials and complete 2-Factor Authentication.")

        with sync_playwright() as p:
            try:
                ctx = launch_browser_context(
                    p,
                    headless=False,
                    viewport={"width": 1280, "height": 850},
                    extra_args=["--disable-blink-features=AutomationControlled"],
                    logger=logger,
                )
            except Exception as e:
                logger(f"❌ Could not launch browser profile (it may already be in use): {e}")
                return False

            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(f"{base_url}/ultra/course")
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

