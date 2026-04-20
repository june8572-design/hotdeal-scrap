#!/usr/bin/env python3
"""오늘의유머 '꿀팁' 키워드 검색 → DB 저장 스크립트.

사용법:
  python todayhumor_tip_scraper.py                   # 1페이지 수집 (기본)
  python todayhumor_tip_scraper.py --pages 5          # 5페이지 수집
  python todayhumor_tip_scraper.py --keyword 생활꿀팁  # 다른 키워드로 검색
  python todayhumor_tip_scraper.py --save             # DB 저장
  python todayhumor_tip_scraper.py --fetch-details    # 본문 상세도 수집
"""
import argparse
import html
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, quote

import urllib.request

BASE = "https://m.todayhumor.co.kr/"
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.getenv("HOTDEAL_DB_PATH", str(PROJECT_ROOT / "hotdeal.db")))

SEARCH_URL_TPL = (
    "{base}list.php?kind=search&table=total"
    "&search_table_name=total&keyfield=subject"
    "&keyword={keyword}&page={page}"
)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as f:
        return f.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------
def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def html_to_text(s: str) -> str:
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p>", "\n", s)
    s = re.sub(r"(?i)</div>", "\n", s)
    s = re.sub(r"(?is)<script.*?</script>", "", s)
    s = re.sub(r"(?is)<style.*?</style>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace("\r", "")
    s = re.sub(r"\xa0", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    lines = [re.sub(r"\s+", " ", line).strip() for line in s.split("\n")]
    return "\n".join(line for line in lines if line)


def extract(pattern: str, text: str, flags: int = 0, default: str = "") -> str:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else default


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------
def parse_list_items(page_html: str) -> list[dict]:
    """오늘의유머 목록 HTML → 게시물 리스트"""
    items = []
    pattern = re.compile(r'<a href="(view\.php[^"]+)">\s*(.*?)\s*</a>', re.S)
    for match in pattern.finditer(page_html):
        href = match.group(1)
        block = match.group(2)

        no_m = re.search(r'<span class="list_no">(\d+)</span>', block)
        date_m = re.search(r'<span class="listDate">([^<]+)</span>', block)
        title_m = re.search(r'<h2 class="listSubject">(.*?)</h2>', block, re.S)
        view_m = re.search(r'<span class="list_viewCount">(\d+)</span>', block)
        ok_m = re.search(r'<span class="list_okNokCount">(\d+)</span>', block)
        comment_m = re.search(r'<span class="list_comment_count">(.*?)</span>', block, re.S)
        writer_m = re.search(r'<span class="list_writer"[^>]*>([^<]*)</span>', block)

        title = strip_tags(title_m.group(1)) if title_m else ""
        if not title:
            continue

        comment_raw = strip_tags(comment_m.group(1)) if comment_m else ""
        comment_count = int(re.sub(r"\D", "", comment_raw) or 0)

        items.append({
            "url": urljoin(BASE, href),
            "no": int(no_m.group(1)) if no_m else None,
            "date": date_m.group(1).strip() if date_m else "",
            "writer": writer_m.group(1).strip() if writer_m else "",
            "title": title,
            "views": int(view_m.group(1)) if view_m else 0,
            "reco": int(ok_m.group(1)) if ok_m else 0,
            "comments": comment_count,
        })
    return items


def parse_detail_page(page_html: str) -> dict:
    """게시물 상세 HTML → 본문/이미지"""
    title = html_to_text(extract(r'<span class="view_subject">(.*?)</span>', page_html, re.S))
    writer = html_to_text(extract(
        r"<span id='viewPageWriterNameSpan'[^>]*>(.*?)</span>", page_html, re.S
    ))
    date_str = html_to_text(extract(r'<span class="view_bestRegDate"[^>]*>(.*?)</span>', page_html, re.S))

    reco_raw = html_to_text(extract(r'<span class="view_okNok">(.*?)</span>', page_html, re.S))
    views_raw = html_to_text(extract(r'<span class="view_viewCount">(.*?)</span>', page_html, re.S))
    comments_raw = html_to_text(extract(r'<span class="view_replyCount">(.*?)</span>', page_html, re.S))

    content_html = extract(
        r'<div class="viewContent" id="viewContent">(.*?)</div>\s*(?:<table class=\'view_page_source_div\'|<!--출처-->)',
        page_html, re.S,
    )
    if not content_html:
        content_html = extract(r'<div class="viewContent" id="viewContent">(.*?)</div>', page_html, re.S)

    content_text = html_to_text(content_html)

    images = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content_html)
    images = [urljoin(BASE, u) for u in images if not u.startswith("data:")]

    source_text = ""
    source_m = re.search(r"<div class='view_page_source_div'[^>]*>(.*?)</div>", page_html, re.S)
    if source_m:
        source_text = html_to_text(source_m.group(1))

    return {
        "title_detail": title,
        "writer": writer,
        "date": date_str,
        "reco": int(re.sub(r"\D", "", reco_raw) or 0),
        "views": int(re.sub(r"\D", "", views_raw) or 0),
        "comments": int(re.sub(r"\D", "", comments_raw) or 0),
        "content_html": content_html,
        "content_text": content_text,
        "content_images_json": json.dumps(images, ensure_ascii=False) if images else None,
        "source_text": source_text or None,
    }


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------
def search_tips(keyword: str, pages: int) -> list[dict]:
    """꿀팁 검색 → 게시물 리스트"""
    all_items = []
    for page in range(1, pages + 1):
        url = SEARCH_URL_TPL.format(base=BASE, keyword=quote(keyword), page=page)
        print(f"  페이지 {page} 수집 중...")
        try:
            html_text = fetch(url)
        except Exception as e:
            print(f"  ❌ 페이지 {page} fetch 실패: {e}")
            break
        items = parse_list_items(html_text)
        if not items:
            print(f"  페이지 {page}: 결과 없음 (수집 종료)")
            break
        all_items.extend(items)
        print(f"  페이지 {page}: {len(items)}건")
        if page < pages:
            time.sleep(0.5)
    return all_items


def enrich_with_details(items: list[dict]) -> int:
    """게시물 상세 본문 수집"""
    count = 0
    for item in items:
        url = item["url"]
        try:
            detail_html = fetch(url)
        except Exception as e:
            print(f"  ❌ 상세 fetch 실패: {url} - {e}")
            continue
        detail = parse_detail_page(detail_html)
        item.update(detail)
        count += 1
        time.sleep(0.3)
    return count


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def ensure_schema(cur: sqlite3.Cursor) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS todayhumor_tips (
            url TEXT PRIMARY KEY,
            no INTEGER,
            title TEXT,
            writer TEXT,
            date TEXT,
            views INTEGER,
            reco INTEGER,
            comments INTEGER,
            keyword TEXT,
            content_html TEXT,
            content_text TEXT,
            content_images_json TEXT,
            source_text TEXT,
            detail_fetched_at TEXT,
            collected_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # 마이그레이션
    cur.execute("PRAGMA table_info(todayhumor_tips)")
    existing = {row[1] for row in cur.fetchall()}
    for col, typ in [("keyword", "TEXT"), ("content_html", "TEXT"), ("content_text", "TEXT"),
                     ("content_images_json", "TEXT"), ("source_text", "TEXT"), ("detail_fetched_at", "TEXT")]:
        if col not in existing:
            cur.execute(f"ALTER TABLE todayhumor_tips ADD COLUMN {col} {typ}")


def save_posts(cur: sqlite3.Cursor, items: list[dict], keyword: str) -> int:
    if not items:
        return 0
    sql = """
        INSERT INTO todayhumor_tips (
            url, no, title, writer, date, views, reco, comments, keyword,
            content_html, content_text, content_images_json, source_text,
            detail_fetched_at, collected_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(url) DO UPDATE SET
            title = excluded.title,
            views = excluded.views,
            reco = excluded.reco,
            comments = excluded.comments,
            keyword = excluded.keyword,
            content_html = COALESCE(excluded.content_html, todayhumor_tips.content_html),
            content_text = COALESCE(excluded.content_text, todayhumor_tips.content_text),
            content_images_json = COALESCE(excluded.content_images_json, todayhumor_tips.content_images_json),
            source_text = COALESCE(excluded.source_text, todayhumor_tips.source_text),
            detail_fetched_at = COALESCE(excluded.detail_fetched_at, todayhumor_tips.detail_fetched_at),
            updated_at = datetime('now')
    """
    saved = 0
    now = datetime.now().isoformat()
    for item in items:
        cur.execute(sql, (
            item["url"], item.get("no"), item["title"], item.get("writer", ""),
            item.get("date", ""), item.get("views", 0), item.get("reco", 0),
            item.get("comments", 0), keyword,
            item.get("content_html"), item.get("content_text"),
            item.get("content_images_json"), item.get("source_text"),
            now if item.get("content_text") else None,
        ))
        saved += cur.rowcount
    return saved


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="오늘의유머 꿀팁 검색 수집기")
    ap.add_argument("--keyword", default="꿀팁", help="검색 키워드 (기본: 꿀팁)")
    ap.add_argument("--pages", type=int, default=3, help="검색 페이지 수 (기본: 3)")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--save", action="store_true", help="DB 저장")
    ap.add_argument("--fetch-details", action="store_true", help="본문 상세 수집")
    args = ap.parse_args()

    print(f"== '{args.keyword}' 키워드 검색 ({args.pages}페이지) ==")
    items = search_tips(args.keyword, args.pages)
    print(f"\n수집 완료: {len(items)}건\n")

    for item in items:
        print(f"[{item['date']}] {item['title']} | 추천 {item['reco']} / 댓글 {item['comments']} / 조회 {item['views']}")

    if args.fetch_details and items:
        print(f"\n== 상세 본문 수집 ==")
        detail_count = enrich_with_details(items)
        print(f"상세 수집 완료: {detail_count}건")

    if args.save:
        conn = sqlite3.connect(Path(args.db))
        cur = conn.cursor()
        ensure_schema(cur)
        saved = save_posts(cur, items, args.keyword)
        conn.commit()
        conn.close()
        print(f"\nDB 저장 완료: {saved}건 → {args.db}")


if __name__ == "__main__":
    main()
