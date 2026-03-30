#!/usr/bin/env python3
import argparse
import html
import json
import math
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import urllib.request

BASE = "https://m.todayhumor.co.kr/"
UA = "Mozilla/5.0"
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.getenv("HOTDEAL_DB_PATH", str(PROJECT_ROOT / "hotdeal.db")))

GOOD_BOARD = "lovestory"
HUMOR_BOARD = "humordata"

TIP_KEYWORDS = [
    "꿀팁", "팁", "방법", "노하우", "정리", "가이드", "체크리스트",
    "비법", "요령", "자주", "FAQ", "알아두면", "유용한", "생활꿀팁",
    "효율적", "시간절약", "비용절감", "초보자", "초간단", "쉽게",
    "간편하게", "꿀정보", "무료", "할인", "앱테크", "부업", "수익",
    "아르바이트", "투자", "재테크", "추천", "비교", "최저가", "특가",
    "이벤트", "공짜", "무료체험", "사용법", "설명서", "가이드북",
    "메뉴얼", "튜토리얼", "팁클", "꿀Tip", "생활정보", "실용적",
    "알아두면좋은", "초보자가이드", "초보자팁", "초보자용", "초보자를위한",
]

TIP_BOARD_NAME_KEYWORDS = [
    "지식인", "컴퓨터", "스마트폰", "DIY", "요리", "인테리어", "생활",
    "법", "심리학", "육아", "다이어트", "건강", "취업정보", "고민",
    "연애", "결혼생활", "육아", "요리", "커피", "철학", "예술",
    "역사", "패션", "뷰티", "인테리어", "IT", "프로그래머", "영화",
    "드라마", "음악", "스포츠", "자동차", "자전거", "카메라", "여행",
    "게임", "모바일게임", "스마트폰", "애플", "안드로이드", "취미",
]

EXCLUDE_BOARD_NAME_KEYWORDS = [
    "베스트", "베오베", "유머", "사이다", "멘붕",
]


def fetch(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as f:
            return f.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"❌ Fetch 실패: {url} - {exc}")
        return ""


def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def parse_list_items(page_html: str) -> list[dict]:
    items = []
    pattern = re.compile(r'<a href="(view\.php[^"]+)">\s*(.*?)\s*</a>', re.S)
    for match in pattern.finditer(page_html):
        href = match.group(1)
        block = match.group(2)

        no_m = re.search(r"<span class=\"list_no\">(\d+)</span>", block)
        date_m = re.search(r"<span class=\"listDate\">([^<]+)</span>", block)
        writer_m = re.search(r"<span class=\"list_writer\"[^>]*>([^<]*)</span>", block)
        title_m = re.search(r"<h2 class=\"listSubject\">(.*?)</h2>", block, re.S)
        comment_m = re.search(r"<span class=\"list_comment_count\">(.*?)</span>", block, re.S)
        view_m = re.search(r"<span class=\"list_viewCount\">(\d+)</span>", block)
        ok_m = re.search(r"<span class=\"list_okNokCount\">(\d+)</span>", block)

        title = strip_tags(title_m.group(1)) if title_m else ""
        comment_raw = strip_tags(comment_m.group(1)) if comment_m else ""
        comment_count = int(re.sub(r"\D", "", comment_raw) or 0)

        items.append(
            {
                "url": urljoin(BASE, href),
                "no": int(no_m.group(1)) if no_m else None,
                "date": date_m.group(1).strip() if date_m else "",
                "writer": writer_m.group(1).strip() if writer_m else "",
                "title": title,
                "views": int(view_m.group(1)) if view_m else 0,
                "reco": int(ok_m.group(1)) if ok_m else 0,
                "comments": comment_count,
            }
        )
    return items


