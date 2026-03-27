#!/bin/bash

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start the bot listener in the background
python3 indexer.py &

# Start the Flask web server with gunicorn in the foreground
gunicorn -b 0.0.0.0:${PORT:-5000} app:app
