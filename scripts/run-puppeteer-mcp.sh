#!/usr/bin/env bash
# Wrapper for @kirkdeam/puppeteer-mcp-server
# Sets Puppeteer env vars to use cached Chromium binary and run as stdio MCP server.
set -euo pipefail

export PUPPETEER_SKIP_DOWNLOAD=true
export PUPPETEER_EXECUTABLE_PATH="${PUPPETEER_EXECUTABLE_PATH:-/root/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome}"
export ALLOW_DANGEROUS=true
export PUPPETEER_LAUNCH_OPTIONS='{"headless":true,"args":["--no-sandbox","--disable-setuid-sandbox"]}'

exec npx -y @kirkdeam/puppeteer-mcp-server "$@"
