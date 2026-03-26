#!/bin/bash

# Start the bot listener in the background
# We use stdbuf to avoid output buffering issues in Render logs
stdbuf -oL python indexer.py &

# Start the Flask web server with gunicorn in the foreground
# gunicorn handles the PORT environment variable from Render
gunicorn -b 0.0.0.0:$PORT app:app
