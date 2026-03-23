#!/usr/bin/env python3
import json
import re
import sqlite3
import time
import html
import urllib.request
import urllib.parse
from pathlib import Path

DB_PATH = Path('/root/.codex/worktrees/aafa/root/hotdeal.db')
UA = 'Mozilla/5.0'
SITES = {'네이버', '네이버쇼핑'}
SLEEP_SEC = 0.5


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req) as f:
        return f.read().decode('utf-8', errors='replace')


def find_div_inner(html_text: str, class_name: str) -> str | None:
    # Find the first <div class="{class_name}"> and return its inner HTML using a simple tag counter
    m = re.search(r'<div\s+class="%s"[^>]*>' % re.escape(class_name), html_text)
    if not m:
        return None
    start_tag_end = m.end()
    idx = start_tag_end
    depth = 1
    # scan for next <div ...> or </div>
    tag_re = re.compile(r'</div\s*>|<div\b[^>]*>', re.I)
    for tm in tag_re.finditer(html_text, idx):
        tag = tm.group(0).lower()
        if tag.startswith('<div'):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return html_text[start_tag_end:tm.start()]
    return None


def html_to_text(s: str) -> str:
    # Preserve basic line breaks
    s = re.sub(r'(?i)<br\s*/?>', '\n', s)
    s = re.sub(r'(?i)</p>', '\n', s)
    s = re.sub(r'(?i)</li>', '\n', s)
    # Remove scripts/styles
    s = re.sub(r'(?is)<script.*?</script>', '', s)
    s = re.sub(r'(?is)<style.*?</style>', '', s)
    # Strip remaining tags
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s)
    # Normalize whitespace
    s = re.sub(r'\r', '', s)
    s = re.sub(r'\n\s*\n+', '\n', s)
    return s.strip()


def clean_text(s: str) -> str:
    # Remove empty lines, collapse whitespace per line
    lines = [re.sub(r'\s+', ' ', line).strip() for line in s.split('\n')]
    lines = [line for line in lines if line]
    # Remove fixed section headers
    lines = [line for line in lines if line != '📝 상품 정보']
    return '\n'.join(lines)


def parse_price_table(ai_price_html: str):
    # Extract first table inside ai-price-content
    tm = re.search(r'<table>(.*?)</table>', ai_price_html, re.S)
    if not tm:
        return []
    table_html = tm.group(1)
    rows = re.findall(r'<tr>(.*?)</tr>', table_html, re.S)
    parsed = []
    for row in rows[1:]:
        cells = re.findall(r'<t[dh]>(.*?)</t[dh]>', row, re.S)
        cells = [clean_text(html_to_text(c)) for c in cells]
        if not cells:
            continue
        item = {
            'seller': cells[0] if len(cells) > 0 else None,
            'product_name': cells[1] if len(cells) > 1 else None,
            'price': cells[2] if len(cells) > 2 else None,
            'note': cells[3] if len(cells) > 3 else None,
        }
        parsed.append(item)
    return parsed


def parse_page(html_text: str):
    # Price summary
    ps = re.search(r'<div class="price-summary">(.*?)</div>', html_text, re.S)
    price_summary = clean_text(html_to_text(ps.group(1))) if ps else None

    # Price table
    ai = re.search(r'<div class="ai-price-content">(.*?)</div>', html_text, re.S)
    price_table = parse_price_table(ai.group(1)) if ai else []

    # Product details
    details_html = find_div_inner(html_text, 'product-details')
    details_images = []
    details_text_raw = None
    details_text_clean = None
    if details_html:
        details_images = re.findall(r'<img[^>]+src="([^"]+)"', details_html)
        details_text_raw = html_to_text(details_html)
        details_text_clean = clean_text(details_text_raw)

    return price_table, price_summary, details_text_raw, details_text_clean, details_images


def ensure_columns(cur):
    cur.execute('PRAGMA table_info(deals)')
    existing = {row[1] for row in cur.fetchall()}
    columns = [
        ('price_table_json', 'TEXT'),
        ('price_summary', 'TEXT'),
        ('details_text_raw', 'TEXT'),
        ('details_text_clean', 'TEXT'),
        ('details_images_json', 'TEXT'),
        ('details_fetched_at', 'TEXT'),
    ]
    for name, col_type in columns:
        if name not in existing:
            cur.execute(f'ALTER TABLE deals ADD COLUMN {name} {col_type}')


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    ensure_columns(cur)

    cur.execute(
        """
        SELECT id, seo_url, site
        FROM deals
        WHERE site IN (?, ?)
          AND (price_table_json IS NULL OR details_text_raw IS NULL)
        ORDER BY created_at DESC
        """,
        tuple(SITES)
    )
    rows = cur.fetchall()

    updated = 0
    errors = 0
    error_samples = []
    for deal_id, seo_url, site in rows:
        safe_slug = urllib.parse.quote(seo_url, safe='-_.~')
        url = f"https://hotdeal.zip/{safe_slug}"
        try:
            html_text = fetch_html(url)
            price_table, price_summary, text_raw, text_clean, images = parse_page(html_text)

            cur.execute(
                """
                UPDATE deals
                SET price_table_json = ?,
                    price_summary = ?,
                    details_text_raw = ?,
                    details_text_clean = ?,
                    details_images_json = ?,
                    details_fetched_at = datetime('now')
                WHERE id = ?
                """,
                (
                    json.dumps(price_table, ensure_ascii=False),
                    price_summary,
                    text_raw,
                    text_clean,
                    json.dumps(images, ensure_ascii=False),
                    deal_id,
                )
            )
            updated += 1
            time.sleep(SLEEP_SEC)
        except Exception as e:
            errors += 1
            if len(error_samples) < 3:
                error_samples.append((deal_id, str(e)))
            # Skip on error but continue
            cur.execute(
                """
                UPDATE deals
                SET details_fetched_at = datetime('now')
                WHERE id = ?
                """,
                (deal_id,)
            )
            continue

    conn.commit()
    print('matched', len(rows))
    print('updated', updated)
    print('errors', errors)
    if error_samples:
        print('error_samples', error_samples)


if __name__ == '__main__':
    main()