def recency_bonus(date_str: str) -> float:
    try:
        dt = datetime.strptime(date_str, "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)
        hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        if hours <= 0:
            return 1.0
        return max(0.0, (72.0 - hours) / 72.0)
    except Exception:
        return 0.0


def humor_score(item: dict) -> float:
    return (item["reco"] * 3) + (item["comments"] * 2) + math.log1p(item["views"]) + recency_bonus(item["date"])


def tip_score(item: dict) -> float:
    bonus = 0
    title = item["title"]
    core_keywords = ["꿀팁", "팁", "방법", "노하우", "비법", "요령", "가이드"]

    for kw in TIP_KEYWORDS:
        if kw in title:
            bonus += 3 if kw in core_keywords else 2

    bonus = min(bonus, 8)
    return (item["reco"] * 2) + (item["comments"] * 2) + math.log1p(item["views"]) + bonus + recency_bonus(item["date"])


def is_tip_candidate(title: str) -> bool:
    return any(kw in title for kw in TIP_KEYWORDS)


def fetch_board(table: str, pages: int) -> list[dict]:
    results = []
    for page in range(1, pages + 1):
        url = f"{BASE}list.php?table={table}&page={page}"
        html_text = fetch(url)
        results.extend(parse_list_items(html_text))
        time.sleep(0.5)
    return results


def discover_tip_boards() -> dict:
    html_text = fetch(BASE)
    boards = {}
    for match in re.finditer(r"<a\s+href=['\"]list\.php\?table=([^'\"]+)['\"][^>]*>(.*?)</a>", html_text, re.S):
        table = match.group(1)
        name = strip_tags(match.group(2))
        if name:
            boards[table] = name
    return boards


def pick_tip_tables(boards: dict) -> list[str]:
    selected = []
    for table, name in boards.items():
        if any(kw in name for kw in EXCLUDE_BOARD_NAME_KEYWORDS):
            continue
        for kw in TIP_BOARD_NAME_KEYWORDS:
            if kw in name:
                selected.append(table)
                break
    return sorted(set(selected))


def ensure_storage_schema(cur: sqlite3.Cursor) -> None:
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS todayhumor_posts (
            url TEXT PRIMARY KEY,
            no INTEGER,
            title TEXT,
            writer TEXT,
            date TEXT,
            views INTEGER,
            reco INTEGER,
            comments INTEGER,
            board_table TEXT,
            board_name TEXT,
            category TEXT,
            score REAL,
            raw_json TEXT,
            collected_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        '''
    )


def save_posts(cur: sqlite3.Cursor, items: list[dict]) -> int:
    if not items:
        return 0

    sql = '''
    INSERT INTO todayhumor_posts (
        url, no, title, writer, date, views, reco, comments,
        board_table, board_name, category, score, raw_json,
        collected_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
    ON CONFLICT(url) DO UPDATE SET
        no = excluded.no,
        title = excluded.title,
        writer = excluded.writer,
        date = excluded.date,
        views = excluded.views,
        reco = excluded.reco,
        comments = excluded.comments,
        board_table = excluded.board_table,
        board_name = excluded.board_name,
        category = excluded.category,
        score = excluded.score,
        raw_json = excluded.raw_json,
        updated_at = datetime('now')
    '''

    saved = 0
    for item in items:
        cur.execute(
            sql,
            (
                item.get("url"),
                item.get("no"),
                item.get("title"),
                item.get("writer"),
                item.get("date"),
                item.get("views", 0),
                item.get("reco", 0),
                item.get("comments", 0),
                item.get("board_table"),
                item.get("board_name"),
                item.get("category"),
                item.get("score"),
                json.dumps(item, ensure_ascii=False),
            ),
        )
        saved += 1
    return saved


def annotate_good_items(items: list[dict]) -> list[dict]:
    for item in items:
        item["board_table"] = GOOD_BOARD
        item["board_name"] = "좋은글"
        item["category"] = "good"
        item["score"] = None
    return items


def annotate_humor_items(items: list[dict]) -> list[dict]:
    for item in items:
        item["board_table"] = HUMOR_BOARD
        item["board_name"] = "유머자료"
        item["category"] = "humor"
        item["score"] = humor_score(item)
    return items


def collect_tip_items(tip_tables: list[str], boards: dict, tips_pages: int) -> list[dict]:
    tip_items = []
    for table in tip_tables[:10]:
        print(f"게시판 탐색 중: {table}")
        items = fetch_board(table, tips_pages)
        for item in items:
            item["board"] = boards.get(table, table)
            item["board_table"] = table
            item["board_name"] = boards.get(table, table)
            item["category"] = "tip"
            if not is_tip_candidate(item["title"]):
                continue
            item["score"] = tip_score(item)
            tip_items.append(item)
    return tip_items


def main() -> None:
    ap = argparse.ArgumentParser(description="TodayHumor dry-run collector (good/humor/tips)")
    ap.add_argument("--good-pages", type=int, default=1)
    ap.add_argument("--humor-pages", type=int, default=1)
    ap.add_argument("--tips-pages", type=int, default=1)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--tips-boards", default="")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    all_items = []

    print("== 좋은글 ==")
    good_items = annotate_good_items(fetch_board(GOOD_BOARD, args.good_pages))
    all_items.extend(good_items)
    for item in good_items[:args.top]:
        print(f"[{item['date']}] {item['title']} | 추천 {item['reco']} / 조회 {item['views']} | {item['url']}")

    print("\n== 유머 (점수 기반) ==")
    humor_items = annotate_humor_items(fetch_board(HUMOR_BOARD, args.humor_pages))
    all_items.extend(humor_items)
    humor_items.sort(key=humor_score, reverse=True)
    for item in humor_items[:args.top]:
        score = humor_score(item)
        print(f"{score:.2f} | {item['title']} | 추천 {item['reco']} / 댓글 {item['comments']} / 조회 {item['views']} | {item['url']}")

    print("\n== 꿀팁 (점수 기반) ==")
    if args.tips_boards:
        tip_tables = [table.strip() for table in args.tips_boards.split(',') if table.strip()]
        boards = {table: table for table in tip_tables}
    else:
        boards = discover_tip_boards()
        tip_tables = pick_tip_tables(boards)
        if not tip_tables:
            print("(꿀팁) 게시판 후보를 찾지 못했습니다. --tips-boards로 테이블을 지정하세요.")
            tip_tables = []

    print(f"탐색할 꿀팁 게시판: {tip_tables[:10]}")
    tip_items = collect_tip_items(tip_tables, boards, args.tips_pages)

    if not tip_items:
        print("(꿀팁) 키워드 매칭 결과가 없습니다. 키워드 확장 또는 --tips-boards 지정이 필요합니다.")
    else:
        tip_items.sort(key=tip_score, reverse=True)
        all_items.extend(tip_items)
        for item in tip_items[:args.top]:
            score = tip_score(item)
            board_name = item.get("board", "")
            print(f"{score:.2f} | {board_name} | {item['title']} | 추천 {item['reco']} / 댓글 {item['comments']} / 조회 {item['views']} | {item['url']}")

    if args.save:
        conn = sqlite3.connect(Path(args.db))
        cur = conn.cursor()
        ensure_storage_schema(cur)
        saved = save_posts(cur, all_items)
        conn.commit()
        conn.close()
        print(f"\n저장 완료: {saved}건 -> {args.db}")


if __name__ == "__main__":
    main()
