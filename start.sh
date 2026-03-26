#!/bin/bash

# Start the bot listener in the background
python indexer.py &

# Start the Flask web server with gunicorn in the foreground
gunicorn -b 0.0.0.0:$PORT app:app
