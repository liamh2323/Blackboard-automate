#!/usr/bin/env python3
"""
build_windows.py - Builds the standalone BlackboardAutomate.exe for Windows using PyInstaller.

Usage on Windows:
    pip install -r requirements.txt pyinstaller pywebview
    python build_windows.py
"""

import os
import sys
import math
import struct
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
ICON_PATH = ROOT_DIR / "app" / "static" / "icon.ico"


def generate_app_icon(target_path: Path = ICON_PATH) -> Path:
    """
    Generates a clean 64x64 32-bit BGRA Windows .ico file (dark indigo rounded badge
    with a gold mortarboard graduation cap) using only the Python standard library.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 64, 64
    pixels = bytearray(w * h * 4)

    cx, cy = 31.5, 31.5
    for y in range(h):
        # BMP in ICO is stored bottom-up
        bmp_y = h - 1 - y
        for x in range(w):
            idx = (bmp_y * w + x) * 4

            # Rounded square mask (radius 14)
            dx = max(abs(x - cx) - 16.5, 0.0)
            dy = max(abs(y - cy) - 16.5, 0.0)
            dist = math.hypot(dx, dy)
            if dist > 14.0:
                pixels[idx : idx + 4] = b"\x00\x00\x00\x00"
                continue

            # Anti-aliased edge alpha
            alpha = 255 if dist < 13.0 else int(255 * (14.0 - dist))

            # Background gradient: deep slate/indigo (#1e293b -> #312e81)
            r = int(30 + (x / w) * 20)
            g = int(35 + (y / h) * 15)
            b = int(75 + ((x + y) / (w + h)) * 65)

            # Mortarboard diamond top: |x - 32|/20 + |y - 24|/9 <= 1.0
            cap_diamond = (abs(x - 32.0) / 21.0 + abs(y - 24.0) / 9.5) <= 1.0
            # Skullcap base underneath diamond
            cap_base = (22 <= x <= 42) and (29 <= y <= 38) and ((y - 29) <= (10 - abs(x - 32) * 0.35))
            # Tassel on right side
            tassel = (46 <= x <= 49) and (25 <= y <= 40)

            if cap_diamond or tassel:
                # Warm gold (#fbbf24)
                r, g, b = 251, 191, 36
            elif cap_base:
                # Lighter gold/ivory (#fde68a)
                r, g, b = 253, 230, 138

            pixels[idx] = b
            pixels[idx + 1] = g
            pixels[idx + 2] = r
            pixels[idx + 3] = alpha

    # AND mask (1 bit per pixel, padded to 32-bit boundary per row -> 8 bytes per row for w=64)
    and_mask = bytes((w // 8) * h)

    # BITMAPINFOHEADER (40 bytes)
    bmp_header = struct.pack(
        "<IIIHHIIIIII",
        40,                 # biSize
        w,                  # biWidth
        h * 2,              # biHeight (XOR + AND height)
        1,                  # biPlanes
        32,                 # biBitCount
        0,                  # biCompression (BI_RGB)
        len(pixels) + len(and_mask),
        0, 0, 0, 0
    )

    image_data = bmp_header + bytes(pixels) + and_mask

    # ICONDIR (6 bytes) + ICONDIRENTRY (16 bytes)
    icondir = struct.pack("<HHH", 0, 1, 1)
    icondirentry = struct.pack(
        "<BBBBHHII",
        w,                  # bWidth
        h,                  # bHeight
        0,                  # bColorCount
        0,                  # bReserved
        1,                  # wPlanes
        32,                 # wBitCount
        len(image_data),    # dwBytesInRes
        6 + 16              # dwImageOffset
    )

    with open(target_path, "wb") as f:
        f.write(icondir + icondirentry + image_data)

    return target_path


def write_friends_readme(dist_dir: Path):
    """Writes a quick-start guide next to the built executable for friends."""
    dist_dir.mkdir(parents=True, exist_ok=True)
    readme_path = dist_dir / "README - How to Use.txt"
    readme_path.write_text(
        "=============================================================\n"
        "  BLACKBOARD AUTOMATE - WINDOWS DESKTOP EDITION\n"
        "=============================================================\n\n"
        "Quick Start (No setup or Python install needed!):\n\n"
        "1. Double-click 'BlackboardAutomate.exe' to open the app.\n"
        "   (A 'Blackboard Automate' shortcut will also be added to your Desktop).\n\n"
        "2. Click '2FA login' in the top-right corner.\n"
        "   A browser window (Microsoft Edge or Chrome) will open.\n"
        "   Sign in with your university account and approve 2FA on your phone.\n"
        "   Once your courses load, the window will close automatically and\n"
        "   save your session.\n\n"
        "3. Click 'Sync now'!\n"
        "   All your lecture slides, labs, announcements, and assignment\n"
        "   deadlines will automatically sync and convert to Markdown notes.\n\n"
        "4. Where are my downloaded files?\n"
        "   By default, files are saved to your 'Downloads\\Blackboard' folder.\n"
        "   You can click 'Settings' in the top bar at any time to browse and\n"
        "   pick a different folder or open your downloads in File Explorer.\n",
        encoding="utf-8",
    )


def build_executable():
    generate_app_icon(ICON_PATH)
    print(f"✅ Generated application icon at {ICON_PATH}")

    try:
        import PyInstaller.__main__
    except ImportError:
        print("❌ PyInstaller is not installed. Run: pip install pyinstaller")
        sys.exit(1)

    sep = os.pathsep
    static_data = f"{ROOT_DIR / 'app' / 'static'}{sep}app/static"

    hidden_imports = [
        "app",
        "app.server",
        "app.config",
        "app.database",
        "app.auth",
        "app.sync",
        "app.downloader",
        "app.converter",
        "app.coverage",
        "app.calendar",
        "app.scheduler",
        "app.tasks",
        "app.desktop",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "bs4",
        "markdownify",
        "pdfplumber",
        "pdfminer",
        "icalendar",
        "docx",
        "pptx",
        "openpyxl",
        "dotenv",
    ]

    pyinstaller_args = [
        str(ROOT_DIR / "run.py"),
        "--name=BlackboardAutomate",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        f"--icon={ICON_PATH}",
        f"--add-data={static_data}",
        "--collect-all=playwright",
    ]

    for mod in hidden_imports:
        pyinstaller_args.append(f"--hidden-import={mod}")

    print("🚀 Running PyInstaller build...")
    PyInstaller.__main__.run(pyinstaller_args)

    dist_dir = ROOT_DIR / "dist"
    write_friends_readme(dist_dir)
    print(f"🎉 Build complete! Output located in: {dist_dir}")


if __name__ == "__main__":
    if "--icon-only" in sys.argv:
        path = generate_app_icon(ICON_PATH)
        print(f"✅ Created icon: {path}")
    else:
        build_executable()
