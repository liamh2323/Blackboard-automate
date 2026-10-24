import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List

from . import config
from . import database as db


def _win_no_window_flags() -> int:
    """Returns subprocess creationflags to hide console flashes on Windows."""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def find_app_mode_browser() -> Optional[str]:
    """
    Finds Microsoft Edge or Google Chrome executable capable of running `--app=<url>`
    for a frameless native-style desktop window.
    """
    if sys.platform == "win32":
        prog_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        prog = os.environ.get("ProgramFiles", r"C:\Program Files")
        local_app = os.environ.get("LOCALAPPDATA", "")

        candidates = [
            os.path.join(prog_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(prog, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(local_app, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(prog, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(prog_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app, "Google", "Chrome", "Application", "chrome.exe"),
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                return path

        for cmd in ("msedge", "chrome"):
            found = shutil.which(cmd)
            if found:
                return found
    else:
        for cmd in ("microsoft-edge", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            found = shutil.which(cmd)
            if found:
                return found

    return None


def launch_desktop_window(url: str, title: str = "Blackboard Automate") -> bool:
    """
    Opens the application in a dedicated desktop window without browser tabs or address bar.
    Blocks until the user closes the window if running in standalone window mode.
    Returns True if a blocking desktop window was used, or False if it fell back to default browser.
    """
    # 1. Try pywebview (native WebView2 on Windows / Cocoa on macOS / GTK on Linux)
    try:
        import webview  # type: ignore
        window = webview.create_window(
            title=title,
            url=url,
            width=1280,
            height=840,
            min_size=(900, 620),
            text_select=True,
        )
        webview.start()
        return True
    except Exception:
        pass

    # 2. Try Edge / Chrome in standalone `--app` mode with dedicated profile so process lifetime matches window
    browser_exe = find_app_mode_browser()
    if browser_exe:
        try:
            ui_profile_dir = config.DATA_DIR / "desktop_ui_profile"
            ui_profile_dir.mkdir(parents=True, exist_ok=True)
            args = [
                browser_exe,
                f"--app={url}",
                f"--user-data-dir={ui_profile_dir}",
                "--window-size=1280,840",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
            ]
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_win_no_window_flags(),
            )
            proc.wait()
            return True
        except Exception:
            pass

    # 3. Fallback: open in user's default web browser
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return False


def open_folder_in_explorer(folder_path: str) -> Tuple[bool, str]:
    """Opens the specified directory in Windows File Explorer, macOS Finder, or Linux file manager."""
    target = Path(os.path.expanduser(folder_path)).resolve()
    target.mkdir(parents=True, exist_ok=True)

    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, str(target)
    except Exception as e:
        return False, str(e)


def pick_folder_dialog(initial_dir: Optional[str] = None) -> Optional[str]:
    """
    Opens a native OS folder selection dialog and returns the selected folder path,
    or None if cancelled.
    """
    start_dir = initial_dir or str(config.DOWNLOAD_DIR)

    # 1. If a pywebview window is active, use its native folder dialog
    try:
        import webview  # type: ignore
        if webview.windows:
            result = webview.windows[0].create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=start_dir
            )
            if result and len(result) > 0:
                return str(result[0])
    except Exception:
        pass

    # 2. Try tkinter filedialog
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=start_dir, title="Select Blackboard Download Folder")
        root.destroy()
        if selected:
            return str(Path(selected).resolve())
        return None
    except Exception:
        pass

    # 3. Windows PowerShell FolderBrowserDialog fallback (always available on Windows)
    if sys.platform == "win32":
        try:
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$f.Description = 'Select Blackboard Download Folder'; "
                f"$f.SelectedPath = '{start_dir.replace(chr(39), chr(39)*2)}'; "
                "$f.ShowNewFolderButton = $true; "
                "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=_win_no_window_flags(),
            )
            chosen = (res.stdout or "").strip()
            if chosen:
                return str(Path(chosen).resolve())
        except Exception:
            pass

    return None


def create_desktop_shortcut(force: bool = False) -> Tuple[bool, str]:
    """
    Creates a desktop shortcut ('Blackboard Automate') on Windows (or Linux).
    When force=False, runs only once on first launch.
    """
    try:
        db.init_db()
        if not force and db.get_setting("desktop_shortcut_created") == "true":
            return True, "Shortcut already initialized on first run."
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            if config.IS_FROZEN:
                target_path = str(Path(sys.executable).resolve())
                working_dir = str(Path(sys.executable).resolve().parent)
                arguments = ""
                icon_path = target_path
            else:
                bat_file = config.BASE_DIR / "Start-Windows.bat"
                if bat_file.exists():
                    target_path = str(bat_file.resolve())
                else:
                    target_path = str(Path(sys.executable).resolve())
                working_dir = str(config.BASE_DIR.resolve())
                arguments = "" if bat_file.exists() else f'"{config.BASE_DIR / "run.py"}"'
                ico_candidate = config.STATIC_DIR / "icon.ico"
                icon_path = str(ico_candidate.resolve()) if ico_candidate.exists() else target_path

            ps_cmd = f"""
$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopPath 'Blackboard Automate.lnk'
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = '{target_path.replace("'", "''")}'
$Shortcut.WorkingDirectory = '{working_dir.replace("'", "''")}'
$Shortcut.Description = 'Blackboard Automate - Sync, Notes & To-Do Dashboard'
"""
            if arguments:
                ps_cmd += f"$Shortcut.Arguments = '{arguments.replace(chr(39), chr(39)*2)}'\n"
            if icon_path:
                ps_cmd += f"$Shortcut.IconLocation = '{icon_path.replace(chr(39), chr(39)*2)}'\n"
            ps_cmd += "$Shortcut.Save()\nWrite-Output $ShortcutPath\n"

            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=_win_no_window_flags(),
            )
            if res.returncode == 0:
                shortcut_loc = (res.stdout or "").strip() or "Desktop\\Blackboard Automate.lnk"
                try:
                    db.set_setting("desktop_shortcut_created", "true")
                except Exception:
                    pass
                return True, f"Created Desktop shortcut: {shortcut_loc}"
            return False, f"Could not create shortcut: {(res.stderr or '').strip()}"
        except Exception as e:
            return False, f"Shortcut creation failed: {e}"
    else:
        # On Linux/macOS, only create if explicitly requested via force=True
        if not force:
            return False, "Automatic desktop shortcut is only enabled by default on Windows."
        try:
            desktop_dir = Path.home() / "Desktop"
            if not desktop_dir.exists():
                return False, "No ~/Desktop directory found."
            shortcut_file = desktop_dir / "Blackboard-Automate.desktop"
            exec_cmd = str(Path(sys.executable).resolve()) if config.IS_FROZEN else str((config.BASE_DIR / "bb").resolve())
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Blackboard Automate\n"
                "Comment=Blackboard Learn Ultra Sync & Academic Dashboard\n"
                f"Exec={exec_cmd}\n"
                f"Path={config.BASE_DIR}\n"
                "Terminal=false\n"
                "Categories=Education;Utility;\n"
            )
            shortcut_file.write_text(content, encoding="utf-8")
            shortcut_file.chmod(0o755)
            db.set_setting("desktop_shortcut_created", "true")
            return True, f"Created Desktop shortcut: {shortcut_file}"
        except Exception as e:
            return False, f"Shortcut creation failed: {e}"
