#!/bin/bash
# Convenience script to run libsafe export with Python virtual environment

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run export script with all arguments passed through
python export_libsafe.py "$@"
