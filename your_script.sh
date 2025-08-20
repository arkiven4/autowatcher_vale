#!/bin/bash

if [ "$1" == "run_in_terminal" ]; then
    while true; do
        echo "Hello from your_script.sh!"
        sleep 60
    done
else
    konsole --noclose -e "bash \"$0\" run_in_terminal" &
fi