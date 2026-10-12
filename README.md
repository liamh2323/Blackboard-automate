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
python run.py --login
```
A browser window will open. Enter your university credentials and approve the 2-Factor Authentication on your phone. Once your Blackboard dashboard loads, your profile is saved.

### 4. Start the Application

```bash
python run.py
```
This launches the web dashboard at `http://localhost:8000` and automatically opens it in your default browser.

---

## 🛠️ CLI Options

| Command | Description |
|---------|-------------|
| `python run.py` | Starts the web dashboard server at `http://localhost:8000` |
| `python run.py --sync-only` | Runs a one-time headless sync without starting the web UI |
| `python run.py --login` | Opens the interactive browser window to refresh 2FA session |
| `python run.py --convert-all` | Scans and converts any unconverted local PDFs to Markdown |
| `python run.py --port 8080` | Runs the server on a custom port |

---

## 🧪 Testing

Run the automated test suite:
```bash
python -m unittest tests/test_app.py
```

---

## 📄 License

MIT
