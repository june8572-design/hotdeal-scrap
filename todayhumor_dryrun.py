#!/usr/bin/env python3
import argparse
import html
import math
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin
import urllib.request

BASE = "https://m.todayhumor.co.kr/"
UA = "Mozilla/5.0"

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
    "알아두면좋은", "초보자가이드", "초보자팁", "초보자용", "초보자를위한"
]

TIP_BOARD_NAME_KEYWORDS = [
    "지식인", "컴퓨터", "스마트폰", "DIY", "요리", "인테리어", "생활",
    "법", "심리학", "육아", "다이어트", "건강", "취업정보", "고민", 
    "연애", "결혼생활", "육아", "요리", "커피", "철학", "예술", 
    "역사", "패션", "뷰티", "인테리어", "IT", "프로그래머", "영화",
    "드라마", "음악", "스포츠", "자동차", "자전거", "카메라", "여행",
    "게임", "모바일게임", "스마트폰", "애플", "안드로이드", "취미"
]

EXCLUDE_BOARD_NAME_KEYWORDS = [
    "베스트", "베오베", "유머", "사이다", "멘붕"
]


def fetch(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as f:
            return f.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"❌ Fetch 실패: {url} - {e}")
        return ""


def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def parse_list_items(page_html: str):
    items = []
    # capture each anchor block for view.php
    pattern = re.compile(r'<a href="(view\.php[^"]+)">\s*(.*?)\s*</a>', re.S)
    for m in pattern.finditer(page_html):
        href = m.group(1)
        block = m.group(2)

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


def recency_bonus(date_str: str) -> float:
    # date format: YYYY/MM/DD HH:MM
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
    
    # 핵심 키워드 가중치 부여
    core_keywords = ["꿀팁", "팁", "방법", "노하우", "비법", "요령", "가이드"]
    
    for kw in TIP_KEYWORDS:
        if kw in title:
            # 핵심 키워드는 더 높은 점수
            if kw in core_keywords:
                bonus += 3
            else:
                bonus += 2
    
    bonus = min(bonus, 8)  # 최대 보너스 점수 증가
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
    # board links are of form list.php?table=xxx and text label is inside anchor
    boards = {}
    for m in re.finditer(r"<a\s+href=['\"]list\.php\?table=([^'\"]+)['\"][^>]*>(.*?)</a>", html_text, re.S):
        table = m.group(1)
        name = strip_tags(m.group(2))
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


def main():
    ap = argparse.ArgumentParser(description="TodayHumor dry-run collector (good/humor/tips)")
    ap.add_argument("--good-pages", type=int, default=1)
    ap.add_argument("--humor-pages", type=int, default=1)
    ap.add_argument("--tips-pages", type=int, default=1)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--tips-boards", default="")
    args = ap.parse_args()

    print("== 좋은글 ==")
    good_items = fetch_board(GOOD_BOARD, args.good_pages)
    for it in good_items[:args.top]:
        print(f"[{it['date']}] {it['title']} | 추천 {it['reco']} / 조회 {it['views']} | {it['url']}")

    print("\n== 유머 (점수 기반) ==")
    humor_items = fetch_board(HUMOR_BOARD, args.humor_pages)
    humor_items.sort(key=humor_score, reverse=True)
    for it in humor_items[:args.top]:
        score = humor_score(it)
        print(f"{score:.2f} | {it['title']} | 추천 {it['reco']} / 댓글 {it['comments']} / 조회 {it['views']} | {it['url']}")

    print("\n== 꿀팁 (점수 기반) ==")
    if args.tips_boards:
        tip_tables = [t.strip() for t in args.tips_boards.split(',') if t.strip()]
        boards = {t: t for t in tip_tables}
        fallback_all = False
    else:
        boards = discover_tip_boards()
        tip_tables = pick_tip_tables(boards)
        fallback_all = False
        if not tip_tables:
            print("(꿀팁) 게시판 후보를 찾지 못했습니다. --tips-boards로 테이블을 지정하세요.")
            tip_tables = []

    tip_items = []
    # 성능 향상: 최대 10개 게시판만 탐색
    tip_tables = tip_tables[:10]
    print(f"탐색할 꿀팁 게시판: {tip_tables}")
    
    for table in tip_tables:
        print(f"게시판 탐색 중: {table}")
        items = fetch_board(table, args.tips_pages)
        for it in items:
            it["board"] = boards.get(table, table)
            if not is_tip_candidate(it["title"]):
                continue
            tip_items.append(it)

    if not tip_items:
        print("(꿀팁) 키워드 매칭 결과가 없습니다. 키워드 확장 또는 --tips-boards 지정이 필요합니다.")
    else:
        tip_items.sort(key=tip_score, reverse=True)
        for it in tip_items[:args.top]:
            score = tip_score(it)
            board_name = it.get("board", "")
            print(f"{score:.2f} | {board_name} | {it['title']} | 추천 {it['reco']} / 댓글 {it['comments']} / 조회 {it['views']} | {it['url']}")


if __name__ == "__main__":
    main()
