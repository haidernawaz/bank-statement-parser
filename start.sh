#!/bin/bash
# Tell Flask which file is the app
export FLASK_APP=app.py
# Set production environment
export FLASK_ENV=production
# Run Flask on host 0.0.0.0 so external servers can access it
flask run --host=0.0.0.0 --port=$PORT
