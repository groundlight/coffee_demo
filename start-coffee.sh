#!/bin/bash

# Get the directory of the current script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to the script's directory
cd "$SCRIPT_DIR"

# Source the secret environment variables
source ./set-environment

# Start the Python program inside a new tmux session
tmux new-session -d -s coffee 'python3 ./coffee_demo.py'

