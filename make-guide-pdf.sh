#!/usr/bin/env bash
# Regenerate AI-Job-Finder-Guide.pdf from guide.html.
# The guide switches to a light print theme automatically, so the PDF is a
# document rather than a screenshot of a dark page.
#
# Usage:  ./make-guide-pdf.sh
set -euo pipefail
cd "$(dirname "$0")"

OUT="AI-Job-Finder-Guide.pdf"
PORT="${PORT:-8799}"

find_browser() {
  local candidates=(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    "$(command -v google-chrome || true)"
    "$(command -v chromium || true)"
    "$(command -v chromium-browser || true)"
  )
  for c in "${candidates[@]}"; do
    [ -n "$c" ] && [ -x "$c" ] && { printf '%s' "$c"; return 0; }
  done
  # Playwright keeps a headless shell here if you have ever installed it
  local pw
  pw="$(find "$HOME/Library/Caches/ms-playwright" "$HOME/.cache/ms-playwright" \
        -name 'chrome-headless-shell' -type f -perm -u+x 2>/dev/null | head -1 || true)"
  [ -n "$pw" ] && { printf '%s' "$pw"; return 0; }
  return 1
}

BROWSER="$(find_browser)" || {
  echo "No Chrome, Chromium or Edge found. Install one, or open guide.html and" >&2
  echo "use the browser's own print dialog with Save as PDF." >&2
  exit 1
}

# The page must be served rather than opened from disk, so its fonts and layout
# resolve the same way they do for a visitor.
python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT
sleep 1

"$BROWSER" --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --virtual-time-budget=15000 --no-pdf-header-footer \
  --print-to-pdf="$OUT" "http://127.0.0.1:$PORT/guide.html" >/dev/null 2>&1

echo "Wrote $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
