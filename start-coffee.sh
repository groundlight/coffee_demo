#!/bin/bash

# Get the directory of the current script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to the script's directory
cd "$SCRIPT_DIR"

# Start the Python program inside a new tmux session
# tmux environment variables are funny and can be shared between sessions, so we source inside the new session
tmux new-session -d -s coffee 'source ./set-environment ; echo $GROUNDLIGHT_API_TOKEN > verify_token.txt ; python3 ./coffee_demo.py'
