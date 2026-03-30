#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv('HOTDEAL_DB_PATH', str(PROJECT_ROOT / 'hotdeal.db')))
ENV_PATH = Path(os.getenv('HOTDEAL_ENV_PATH', str(PROJECT_ROOT / '.env')))
MODEL = 'moonshotai/kimi-k2.5'

PROMPT_PREFIX = (
    "제품 홍보글 재가공 해줘. 홍보글의 전개는 \"어떤 제품이 특가가 떴는데 어떻게 싸고, 제품이 어떤 장점으로 추천하는 이유\"를 적는 흐름으로 가자. "
    "절대 ai 스럽지 않게 사람이 가볍게 홍보하는투의 글이어야 해. 존댓말로 작성. 이모지 금지. 필수사항, 반드시 2~3 문장으로만 작성해줘. 다른 문장 추가 금지. 내가 제공하는 정보"
)


def build_prompt(row: dict) -> str:
    parts = [PROMPT_PREFIX]
    parts.append(f"1. 제품명 {row.get('title') or ''}")
    if row.get('price_summary'):
        parts.append(f"2. 가격요약 {row['price_summary']}")
    if row.get('details_text_clean'):
        details = row['details_text_clean']
        # keep prompt size reasonable (short to encourage 2-3 sentences)
        if len(details) > 400:
            details = details[:400] + "..."
        parts.append(f"3. 제품홍보글 {details}")
    return " ".join(parts).strip()

def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def call_llm(prompt: str) -> str:
    load_dotenv(ENV_PATH)
    api_key = os.environ.get('NVIDIA_API_KEY')
    if not api_key:
        raise SystemExit('NVIDIA_API_KEY is not set')

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
        "temperature": 0.30,
        "top_p": 1.00,
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }

    cmd = [
        'curl', '-sS',
        '-H', f'Authorization: Bearer {api_key}',
        '-H', 'Content-Type: application/json',
        '-H', 'Accept: application/json',
        '-d', json.dumps(payload),
        'https://integrate.api.nvidia.com/v1/chat/completions'
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or 'curl failed')

    data = json.loads(res.stdout)
    return data['choices'][0]['message']['content'].strip()


def ensure_columns(cur):
    cur.execute('PRAGMA table_info(deals)')
    existing = {row[1] for row in cur.fetchall()}
    columns = [
        ('promo_text', 'TEXT'),
        ('promo_generated_at', 'TEXT'),
    ]
    for name, col_type in columns:
        if name not in existing:
            cur.execute(f'ALTER TABLE deals ADD COLUMN {name} {col_type}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=int, help='deal id')
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    ensure_columns(cur)

    if args.id:
        cur.execute(
            """
            SELECT id, title, price_summary, details_text_clean
            FROM deals
            WHERE id = ?
            """,
            (args.id,)
        )
    else:
        cur.execute(
            """
            SELECT id, title, price_summary, details_text_clean
            FROM deals
            WHERE details_text_clean IS NOT NULL
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.limit,)
        )

    rows = cur.fetchall()
    for row in rows:
        prompt = build_prompt(dict(row))
        if args.dry_run:
            print(f"[ID {row['id']}]\n{prompt}\n")
            continue
        promo = call_llm(prompt)
        cur.execute(
            """
            UPDATE deals
            SET promo_text = ?, promo_generated_at = datetime('now')
            WHERE id = ?
            """,
            (promo, row['id'])
        )
        conn.commit()
        print(f"[ID {row['id']}] {promo}")


if __name__ == '__main__':
    main()
