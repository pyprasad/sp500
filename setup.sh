#!/bin/bash
# Setup script for RSI-2 Strategy

echo "=========================================="
echo "RSI-2 Rebound Strategy Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env from example if not exists
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ Created .env file - Please edit with your IG credentials!"
else
    echo ""
    echo "✓ .env file already exists"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env with your IG Demo credentials"
echo "2. Review config.yaml settings"
echo "3. For backtesting:"
echo "   - Place 30-min CSV files in data/backtest/"
echo "   - Run: python -m src.backtest --data-path data/backtest --tp 5"
echo "4. For live trading (dry run):"
echo "   - Run: python -m src.main --tp 5"
echo ""
echo "Run 'source venv/bin/activate' to activate the environment"
echo ""
