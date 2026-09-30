#!/bin/bash

# -e Exit immediately if a pipeline returns a non-zero status
# -x Print a trace of simple commands
# -u Treat unset variables and parameters as an error
set -ex
echo "$1"
echo "$@"

case $1 in
    web)
        echo "START WEB"
        exec python src/main.py
        ;;
    *)
        if [ $# -eq 0]
          then
            echo "No arguments supplied"
          else
            echo "Running '$1' command..."
            exec "$1"
        fi
        ;;
esac
