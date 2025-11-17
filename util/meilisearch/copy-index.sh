#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./copy-index.sh SOURCE_ES SOURCE_INDEX TARGET_MEILI TARGET_INDEX [API_KEY]

SOURCE_ES=$1
SOURCE_INDEX=$2
TARGET_MEILI=$3
TARGET_INDEX=$4
API_KEY="${5:-}"

AUTH_HEADER=()
if [ -n "$API_KEY" ]; then
  AUTH_HEADER=(-H "Authorization: Bearer $API_KEY")
fi

# Recreate target index (optional but safer for fresh import)
curl -s -X DELETE "$TARGET_MEILI/indexes/$TARGET_INDEX" "${AUTH_HEADER[@]}" || true
curl -s -X POST "$TARGET_MEILI/indexes" \
    -H "Content-Type: application/json" \
    "${AUTH_HEADER[@]}" \
    -d "{ \"uid\": \"$TARGET_INDEX\" }"

# Scroll through Elasticsearch
SCROLL="1m"
SIZE=500
SCROLL_ID=$(curl -s "$SOURCE_ES/$SOURCE_INDEX/_search?scroll=$SCROLL" \
    -H 'Content-Type: application/json' \
    -d "{ \"size\": $SIZE }" | jq -r '._scroll_id')

while [ "$SCROLL_ID" != "null" ]; do
    RESPONSE=$(curl -s "$SOURCE_ES/_search/scroll" \
        -H 'Content-Type: application/json' \
        -d "{ \"scroll\": \"$SCROLL\", \"scroll_id\": \"$SCROLL_ID\" }")

    DOCS=$(echo "$RESPONSE" | jq '.hits.hits[]._source')
    COUNT=$(echo "$DOCS" | jq -s 'length')

    if [ "$COUNT" -eq 0 ]; then
        break
    fi

    echo "$DOCS" | jq -s '.' | curl -s -X POST \
        "$TARGET_MEILI/indexes/$TARGET_INDEX/documents" \
        -H "Content-Type: application/json" \
        "${AUTH_HEADER[@]}" \
        --data-binary @-

    SCROLL_ID=$(echo "$RESPONSE" | jq -r '._scroll_id')
done

# Cleanup scroll context
curl -s -X DELETE "$SOURCE_ES/_search/scroll" \
    -H 'Content-Type: application/json' \
    -d "{ \"scroll_id\": [\"$SCROLL_ID\"] }" > /dev/null || true

echo "Copied index $SOURCE_INDEX from $SOURCE_ES to $TARGET_INDEX on $TARGET_MEILI"
