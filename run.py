#!/usr/bin/env python3
"""
run.py - Main CLI and Desktop App entry point for Blackboard Automate.
Usage:
    python run.py                   # Starts server and opens desktop app window / browser
    python run.py --app-window      # Opens in dedicated native-style desktop window
    python run.py --sync-only       # Runs one-time crawler, download & markdown conversion
    python run.py --login           # Launches interactive browser window for 2FA login
    python run.py --convert-all     # Scans and converts any unconverted PDFs to Markdown
"""

import os
import sys
import socket
import argparse
import webbrowser
import threading
import time
import multiprocessing
import urllib.request


def _ensure_stdio():
    """
    When packaged as a windowed/noconsole Windows .exe via PyInstaller,
    sys.stdout and sys.stderr are None, which causes uvicorn's logging formatter
    to crash on `.isatty()`. Redirect None streams to a log file.
    """
    if sys.stdout is None or sys.stderr is None:
        try:
            from app.config import DATA_DIR
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            log_file = open(DATA_DIR / "blackboard_app.log", "a", encoding="utf-8", buffering=1)
            if sys.stdout is None:
                sys.stdout = log_file
            if sys.stderr is None:
                sys.stderr = log_file
        except Exception:
            devnull = open(os.devnull, "w")
            if sys.stdout is None:
                sys.stdout = devnull
            if sys.stderr is None:
                sys.stderr = devnull


def _is_existing_bb_server_running(host: str, port: int) -> bool:
    """Checks if an instance of Blackboard Automate is already serving on host:port."""
    try:
        req = urllib.request.urlopen(f"http://{host}:{port}/api/stats", timeout=1.0)
        return req.status == 200
    except Exception:
        return False


def _find_available_port(host: str, preferred_port: int) -> int:
    """Returns preferred_port if available, otherwise finds the next open port."""
    for p in range(preferred_port, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return preferred_port


def _wait_for_server(url: str, timeout: float = 12.0) -> bool:
    """Waits until the local FastAPI server is ready to accept connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.urlopen(f"{url}/api/stats", timeout=0.8)
            if req.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.15)
    return False


def main():
    multiprocessing.freeze_support()
    _ensure_stdio()

    parser = argparse.ArgumentParser(description="Blackboard Automate: Sync, Markdown Converter & To-Do Dashboard")
    parser.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Port to bind (default: 8000)")
    parser.add_argument("--sync-only", action="store_true", help="Run sync directly without starting web dashboard")
    parser.add_argument("--login", action="store_true", help="Launch interactive 2FA browser login")
    parser.add_argument("--convert-all", action="store_true", help="Convert all existing unconverted PDFs to Markdown")
    parser.add_argument("--coverage", "-c", action="store_true", help="Analyze downloaded markdown notes and print study coverage")
    parser.add_argument("--course", default=None, help="Filter study coverage to a specific course code or name")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser or app window on startup")
    parser.add_argument("--app-window", action="store_true", help="Force opening in a dedicated native-looking desktop window")
    parser.add_argument("--browser-tab", action="store_true", help="Open in default web browser tab instead of dedicated app window")
    parser.add_argument("--download-mp4", action="store_true", help="Allow downloading MP4 video files (skipped by default)")

    args = parser.parse_args()

    if args.download_mp4:
        os.environ["DOWNLOAD_MP4"] = "true"
        import app.config
        app.config.SKIP_MP4_DOWNLOADS = False

    # Mode 1: Interactive Login
    if args.login:
        from app.auth import launch_interactive_login
        success = launch_interactive_login()
        sys.exit(0 if success else 1)

    # Mode 2: Sync Only
    if args.sync_only:
        from app.sync import run_sync
        res = run_sync()
        sys.exit(0 if res.get("status") == "success" else 1)

    # Mode 3: Convert All Unconverted Files
    if args.convert_all:
        from app.converter import convert_all_pending_files
        count = convert_all_pending_files()
        print(f"✅ Converted {count} pending PDF(s) to Markdown.")
        sys.exit(0)

    # Mode 4: Study Coverage & Syllabus Analyzer
    if args.coverage:
        from app.coverage import print_cli_coverage
        print_cli_coverage(args.course)
        sys.exit(0)

    # Mode 5: Desktop App / Web Dashboard Server (Default)
    import uvicorn
    from app.config import HOST, PORT, IS_WINDOWS, IS_FROZEN
    from app.server import app as fastapi_app
    from app.desktop import launch_desktop_window

    host = args.host or HOST
    preferred_port = args.port or PORT

    # If an instance of Blackboard Automate is already running on preferred_port, just open its window
    if _is_existing_bb_server_running(host, preferred_port):
        url = f"http://{host}:{preferred_port}"
        print(f"ℹ️ Blackboard Automate server is already running at {url}. Opening window...")
        if not args.no_browser:
            if args.browser_tab:
                webbrowser.open(url)
            else:
                launch_desktop_window(url)
        sys.exit(0)

    port = _find_available_port(host, preferred_port)
    url = f"http://{host}:{port}"

    print("=" * 65)
    print("🎓 BLACKBOARD AUTOMATE DASHBOARD")
    print("=" * 65)
    print(f"🚀 App Interface : {url}")
    print(f"📅 Calendar Feed : {url}/calendar/deadlines.ics")
    print(f"⚡ Live API docs : {url}/docs")
    print("=" * 65)

    use_desktop_window = (
        not args.no_browser
        and not args.browser_tab
        and (args.app_window or IS_WINDOWS or IS_FROZEN)
    )

    if use_desktop_window:
        # Run Uvicorn in a background thread and block main thread on the desktop window
        config_uv = uvicorn.Config(fastapi_app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config_uv)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()

        _wait_for_server(url, timeout=12.0)
        used_blocking_window = launch_desktop_window(url)

        if used_blocking_window:
            # User closed the desktop window -> shut down server cleanly
            server.should_exit = True
            server_thread.join(timeout=3.0)
            sys.exit(0)
        else:
            # Fell back to opening a browser tab -> keep server thread alive
            try:
                while server_thread.is_alive():
                    time.sleep(1.0)
            except KeyboardInterrupt:
                server.should_exit = True
    else:
        if not args.no_browser:
            def open_browser():
                _wait_for_server(url, timeout=10.0)
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
            threading.Thread(target=open_browser, daemon=True).start()

        uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

