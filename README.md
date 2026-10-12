# 🎓 Blackboard Automate

An automated sync engine, document converter, and academic to-do dashboard for **Blackboard Learn Ultra**.

---

## ✨ Features

- **🔑 Single Sign-On & 2FA Persistence**: Log in once via an interactive Chromium browser window with Microsoft Authenticator; your session is saved locally for seamless headless runs.
- **📚 Course Discovery & Smart Downloads**: Queries Blackboard's REST API to discover enrolled modules and organizes downloaded lecture slides, labs, tutorials, and past exams.
- **⚡ Two-Tier Deduplication**: Prevents duplicate downloads using filename/size checks and SHA-256 cryptographic hashes.
- **📄 PDF & Announcement to Markdown**: Converts lecture/lab PDFs into clean Markdown notes side-by-side (e.g. `slides.pdf` $\rightarrow$ `slides.md`), and converts HTML announcements into readable Markdown.
- **📋 Smart To-Do List Engine**:
  - Automatically extracts official Blackboard deadlines from assignment portals.
  - Scans course announcements using regex & heuristics to detect implicit tasks, submission dates, and lab check requirements.
- **📅 Google Calendar & .ics Feeds**: Automatically generates RFC 5545 `.ics` feeds with reminder alarms (2 days and 4 hours before deadlines), subscribable directly via URL in Google Calendar or Apple Calendar.
- **🖥️ Desktop Web Dashboard**: Modern dark-mode interface with live task tracking, course toggles, note previews, and real-time streaming sync logs.

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/liamh2323/Blackboard-automate.git
cd Blackboard-automate

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies and browser binary
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default settings are configured out of the box for Trinity College Dublin (`https://tcd.blackboard.com`). Customize `DOWNLOAD_DIR` or term filters as needed.

### 3. One-Time 2FA Authentication

```bash
./bb login
```
A browser window will open. Enter your university credentials and approve the 2-Factor Authentication on your phone. Once your Blackboard dashboard loads, your profile is saved.

### 4. Start the Application

```bash
./bb
```
This launches the web dashboard at `http://localhost:8000`, starts background auto-sync, and automatically opens it in your default browser.

---

## 🛠️ Unified CLI (`bb`)

Use the `./bb` script for fast, one-command management without having to manually activate virtual environments:

| Command | Description |
|---------|-------------|
| `./bb` | Starts dashboard server at `http://localhost:8000` with background auto-sync |
| `./bb sync` | Runs one-time headless sync without starting web UI |
| `./bb cover` / `./bb coverage` | Analyzes converted `.md` notes and outputs study roadmap for Antigravity |
| `./bb login` | Opens Chromium window for 2FA login |
| `./bb convert` | Scans and converts any unconverted local PDFs to Markdown |
| `./bb test` | Runs the full automated test suite |
| `./bb install` | Symlinks `bb` to `~/.local/bin/bb` so you can type `bb` from any folder |
| `./bb --port 8080` | Starts server on a custom port |

---

## 🤖 Antigravity CLI Study Integration

Blackboard Automate generates structured syllabus maps, concept checklists, and `STUDY_PLAN.md` documents directly from your downloaded Markdown notes.

You can quiz yourself or generate revision study roadmaps using the Antigravity CLI (`agy`):

```bash
# Analyze study coverage directly in the terminal
./bb cover

# Quiz yourself on a specific module using Antigravity
agy "Review the markdown notes in ./downloads/Systems Programming I and quiz me on memory management."
```

---

## 🧪 Testing

Run the automated test suite:
```bash
python -m unittest tests/test_app.py
```

---

## 📄 License

MIT
