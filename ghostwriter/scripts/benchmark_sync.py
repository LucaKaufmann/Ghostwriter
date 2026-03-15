#!/usr/bin/env python3
"""
Benchmark script that mimics the mobile app's sync flow.

Measures timing for each phase:
  1. Initial sync (no prior state — downloads everything)
  2. Incremental sync (passes known digest IDs + feed_since)
  3. Individual digest article fetch (legacy per-digest endpoint)

Usage:
    python scripts/benchmark_sync.py --base-url http://localhost:8080 --token gw_xxx

    # Against a remote server
    python scripts/benchmark_sync.py --base-url http://your-server:8080 --token gw_xxx

    # Repeat N times and show stats
    python scripts/benchmark_sync.py --base-url http://localhost:8080 --token gw_xxx -n 5
"""

import argparse
import json
import statistics
import sys
import time

import requests


def timed(label: str, fn):
    """Run fn(), print elapsed time, return (elapsed_ms, result)."""
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000
    print(f"  {label}: {elapsed_ms:.0f}ms")
    return elapsed_ms, result


def sizeof_fmt(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


def run_benchmark(base_url: str, headers: dict) -> dict:
    """Run one full sync benchmark cycle. Returns timing dict."""
    results = {}

    # --- 1. Initial sync (no prior state) ---
    print("\n[1] Initial sync (full)")

    def do_initial_sync():
        r = requests.get(f"{base_url}/api/sync", headers=headers, timeout=120)
        r.raise_for_status()
        return r

    ms, resp = timed("GET /api/sync", do_initial_sync)
    results["initial_sync_ms"] = ms

    body = resp.json()
    resp_bytes = len(resp.content)
    results["initial_sync_bytes"] = resp_bytes

    digests = body.get("digests", {}).get("new_digests", [])
    total_articles = sum(len(d.get("articles", [])) for d in digests)
    feeds = body.get("feeds", {}).get("feeds", [])
    server_ts = body.get("feeds", {}).get("server_timestamp")

    print(f"    Response size: {sizeof_fmt(resp_bytes)}")
    print(f"    Feeds: {len(feeds)}")
    print(f"    Digests: {len(digests)}, Articles: {total_articles}")

    # --- 2. Incremental sync (client already has everything) ---
    print("\n[2] Incremental sync (all digests known)")
    known_ids = ",".join(str(d["id"]) for d in digests)
    params = {}
    if known_ids:
        params["digest_ids"] = known_ids
    if server_ts:
        params["feed_since"] = server_ts

    def do_incremental_sync():
        r = requests.get(
            f"{base_url}/api/sync", headers=headers, params=params, timeout=120
        )
        r.raise_for_status()
        return r

    ms, resp = timed("GET /api/sync (incremental)", do_incremental_sync)
    results["incremental_sync_ms"] = ms
    results["incremental_sync_bytes"] = len(resp.content)

    inc_body = resp.json()
    inc_digests = inc_body.get("digests", {}).get("new_digests", [])
    print(f"    Response size: {sizeof_fmt(len(resp.content))}")
    print(f"    New digests: {len(inc_digests)}")

    # --- 3. Legacy per-digest article fetch (for comparison) ---
    if digests:
        print(f"\n[3] Legacy per-digest article fetch ({len(digests)} digests)")
        total_legacy_ms = 0
        for d in digests:
            def do_fetch(digest_id=d["id"]):
                r = requests.get(
                    f"{base_url}/api/digests/{digest_id}/articles",
                    headers=headers,
                    timeout=60,
                )
                r.raise_for_status()
                return r

            ms, _ = timed(f"  GET /digests/{d['id'][:8]}…/articles", do_fetch)
            total_legacy_ms += ms

        results["legacy_total_ms"] = total_legacy_ms
        print(f"    Total (sequential): {total_legacy_ms:.0f}ms")
        if len(digests) > 1:
            print(
                f"    vs initial sync:    {results['initial_sync_ms']:.0f}ms "
                f"({results['initial_sync_ms'] / total_legacy_ms:.1f}x)"
            )

    # --- 4. Health endpoint (baseline latency) ---
    print("\n[4] Baseline latency")

    def do_health():
        r = requests.get(f"{base_url}/health", timeout=10)
        r.raise_for_status()
        return r

    ms, _ = timed("GET /health", do_health)
    results["health_ms"] = ms

    return results


def main():
    parser = argparse.ArgumentParser(description="Benchmark Ghostwriter sync")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="Ghostwriter server URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="API token (gw_xxx) or JWT token for auth",
    )
    parser.add_argument(
        "-n",
        type=int,
        default=1,
        help="Number of iterations (default: 1)",
    )
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"}
    base = args.base_url.rstrip("/")

    # Quick connectivity check
    try:
        r = requests.get(f"{base}/health", timeout=5)
        r.raise_for_status()
    except Exception as e:
        print(f"Cannot reach {base}/health: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Benchmarking {base} ({args.n} iteration{'s' if args.n > 1 else ''})")

    all_results = []
    for i in range(args.n):
        if args.n > 1:
            print(f"\n{'='*40} Run {i+1}/{args.n} {'='*40}")
        results = run_benchmark(base, headers)
        all_results.append(results)

    # Summary
    if args.n > 1:
        print(f"\n{'='*40} Summary {'='*40}")
        for key in ("initial_sync_ms", "incremental_sync_ms", "health_ms"):
            values = [r[key] for r in all_results if key in r]
            if values:
                print(
                    f"  {key}: "
                    f"min={min(values):.0f}ms "
                    f"median={statistics.median(values):.0f}ms "
                    f"max={max(values):.0f}ms "
                    f"stdev={statistics.stdev(values):.0f}ms"
                    if len(values) > 1
                    else f"  {key}: {values[0]:.0f}ms"
                )


if __name__ == "__main__":
    main()
