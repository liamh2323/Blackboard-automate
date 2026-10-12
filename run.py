#!/usr/bin/env python3
"""
run.py - Main CLI entry point for Blackboard Automate.
Usage:
    python run.py                   # Starts web dashboard server and opens in browser
    python run.py --sync-only       # Runs one-time crawler, download & markdown conversion
    python run.py --login           # Launches interactive Chromium window for 2FA login
    python run.py --convert-all     # Scans and converts any unconverted PDFs to Markdown
"""

import sys
import argparse
import webbrowser
import threading
import time

def main():
    parser = argparse.ArgumentParser(description="Blackboard Automate: Sync, Markdown Converter & To-Do Dashboard")
    parser.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Port to bind (default: 8000)")
    parser.add_argument("--sync-only", action="store_true", help="Run sync directly without starting web dashboard")
    parser.add_argument("--login", action="store_true", help="Launch interactive 2FA browser login")
    parser.add_argument("--convert-all", action="store_true", help="Convert all existing unconverted PDFs to Markdown")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser on dashboard startup")

    args = parser.parse_args()

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

    # Mode 4: Web Dashboard Server (Default)
    import uvicorn
    from app.config import HOST, PORT

    host = args.host or HOST
    port = args.port or PORT
    url = f"http://{host}:{port}"

    print("=" * 65)
    print("🎓 BLACKBOARD AUTOMATE DASHBOARD")
    print("=" * 65)
    print(f"🚀 Web Interface : {url}")
    print(f"📅 Calendar Feed : {url}/calendar/deadlines.ics")
    print(f"⚡ Live API docs : {url}/docs")
    print("=" * 65)

    if not args.no_browser:
        def open_browser():
            time.sleep(1.2)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run("app.server:app", host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()
