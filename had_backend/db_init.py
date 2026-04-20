import sqlite3
import os
from pathlib import Path

# DB 경로: 환경변수 우선, 없으면 현재 디렉토리
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = Path(os.getenv("HOTDEAL_DB_PATH", str(PROJECT_ROOT / "hotdeal.db")))


def init_had_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 0. 핫딜 정보 테이블 (Deals) - 기존 수집 스크립트 호환용
    conn.execute("""
    CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY,
        title TEXT,
        price TEXT,
        category TEXT,
        site TEXT,
        created_at TEXT,
        views INTEGER,
        thumbnail_url TEXT,
        seo_url TEXT,
        post_url TEXT,
        time TEXT,
        relative_time TEXT,
        relative_time_class TEXT,
        favicon_url TEXT,
        community_name TEXT,
        gradient TEXT,
        fetched_at TEXT DEFAULT (datetime('now')),
        price_table_json TEXT,
        price_summary TEXT,
        details_text_raw TEXT,
        details_text_clean TEXT,
        details_images_json TEXT,
        details_fetched_at TEXT,
        out_links_json TEXT,
        naver_brand_connector_links_json TEXT,
        is_affiliate_candidate INTEGER,
        affiliate_url_type TEXT,
        canonical_product_name TEXT,
        canonical_product_url TEXT,
        promo_text TEXT,
        promo_generated_at TEXT
    )
    """)

    # 1. 기존 테이블 (Presets, Scheduled Jobs, Confirmations)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS presets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        target_url TEXT NOT NULL,
        action_type TEXT NOT NULL,
        interval_min INTEGER NOT NULL DEFAULT 60,
        needs_confirmation INTEGER NOT NULL DEFAULT 1,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. 카페 활동 대상 테이블 (Targets)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        site_type TEXT NOT NULL DEFAULT 'naver_cafe',
        target_url TEXT NOT NULL,
        cafe_id TEXT,
        menu_id TEXT,
        activity_type TEXT NOT NULL, -- 'COMMENT', 'ATTENDANCE'
        daily_limit INTEGER NOT NULL DEFAULT 3,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 3. 샘플 문구 저장소 (Comment Pool)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS comment_pool (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        use_count INTEGER DEFAULT 0
    )
    """)

    # 4. 통합 작업 대기열 (Jobs)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
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
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 샘플 문구 50개 자동 삽입 (기본 예시)
    sample_texts = [
        "반갑습니다! 좋은 정보 감사합니다.",
        "안녕하세요, 가입 인사 드립니다.",
        "반가워요~ 자주 소통해요.",
        "좋은 아침입니다!",
        "정보 공유 감사드려요.",
        "환영합니다!",
        "오늘도 좋은 하루 되세요.",
        "우와, 정말 유익하네요.",
        "반가워요! 잘 부탁드립니다.",
        "안녕하세요~ 소통하며 지내요.",
        "반갑습니다! 잘 읽었습니다.",
        "좋은 글이네요, 감사해요.",
        "반가워요! 자주 뵈어요.",
        "유용한 정보네요, 고맙습니다.",
        "안녕하세요, 반갑습니다!",
        "좋은 글 감사합니다~",
        "반가워요! 오늘도 파이팅!",
        "반갑습니다, 잘 부탁드려요.",
        "안녕하세요! 응원합니다.",
        "좋은 정보네요! 잘 보고 갑니다.",
        "반가워요~ 반가워요!",
        "오늘도 즐거운 하루 되세요.",
        "글 잘 읽었습니다, 감사해요.",
        "반갑습니다! 반가워요!",
        "안녕하세요~ 반갑습니다.",
        "유익한 정보 공유 감사해요!",
        "반가워요! 자주 소통합시다.",
        "좋은 정보 감사드립니다.",
        "반갑습니다! 오늘도 행복하세요.",
        "안녕하세요, 좋은 글이네요.",
        "반가워요! 좋은 하루 되세요.",
        "정보 정말 감사합니다!",
        "반갑습니다~ 잘 부탁드려요.",
        "안녕하세요! 반가워요.",
        "좋은 정보 고맙습니다!",
        "반가워요! 글 잘 봤어요.",
        "반갑습니다! 소통해요.",
        "안녕하세요~ 자주 올게요.",
        "좋은 글 감사해요! 반가워요.",
        "반가워요! 반갑습니다.",
        "유익한 글 잘 읽고 갑니다.",
        "반갑습니다! 행복한 하루 되세요.",
        "안녕하세요! 응원할게요.",
        "좋은 정보 감사해요~",
        "반가워요! 자주 뵈었으면 좋겠네요.",
        "반갑습니다! 고마워요.",
        "안녕하세요, 유용한 정보 감사합니다.",
        "반가워요! 파이팅입니다.",
        "좋은 글 잘 읽었습니다!",
        "반갑습니다! 오늘도 파이팅하세요.",
    ]

    # 기존 데이터가 없을 때만 삽입
    count = conn.execute("SELECT count(*) FROM comment_pool").fetchone()[0]
    if count == 0:
        for text in sample_texts:
            conn.execute("INSERT INTO comment_pool (content) VALUES (?)", (text,))

    conn.commit()
    conn.close()
    print(f"HAD Tables initialized with {len(sample_texts)} sample comments.")


if __name__ == "__main__":
    init_had_tables()
