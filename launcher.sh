#!/bin/bash

cd "$(dirname "$0")"

while true; do
    python3.9 autowatch_gui.py
    exit_code=$?

    if [ $exit_code -eq 10 ]; then
        echo "Application exited with restart code. Restarting..."
    else
        echo "Application exited with code $exit_code. Not restarting."
        break
    fi
done
