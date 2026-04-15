#!/bin/bash
set -e

echo "🎤 Talk to Vibe Setup"
echo "==================="

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required. Install from https://python.org"
    exit 1
fi

PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Python: $PYTHON_VER"

if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! brew list portaudio &> /dev/null 2>&1; then
        echo "  Installing PortAudio (required for microphone)..."
        if command -v brew &> /dev/null; then
            brew install portaudio
        else
            echo "❌ Homebrew not found. Install PortAudio manually:"
            echo "   brew install portaudio"
            exit 1
        fi
    else
        echo "  PortAudio: installed"
    fi
fi

if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv .venv
else
    echo "  Virtual environment: exists"
fi

source .venv/bin/activate

echo "  Installing dependencies..."
pip install -q -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "Run the app:"
echo "  ./run_ttv.sh"
echo ""
echo "Reconfigure provider:"
echo "  ./run_ttv.sh --setup"
echo ""
echo "Run tests:"
echo "  ./run_ttv.sh --test"
echo ""
echo "⚠️  First run: You'll be asked to select an STT provider and enter your API key."
echo "⚠️  macOS: Grant Accessibility & Microphone permissions when prompted."
