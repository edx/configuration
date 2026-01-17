#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./forums-incremental-reindex.sh INDEX [WINDOW] [SLEEP_TIME] [BATCH_SIZE]
#
# Example:
#   ./forums-incremental-reindex.sh content 30

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

AUTH_HEADER=()
if [ -n "$API_KEY" ]; then
  AUTH_HEADER=(-H "Authorization: Bearer $API_KEY")
fi

while : ; do
  echo "Fetching documents newer than $WINDOW minutes..."

  # Fetch documents newer than $WINDOW minutes using Meilisearch API
  SINCE_TIMESTAMP=$(date -u -d "$WINDOW minutes ago" +"%Y-%m-%dT%H:%M:%SZ")
  NEW_DOCS=$(curl -s "${AUTH_HEADER[@]}" \
    "$MEILI_URL/indexes/$INDEX/documents?limit=$BATCH_SIZE" \
    | jq --arg since "$SINCE_TIMESTAMP" '[.[] | select(.updated_at >= $since)]')

  if [ -n "$NEW_DOCS" ] && [ "$NEW_DOCS" != "[]" ]; then
    echo "$NEW_DOCS" | curl -s -X POST "$MEILI_URL/indexes/$INDEX/documents" \
      -H "Content-Type: application/json" \
      "${AUTH_HEADER[@]}" \
      --data-binary @-
    echo "Indexed $(echo "$NEW_DOCS" | jq length) docs into $INDEX"
  else
    echo "No new docs."
  fi

  echo "Sleeping $SLEEP_TIME seconds..."
  sleep "$SLEEP_TIME"

  [ "$SLEEP_TIME" -le 0 ] && break
done
