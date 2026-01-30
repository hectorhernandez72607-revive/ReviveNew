#!/bin/bash
# Run from project root:  ./start-backend.sh   or   bash start-backend.sh
cd "$(dirname "$0")/backend" || exit 1
source venv/bin/activate
uvicorn main2:app --reload --port 8000
