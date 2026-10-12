#!/usr/bin/env bash
#
# bb - Blackboard Automate unified CLI launcher
#

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# Locate Python environment
if [ -f "$REPO_DIR/.venv/bin/python" ]; then
    PYTHON="$REPO_DIR/.venv/bin/python"
elif [ -n "$VIRTUAL_ENV" ] && [ -f "$VIRTUAL_ENV/bin/python" ]; then
    PYTHON="$VIRTUAL_ENV/bin/python"
else
    PYTHON="python3"
fi

show_help() {
    cat << 'EOF'
🎓 Blackboard Automate - Quick CLI Launcher (bb)

Usage:
  ./bb [COMMAND] [OPTIONS]

Commands:
  (no args)       Start the web dashboard server at http://localhost:8000
  start           Start the web dashboard server
  sync            Run one-time headless synchronization now
  login           Launch Chromium window for 2FA authentication
  cover, coverage Analyze downloaded .md notes and print study coverage
  convert         Convert all unconverted PDF files to Markdown
  test            Run automated test suite
  install         Symlink 'bb' to ~/.local/bin/bb for global access
  help, -h        Show this help message

Options:
  --port <PORT>   Specify custom port (default: 8000)
  --host <HOST>   Specify custom host (default: 127.0.0.1)
  --course <NAME> Filter coverage by course name/code
EOF
}

cmd="${1:-}"

case "$cmd" in
    ""|"start")
        shift || true
        echo "🚀 Starting Blackboard Automate Dashboard..."
        exec "$PYTHON" run.py "$@"
        ;;
    "sync"|"sync-only"|"--sync-only")
        shift || true
        echo "⚡ Running headless synchronization..."
        exec "$PYTHON" run.py --sync-only "$@"
        ;;
    "login"|"--login")
        shift || true
        echo "🔑 Launching 2FA login browser..."
        exec "$PYTHON" run.py --login "$@"
        ;;
    "cover"|"coverage"|"--coverage")
        shift || true
        echo "📖 Analyzing academic study coverage..."
        exec "$PYTHON" run.py --coverage "$@"
        ;;
    "convert"|"convert-all"|"--convert-all")
        shift || true
        echo "📄 Converting all pending PDFs to Markdown..."
        exec "$PYTHON" run.py --convert-all "$@"
        ;;
    "test"|"tests")
        shift || true
        echo "🧪 Running unit test suite..."
        exec "$PYTHON" -m unittest tests/test_app.py "$@"
        ;;
    "install")
        mkdir -p "$HOME/.local/bin"
        ln -sf "$REPO_DIR/bb" "$HOME/.local/bin/bb"
        echo "✅ Symlinked '$REPO_DIR/bb' -> '$HOME/.local/bin/bb'"
        echo "If ~/.local/bin is in your PATH, you can now run 'bb' from anywhere!"
        exit 0
        ;;
    "help"|"-h"|"--help")
        show_help
        exit 0
        ;;
    *)
        # Forward any custom flags directly to run.py
        exec "$PYTHON" run.py "$@"
        ;;
esac
