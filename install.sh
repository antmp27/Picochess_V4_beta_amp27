#!/bin/bash

# PicoChess Installation Script for GitHub
# Simplified version for development setup

set -e

echo "🚀 Installing PicoChess..."

# Check Python version
python3 --version || { echo "❌ Python 3 is required"; exit 1; }

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Install development dependencies if available
if [ -f "test-requirements.txt" ]; then
    echo "🧪 Installing test dependencies..."
    pip install -r test-requirements.txt
fi

# Make scripts executable
chmod +x picochess.sh
chmod +x install-picochess.sh 2>/dev/null || true
chmod +x connect-dgt-on-debian.sh 2>/dev/null || true

echo "✅ Installation complete!"
echo ""
echo "To run PicoChess:"
echo "  source venv/bin/activate"
echo "  python picochess.py"
echo ""
echo "To run tests:"
echo "  source venv/bin/activate"
echo "  pytest tests/"