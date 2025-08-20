#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./copy-index-meili.sh SOURCE_ES SERVER:PORT SOURCE_INDEX TARGET_MEILI_SERVER:PORT TARGET_INDEX
#
# Example:
#   ./copy-index-meili.sh http://localhost:9200 source_index http://localhost:7700 target_index

SOURCE_ES=$1
SOURCE_INDEX=$2
TARGET_MEILI=$3
TARGET_INDEX=$4
API_KEY="${5:-}"   # Optional Meilisearch master key

# Ensure target index exists
curl -s -X POST "$TARGET_MEILI/indexes" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d "{ \"uid\": \"$TARGET_INDEX\" }" || true

# Scroll through Elasticsearch index
SCROLL="1m"
SIZE=1000
SCROLL_ID=$(curl -s "$SOURCE_ES/$SOURCE_INDEX/_search?scroll=$SCROLL" \
    -H 'Content-Type: application/json' \
    -d "{ \"size\": $SIZE }" | jq -r '._scroll_id')

while [ "$SCROLL_ID" != "null" ]; do
    # Fetch batch from Elasticsearch
    RESPONSE=$(curl -s "$SOURCE_ES/_search/scroll" \
        -H 'Content-Type: application/json' \
        -d "{ \"scroll\": \"$SCROLL\", \"scroll_id\": \"$SCROLL_ID\" }")

    DOCS=$(echo "$RESPONSE" | jq '.hits.hits[]._source')
    COUNT=$(echo "$DOCS" | jq length)

    if [ "$COUNT" -eq 0 ]; then
        break
    fi

    # Push batch into Meilisearch
    echo "$DOCS" | jq -s '.' | curl -s -X POST "$TARGET_MEILI/indexes/$TARGET_INDEX/documents" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        --data-binary @-

    # Next scroll id
    SCROLL_ID=$(echo "$RESPONSE" | jq -r '._scroll_id')
done
