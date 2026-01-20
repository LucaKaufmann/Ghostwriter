#!/usr/bin/env python3
"""
Ghostwriter End-to-End Test Script

Tests the full pipeline: feeds → extraction → EPUB generation
Can be run with or without a live server (uses TestClient for isolated testing).
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_with_live_server(base_url: str) -> None:
    """Test against a running server."""
    import httpx

    client = httpx.Client(base_url=base_url, timeout=30.0)

    print("=" * 50)
    print("Testing against live server:", base_url)
    print("=" * 50)

    # Health check
    print("\n[1/6] Health check...")
    r = client.get("/health")
    r.raise_for_status()
    health = r.json()
    print(f"  Status: {health['status']}")
    print(f"  Version: {health['version']}")
    print(f"  AI Provider: {health['ai_provider']}")

    # Config
    print("\n[2/6] Config...")
    r = client.get("/config")
    r.raise_for_status()
    config = r.json()
    print(f"  Timezone: {config['timezone']}")
    print(f"  Schedule enabled: {config['schedule_enabled']}")

    # Sync feeds
    print("\n[3/6] Syncing test feeds...")
    feeds = [
        {
            "url": "https://feeds.arstechnica.com/arstechnica/index",
            "title": "Ars Technica",
            "mode": "raw",
            "max_articles": 2,
        },
        {
            "url": "https://hnrss.org/frontpage",
            "title": "Hacker News",
            "mode": "raw",
            "max_articles": 3,
        },
    ]
    r = client.post("/feeds/sync", json=feeds)
    r.raise_for_status()
    sync_result = r.json()
    print(f"  Synced: {sync_result['synced']}")
    print(f"  Created: {sync_result['created']}")

    # List feeds
    print("\n[4/6] Listing feeds...")
    r = client.get("/feeds")
    r.raise_for_status()
    for feed in r.json():
        print(f"  - {feed['title']} ({feed['mode']})")

    # Trigger digest
    print("\n[5/6] Triggering digest generation...")
    r = client.post("/digests/trigger", json={"period": "manual"})
    r.raise_for_status()
    trigger = r.json()
    digest_id = trigger["id"]
    print(f"  Digest ID: {digest_id}")

    # Poll for completion
    print("\n[6/6] Waiting for completion...")
    max_wait = 300
    start = time.time()

    while time.time() - start < max_wait:
        r = client.get(f"/digests/{digest_id}/status")
        r.raise_for_status()
        status = r.json()

        progress = status["progress"]
        elapsed = int(time.time() - start)
        print(
            f"\r  [{elapsed}s] {status['status']} | {status['stage']} | "
            f"Feeds: {progress['feeds_fetched']}/{progress['total_feeds']} | "
            f"Articles: {progress['articles_enriched']}/{progress['total_articles']}",
            end="",
            flush=True,
        )

        if status["status"] == "completed":
            print("\n  Done!")
            break
        elif status["status"] == "failed":
            print(f"\n  FAILED: {status.get('error_message', 'Unknown error')}")
            sys.exit(1)

        time.sleep(2)
    else:
        print(f"\n  Timeout after {max_wait}s")
        sys.exit(1)

    # Download result
    print("\nDownloading digest...")
    r = client.get("/digests/latest")
    r.raise_for_status()
    latest = r.json()
    filename = latest["filename"]

    r = client.get(f"/digests/{filename}")
    r.raise_for_status()

    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / filename

    output_path.write_bytes(r.content)
    print(f"  Saved: {output_path} ({len(r.content)} bytes)")

    print("\n" + "=" * 50)
    print("SUCCESS!")
    print("=" * 50)


def test_with_testclient() -> None:
    """Test using FastAPI TestClient (no server required)."""
    # Set test environment
    os.environ["DATA_DIR"] = "/tmp/ghostwriter_test"
    os.environ["OUTPUT_DIR"] = "/tmp/ghostwriter_test_output"
    os.environ["API_KEY"] = ""
    os.environ["SCHEDULE_ENABLED"] = "false"

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    print("=" * 50)
    print("Testing with TestClient (isolated)")
    print("=" * 50)

    # Health
    print("\n[1/4] Health check...")
    r = client.get("/health")
    assert r.status_code == 200
    print(f"  Status: {r.json()['status']}")

    # Create feed
    print("\n[2/4] Creating feed...")
    r = client.post(
        "/feeds",
        json={
            "url": "https://hnrss.org/frontpage",
            "title": "Hacker News",
            "mode": "raw",
            "max_articles": 2,
        },
    )
    assert r.status_code == 200
    print(f"  Created: {r.json()['title']}")

    # List feeds
    print("\n[3/4] Listing feeds...")
    r = client.get("/feeds")
    assert r.status_code == 200
    print(f"  Count: {len(r.json())}")

    # Trigger (this will run synchronously in test mode)
    print("\n[4/4] Triggering digest...")
    r = client.post("/digests/trigger", json={"period": "manual"})
    if r.status_code == 200:
        print(f"  Started: {r.json()['id']}")
    else:
        print(f"  Response: {r.status_code} - {r.text}")

    print("\n" + "=" * 50)
    print("Basic tests passed!")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Test Ghostwriter")
    parser.add_argument(
        "--live",
        "-l",
        metavar="URL",
        default=None,
        help="Test against live server (e.g., http://localhost:8080)",
    )
    parser.add_argument(
        "--isolated",
        "-i",
        action="store_true",
        help="Run isolated tests with TestClient (default)",
    )

    args = parser.parse_args()

    if args.live:
        test_with_live_server(args.live)
    else:
        test_with_testclient()


if __name__ == "__main__":
    main()
