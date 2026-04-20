#!/bin/bash
echo "Installing dependencies..."
pip3 install -r requirements.txt

echo ""
echo "Starting SubTok..."
echo "Open http://localhost:8000 in your browser"
echo ""
python3 app.py
