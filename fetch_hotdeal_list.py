#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_DB = Path('/root/.codex/worktrees/aafa/root/hotdeal.db')
BASE_URL = 'https://hotdeal.zip/api/deals.php'
UA = 'Mozilla/5.0'


def fetch_page(page: int, category: str, period: str | None, communities: str | None) -> list[dict]:
    params = {
        'page': page,
        'category': category,
        '_t': int(time.time() * 1000),
    }
    if period and category != 'all':
        params['period'] = period
    if communities:
        params['communities'] = communities

    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as f:
        data = f.read().decode('utf-8', errors='replace')
    js = json.loads(data)
    return js.get('data', [])


def ensure_schema(cur: sqlite3.Cursor) -> None:
    cur.execute('''
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
        fetched_at TEXT DEFAULT (datetime('now'))
    )
    ''')


def insert_rows(cur: sqlite3.Cursor, rows: list[dict]) -> int:
    sql = '''
    INSERT OR IGNORE INTO deals (
        id, title, price, category, site, created_at, views, thumbnail_url,
        seo_url, post_url, time, relative_time, relative_time_class,
        favicon_url, community_name, gradient
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    '''
    inserted = 0
    for r in rows:
        cur.execute(sql, (
            r.get('id'), r.get('title'), r.get('price'), r.get('category'), r.get('site'),
            r.get('created_at'), r.get('views'), r.get('thumbnail_url'), r.get('seo_url'),
            r.get('post_url'), r.get('time'), r.get('relative_time'), r.get('relative_time_class'),
            r.get('favicon_url'), r.get('community_name'), r.get('gradient')
        ))
        inserted += cur.rowcount
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description='Fetch hotdeal list pages into SQLite.')
    parser.add_argument('--db', default=str(DEFAULT_DB))
    parser.add_argument('--page-start', type=int, default=1)
    parser.add_argument('--page-end', type=int, default=1)
    parser.add_argument('--category', default='all')
    parser.add_argument('--period', default=None)
    parser.add_argument('--communities', default=None)
    parser.add_argument('--sleep', type=float, default=0.5)
    args = parser.parse_args()

    db_path = Path(args.db)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    ensure_schema(cur)

    total_fetched = 0
    total_inserted = 0

    for page in range(args.page_start, args.page_end + 1):
        rows = fetch_page(page, args.category, args.period, args.communities)
        total_fetched += len(rows)
        inserted = insert_rows(cur, rows)
        total_inserted += inserted
        conn.commit()
        if args.sleep:
            time.sleep(args.sleep)

    print(f"fetched={total_fetched} inserted={total_inserted} db={db_path}")


if __name__ == '__main__':
    main()
