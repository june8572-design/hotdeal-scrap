#!/usr/bin/env python3
"""002: 대시보드 개선을 위한 DB 스키마 확장 마이그레이션.

변경 사항:
1. presets 테이블에 source_type 컬럼 추가 (hotdeal/todayhumor_tip/todayhumor_good/todayhumor_fun)
2. targets 테이블에 categories JSON 컬럼 추가 (카테고리 복수 선택)
3. todayhumor_tips 테이블에 category 컬럼 추가 (tip/good/fun 분류)
4. article_sources 테이블 생성 (통합 글 소스 관리)
5. article_queue 테이블 생성 (자동글 작성 큐)
"""
import json
import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("HOTDEAL_DB_PATH", str(PROJECT_ROOT / "hotdeal.db")))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """테이블에 컬럼이 존재하는지 확인"""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """테이블이 존재하는지 확인"""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone()
    return row is not None


def migrate():
    conn = get_conn()
    
    try:
        # 1. presets 테이블에 source_type 컬럼 추가
        if not column_exists(conn, "presets", "source_type"):
            conn.execute("ALTER TABLE presets ADD COLUMN source_type TEXT DEFAULT 'hotdeal'")
            print("✅ presets.source_type 컬럼 추가 완료")
        else:
            print("⏭️ presets.source_type 컬럼 이미 존재")
        
        # 2. targets 테이블에 categories JSON 컬럼 추가
        if not column_exists(conn, "targets", "categories"):
            conn.execute("ALTER TABLE targets ADD COLUMN categories TEXT DEFAULT '[]'")
            print("✅ targets.categories 컬럼 추가 완료")
        else:
            print("⏭️ targets.categories 컬럼 이미 존재")
        
        # 3. todayhumor_tips 테이블에 category 컬럼 추가
        if table_exists(conn, "todayhumor_tips"):
            if not column_exists(conn, "todayhumor_tips", "category"):
                conn.execute("ALTER TABLE todayhumor_tips ADD COLUMN category TEXT DEFAULT 'tip'")
                print("✅ todayhumor_tips.category 컬럼 추가 완료")
            else:
                print("⏭️ todayhumor_tips.category 컬럼 이미 존재")
        
        # 4. article_sources 테이블 생성 (통합 글 소스 관리)
        if not table_exists(conn, "article_sources"):
            conn.execute("""
                CREATE TABLE article_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,  -- 'hotdeal', 'todayhumor_tip', 'todayhumor_good', 'todayhumor_fun'
                    title TEXT NOT NULL,
                    content_text TEXT,
                    content_html TEXT,
                    source_url TEXT,
                    thumbnail_url TEXT,
                    category TEXT,  -- 'product', 'tip', 'good', 'fun'
                    metadata_json TEXT,  -- 추가 메타데이터 (가격, 작성자 등)
                    collected_at DATETIME DEFAULT (datetime('now')),
                    used_count INTEGER DEFAULT 0,
                    is_archived INTEGER DEFAULT 0
                )
            """)
            print("✅ article_sources 테이블 생성 완료")
        else:
            print("⏭️ article_sources 테이블 이미 존재")
        
        # 5. article_queue 테이블 생성 (자동글 작성 큐)
        if not table_exists(conn, "article_queue"):
            conn.execute("""
                CREATE TABLE article_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER REFERENCES targets(id) ON DELETE CASCADE,
                    preset_id INTEGER REFERENCES presets(id) ON DELETE SET NULL,
                    category TEXT NOT NULL,  -- 'product', 'tip', 'good', 'fun'
                    title TEXT,
                    content TEXT,  -- LLM 생성 글
                    source_ids TEXT,  -- 사용된 소스 ID 목록 (JSON 배열)
                    status TEXT DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED, COMPLETED
                    created_at DATETIME DEFAULT (datetime('now')),
                    updated_at DATETIME DEFAULT (datetime('now')),
                    approved_at DATETIME,
                    posted_at DATETIME
                )
            """)
            print("✅ article_queue 테이블 생성 완료")
        else:
            print("⏭️ article_queue 테이블 이미 존재")
        
        # 6. 인덱스 생성
        indexes = [
            "CREATE INDEX IF EXISTS idx_article_sources_type ON article_sources(source_type)",
            "CREATE INDEX IF EXISTS idx_article_sources_category ON article_sources(category)",
            "CREATE INDEX IF EXISTS idx_article_sources_collected ON article_sources(collected_at)",
            "CREATE INDEX IF EXISTS idx_article_queue_status ON article_queue(status)",
            "CREATE INDEX IF EXISTS idx_article_queue_target ON article_queue(target_id)",
            "CREATE INDEX IF EXISTS idx_article_queue_category ON article_queue(category)",
            "CREATE INDEX IF EXISTS idx_todayhumor_tips_category ON todayhumor_tips(category)",
        ]
        for idx_sql in indexes:
            try:
                conn.execute(idx_sql.replace("IF EXISTS", "IF NOT EXISTS"))
            except sqlite3.OperationalError:
                pass
        
        # 7. 기본 프리셋 데이터 삽입 (없는 경우)
        existing_presets = conn.execute("SELECT name FROM presets").fetchall()
        existing_names = {row["name"] for row in existing_presets}
        
        default_presets = [
            ("hotdeal.zip", "https://hotdeal.zip/api/deals.php", "HOTDEAL", "hotdeal", 60, 1),
            ("오늘의유머 꿀팁", "https://m.todayhumor.co.kr/", "TODAYHUMOR", "todayhumor_tip", 120, 0),
            ("오늘의유머 좋은글", "https://m.todayhumor.co.kr/", "TODAYHUMOR", "todayhumor_good", 120, 0),
            ("오늘의유머 유머글", "https://m.todayhumor.co.kr/", "TODAYHUMOR", "todayhumor_fun", 120, 0),
        ]
        
        for name, url, action_type, source_type, interval, needs_confirm in default_presets:
            if name not in existing_names:
                conn.execute(
                    """INSERT INTO presets (name, target_url, action_type, source_type, interval_min, needs_confirmation, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, 0)""",
                    (name, url, action_type, source_type, interval, needs_confirm)
                )
                print(f"✅ 기본 프리셋 '{name}' 추가 완료")
        
        conn.commit()
        print("\n🎉 마이그레이션 완료!")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ 마이그레이션 실패: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
