#!/bin/bash
# Ghostwriter Local Test Script
# Tests the full pipeline: feeds → extraction → EPUB generation

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# Check if server is running
check_server() {
    echo "Checking server at $BASE_URL..."
    if curl -sf "$BASE_URL/health" > /dev/null 2>&1; then
        log "Server is running"
        return 0
    else
        return 1
    fi
}

# Wait for server to be ready
wait_for_server() {
    echo "Waiting for server..."
    for i in {1..30}; do
        if check_server; then
            return 0
        fi
        sleep 1
    done
    error "Server did not start within 30 seconds"
}

# Test health endpoint
test_health() {
    echo ""
    echo "=== Testing Health Endpoint ==="
    response=$(curl -sf "$BASE_URL/health")
    echo "$response" | python3 -m json.tool
    log "Health check passed"
}

# Test config endpoint
test_config() {
    echo ""
    echo "=== Testing Config Endpoint ==="
    response=$(curl -sf "$BASE_URL/config")
    echo "$response" | python3 -m json.tool
    log "Config check passed"
}

# Add test feeds
add_feeds() {
    echo ""
    echo "=== Adding Test Feeds ==="

    # Sync multiple feeds at once
    feeds='[
        {"url": "https://feeds.arstechnica.com/arstechnica/index", "title": "Ars Technica", "mode": "raw", "max_articles": 3},
        {"url": "https://www.theverge.com/rss/index.xml", "title": "The Verge", "mode": "raw", "max_articles": 3},
        {"url": "https://hnrss.org/frontpage", "title": "Hacker News", "mode": "raw", "max_articles": 3}
    ]'

    response=$(curl -sf -X POST "$BASE_URL/feeds/sync" \
        -H "Content-Type: application/json" \
        -d "$feeds")

    echo "$response" | python3 -m json.tool
    log "Feeds synced"
}

# List feeds
list_feeds() {
    echo ""
    echo "=== Current Feeds ==="
    curl -sf "$BASE_URL/feeds" | python3 -m json.tool
}

# Trigger digest generation
trigger_digest() {
    echo ""
    echo "=== Triggering Digest Generation ==="

    response=$(curl -sf -X POST "$BASE_URL/digests/trigger" \
        -H "Content-Type: application/json" \
        -d '{"period": "manual"}')

    echo "$response" | python3 -m json.tool

    # Extract digest ID
    DIGEST_ID=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")

    if [ -z "$DIGEST_ID" ] || [ "$DIGEST_ID" = "null" ]; then
        error "Failed to get digest ID"
    fi

    log "Digest started: $DIGEST_ID"
    echo "$DIGEST_ID"
}

# Poll digest status until complete
wait_for_digest() {
    local digest_id="$1"
    local max_wait=300  # 5 minutes max
    local elapsed=0

    echo ""
    echo "=== Waiting for Digest Completion ==="

    while [ $elapsed -lt $max_wait ]; do
        response=$(curl -sf "$BASE_URL/digests/$digest_id/status")
        status=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))")
        stage=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('stage', ''))")

        # Show progress
        progress=$(echo "$response" | python3 -c "
import sys, json
p = json.load(sys.stdin).get('progress', {})
print(f\"Feeds: {p.get('feeds_fetched', 0)}/{p.get('total_feeds', 0)} | Articles: {p.get('articles_enriched', 0)}/{p.get('total_articles', 0)}\")
")

        echo -ne "\r[${elapsed}s] Status: $status | Stage: $stage | $progress     "

        if [ "$status" = "completed" ]; then
            echo ""
            log "Digest completed!"
            return 0
        elif [ "$status" = "failed" ]; then
            echo ""
            error_msg=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error_message', 'Unknown error'))")
            error "Digest failed: $error_msg"
        fi

        sleep 2
        elapsed=$((elapsed + 2))
    done

    error "Digest did not complete within $max_wait seconds"
}

# List and download the digest
download_digest() {
    echo ""
    echo "=== Listing Digests ==="
    response=$(curl -sf "$BASE_URL/digests?limit=5")
    echo "$response" | python3 -m json.tool

    # Get latest digest filename
    filename=$(curl -sf "$BASE_URL/digests/latest" | python3 -c "import sys, json; print(json.load(sys.stdin).get('filename', ''))")

    if [ -z "$filename" ]; then
        warn "No completed digest found to download"
        return
    fi

    echo ""
    echo "=== Downloading: $filename ==="

    output_file="$PROJECT_DIR/output/$filename"
    curl -sf "$BASE_URL/digests/$filename" -o "$output_file"

    if [ -f "$output_file" ]; then
        size=$(ls -lh "$output_file" | awk '{print $5}')
        log "Downloaded: $output_file ($size)"

        # Try to open on macOS
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo ""
            read -p "Open EPUB in default reader? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                open "$output_file"
            fi
        fi
    else
        error "Download failed"
    fi
}

# Main test flow
main() {
    echo "========================================"
    echo "  Ghostwriter Local Test"
    echo "========================================"
    echo ""

    # Check if server is running, offer to start it
    if ! check_server; then
        echo ""
        warn "Server is not running at $BASE_URL"
        echo ""
        echo "Start the server in another terminal:"
        echo ""
        echo "  cd $PROJECT_DIR"
        echo "  source venv/bin/activate  # if using venv"
        echo "  export DATA_DIR=./data OUTPUT_DIR=./output"
        echo "  uvicorn app.main:app --reload --port 8080"
        echo ""
        read -p "Press Enter when server is ready, or Ctrl+C to cancel..."
        wait_for_server
    fi

    # Run tests
    test_health
    test_config
    add_feeds
    list_feeds

    # Generate digest
    digest_id=$(trigger_digest)
    wait_for_digest "$digest_id"
    download_digest

    echo ""
    echo "========================================"
    log "All tests completed successfully!"
    echo "========================================"
}

# Run main
main "$@"
