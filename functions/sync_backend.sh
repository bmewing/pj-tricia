#!/bin/bash
set -e
# Copies backend/app into functions/lib/app, the copy the deployed function runs.
#
# The copy is committed rather than made at build time: the function's dependencies are
# built remotely, and a remote build only receives this functions/ folder, so backend/
# isn't there to copy from. Run this after changing backend/app; CI fails if it's stale.
cd "$(dirname "$0")"
rm -rf lib/app
mkdir -p lib
cp -r ../backend/app lib/app
find lib/app -name "__pycache__" -type d -prune -exec rm -rf {} +
