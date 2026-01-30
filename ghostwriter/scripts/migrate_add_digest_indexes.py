#!/usr/bin/env python3
"""Add index on digests.status for faster sync queries."""

import sqlite3
import sys
from pathlib import Path

DB_PATHS = [
    Path("/app/data/ghostwriter.db"),       # Docker
    Path("data/ghostwriter.db"),            # Local dev
]


def migrate(db_path: Path) -> None:
    print(f"Migrating {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_digests_status'"
    )
    if cursor.fetchone():
        print("  Index ix_digests_status already exists, skipping.")
    else:
        cursor.execute("CREATE INDEX ix_digests_status ON digests (status)")
        print("  Created index ix_digests_status.")

    conn.commit()

    # Run ANALYZE so the query planner picks up the new index
    cursor.execute("ANALYZE")
    print("  Ran ANALYZE.")

    conn.close()
    print("  Done.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        migrate(Path(sys.argv[1]))
    else:
        for p in DB_PATHS:
            if p.exists():
                migrate(p)
                break
        else:
            print(f"No database found at: {[str(p) for p in DB_PATHS]}")
            sys.exit(1)
