#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_NAME="claude-ralph"
INSTALL_DIR="${HOME}/.local/bin"

echo "Building image..."
docker build -q -t "$IMAGE_NAME" "$SCRIPT_DIR" >/dev/null

echo "Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
ln -sf "$SCRIPT_DIR/ralphish" "$INSTALL_DIR/ralphish"

echo "Done. Make sure $INSTALL_DIR is in your PATH."
