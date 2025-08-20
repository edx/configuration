#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./incremental-reindex-meili.sh INDEX [WINDOW] [SLEEP_TIME] [BATCH_SIZE]
#
# Example:
#   ./incremental-reindex-meili.sh content 30

INDEX="$1"
WINDOW="${2:-5}"
SLEEP_TIME="${3:-60}"
BATCH_SIZE="${4:-500}"
API_KEY="${MEILI_API_KEY:-}"
MEILI_URL="${MEILI_URL:-http://localhost:7700}"

if [ "$SLEEP_TIME" -ge "$((WINDOW * 60))" ]; then
  echo 'ERROR: SLEEP_TIME must not be longer than WINDOW, or else documents may be missed.'
  exit 1
fi

while : ; do
  echo "Fetching documents newer than $WINDOW minutes..."

  # Replace this with your actual data fetch logic (DB query or API)
  # Here, we assume you have a script `fetch_new_docs.rb` that prints JSON array
  NEW_DOCS=$(./fetch_new_docs.rb "$WINDOW" "$INDEX" "$BATCH_SIZE")

  if [ -n "$NEW_DOCS" ]; then
    echo "$NEW_DOCS" | curl -s -X POST "$MEILI_URL/indexes/$INDEX/documents" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      --data-binary @-
    echo "Indexed batch into $INDEX"
  else
    echo "No new docs."
  fi

  echo "Sleeping $SLEEP_TIME seconds..."
  sleep "$SLEEP_TIME"

  [ "$SLEEP_TIME" -le 0 ] && break
done
