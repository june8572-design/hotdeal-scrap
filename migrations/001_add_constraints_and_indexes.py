#!/usr/bin/env python3
"""
Migration 001: Add Foreign Keys and Indexes
- Foreign Key 제약조건 추가 (jobs → targets, presets)
- 필수 인덱스 추가 (site, status, brand_connector_status)
"""

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "hotdeal.db"


def migrate():
    conn = sqlite3.connect(DB_PATH)
    # Enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("🔧 Migration 001: Adding constraints and indexes...")

    try:
        # 1. 인덱스 추가 (deals 테이블)
        print("  → Creating index on deals.site...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deals_site ON deals(site)")

        print("  → Creating index on deals.brand_connector_status...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_deals_bc_status ON deals(brand_connector_status)"
        )

        print("  → Creating index on deals.fetched_at...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_deals_fetched_at ON deals(fetched_at)"
        )

        # 2. 인덱스 추가 (jobs 테이블)
        print("  → Creating index on jobs.status...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")

        print("  → Creating index on jobs.job_type...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type)")

        print("  → Creating index on jobs.target_id...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_target_id ON jobs(target_id)"
        )

        print("  → Creating index on jobs.preset_id...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_preset_id ON jobs(preset_id)"
        )

        # 3. 인덱스 추가 (presets, targets)
        print("  → Creating index on presets.is_active...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_presets_active ON presets(is_active)"
        )

        print("  → Creating index on targets.is_active...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_targets_active ON targets(is_active)"
        )

        # 4. Foreign Key 제약조건 추가
        print("  → Adding foreign key: jobs.target_id → targets(id)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER,
                preset_id INTEGER,
                job_type TEXT NOT NULL, -- 'HOTDEAL', 'CAFE_COMMENT'
                status TEXT NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'RUNNING', 'COMPLETED', 'FAILED'
                post_title TEXT,
                post_url TEXT,
                content TEXT, -- 작성할 문구
                error_message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (target_id) REFERENCES targets(id),
                FOREIGN KEY (preset_id) REFERENCES presets(id)
            )
        """)

        # Copy data from old jobs table to new one
        cursor.execute("""
            INSERT INTO jobs_new (id, target_id, preset_id, job_type, status, post_title, post_url, content, error_message, created_at, updated_at)
            SELECT id, target_id, preset_id, job_type, status, post_title, post_url, content, error_message, created_at, updated_at FROM jobs
        """)

        # Drop old jobs table and rename new one
        cursor.execute("DROP TABLE jobs")
        cursor.execute("ALTER TABLE jobs_new RENAME TO jobs")

        # Recreate indexes on the new jobs table
        print("  → Recreating indexes on jobs table...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_target_id ON jobs(target_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_preset_id ON jobs(preset_id)"
        )

        conn.commit()
        print("✅ Migration 001 completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
