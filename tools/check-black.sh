#!/bin/bash

set -u

if ! black --check --target-version py36 .; then
    echo ""
    echo ""
    echo "************************************"
    echo "ERROR"
    echo "Code is not formatted correctly. Please run the program 'black' on the code"
    echo "To do this run:"
    echo "   $ tox -e black"
    echo ""
    exit 1
fi
