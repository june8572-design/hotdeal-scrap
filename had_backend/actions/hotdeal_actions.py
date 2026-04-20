import json
import logging
import os
import re
import sqlite3
import time
import html
import urllib.request
import urllib.parse
import urllib.error
import subprocess
from pathlib import Path
from typing import Any

from had_backend.affiliate_classifier import classify_naver_url

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "hotdeal.db"
ENV_PATH = PROJECT_ROOT / ".env"
UA = "Mozilla/5.0"


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


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _ensure_affiliate_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(deals)")
    existing = {row[1] for row in cur.fetchall()}
    columns = [
        ("is_affiliate_candidate", "INTEGER"),
        ("affiliate_url_type", "TEXT"),
        ("canonical_product_name", "TEXT"),
        ("canonical_product_url", "TEXT"),
    ]
    for name, col_type in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {name} {col_type}")


def _ensure_enrich_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(deals)")
    existing = {row[1] for row in cur.fetchall()}
    columns = [
        ("price_summary", "TEXT"),
        ("details_text_clean", "TEXT"),
        ("details_fetched_at", "TEXT"),
        ("out_links_json", "TEXT"),
    ]
    for name, col_type in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {name} {col_type}")
    _ensure_affiliate_columns(conn)


def _classify_naver_url_with_redirect(
    source_url: str | None, final_url: str | None
) -> tuple[int | None, str | None]:
    src = (source_url or "").strip().lower()
    if "naver.me/" in src:
        return 1, "naver_me"

    base_cls, base_type = classify_naver_url(source_url)
    if base_cls is not None:
        return base_cls, base_type

    return classify_naver_url(final_url)


def _extract_product_name_from_html(html_text: str) -> str | None:
    og = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        html_text,
        re.I,
    )
    title = og.group(1).strip() if og else None
    if not title:
        tm = re.search(r"<title>(.*?)</title>", html_text, re.I | re.S)
        title = html.unescape(tm.group(1)).strip() if tm else None
    if not title:
        return None
    title = re.sub(r"\s*[:\-]\s*네이버.*$", "", title).strip()
    return title or None


def _fetch_canonical_naver_product(url: str) -> tuple[str | None, str | None]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as f:
            final_url = f.geturl()
            html_text = f.read().decode("utf-8", errors="replace")
        return _extract_product_name_from_html(html_text), final_url
    except Exception:
        return None, None


# --- Scraper Actions ---


def fetch_latest_deals(category: str = "all", page: int = 1) -> list[dict]:
    base_url = "https://hotdeal.zip/api/deals.php"
    params = {
        "page": page,
        "category": category,
        "_t": int(time.time() * 1000),
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as f:
            data = f.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        logger.error("hotdeal.zip API HTTP 오류 (코드 %s): %s", e.code, e.reason)
        raise RuntimeError(f"핫딜 API HTTP 오류 (코드 {e.code}): {e.reason}") from e
    except urllib.error.URLError as e:
        logger.error("hotdeal.zip API 요청 실패: %s", e)
        raise RuntimeError(f"핫딜 API 호출 실패: {e}") from e
    except TimeoutError as e:
        logger.error("hotdeal.zip API 타임아웃: %s", e)
        raise RuntimeError(f"핫딜 API 타임아웃: {e}") from e
    except Exception as e:
        logger.error("hotdeal.zip API 요청 중 예상치 못한 오류: %s", e)
        raise RuntimeError(f"핫딜 API 요청 실패: {e}") from e

    try:
        js = json.loads(data)
    except json.JSONDecodeError as e:
        logger.error("hotdeal.zip API 응답 파싱 실패: %s", e)
        raise RuntimeError(f"핫딜 API 응답 파싱 실패: {e}") from e
    except Exception as e:
        logger.error("hotdeal.zip API 응답 처리 중 예상치 못한 오류: %s", e)
        raise RuntimeError(f"핫딜 API 응답 처리 실패: {e}") from e

    return js.get("data", [])


def save_deals_to_db(deals: list[dict]) -> int:
    if not deals:
        logger.info("저장할 핫딜 데이터가 없음")
        return 0

    sql = """
    INSERT OR IGNORE INTO deals (
        id, title, price, category, site, created_at, views, thumbnail_url,
        seo_url, post_url, time, relative_time, relative_time_class,
        favicon_url, community_name, gradient
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    inserted = 0
    try:
        with get_conn() as conn:
            _ensure_affiliate_columns(conn)
            for r in deals:
                try:
                    conn.execute(
                        sql,
                        (
                            r.get("id"),
                            r.get("title"),
                            r.get("price"),
                            r.get("category"),
                            r.get("site"),
                            r.get("created_at"),
                            r.get("views"),
                            r.get("thumbnail_url"),
                            r.get("seo_url"),
                            r.get("post_url"),
                            r.get("time"),
                            r.get("relative_time"),
                            r.get("relative_time_class"),
                            r.get("favicon_url"),
                            r.get("community_name"),
                            r.get("gradient"),
                        ),
                    )
                    inserted += 1

                    # 분류는 enrich_deal()에서 수행 (out_links 기반)
                    # 여기서는 post_url(커뮤니티 URL)으로 분류 시도하면 부정확함

                    conn.execute(
                        """
                        UPDATE deals
                        SET is_affiliate_candidate = ?,
                            affiliate_url_type = ?,
                            canonical_product_name = ?,
                            canonical_product_url = ?
                        WHERE id = ?
                        """,
                        (
                            None,
                            None,
                            None,
                            None,
                            r.get("id"),
                        ),
                    )
                except sqlite3.Error as e:
                    logger.warning("개별 딜 저장 실패 (id=%s): %s", r.get("id"), e)
                    # Continue processing other deals even if one fails
                    continue
                except Exception as e:
                    logger.warning(
                        "개별 딜 저장 중 예상치 못한 오류 (id=%s): %s", r.get("id"), e
                    )
                    continue
            conn.commit()
    except sqlite3.Error as e:
        logger.error("핫딜 DB 저장 중 치명적 오류: %s", e)
        raise RuntimeError(f"핫딜 DB 저장 실패: {e}") from e
    except Exception as e:
        logger.error("핫딜 DB 저장 중 예상치 못한 오류: %s", e)
        raise RuntimeError(f"핫딜 DB 저장 실패: {e}") from e

    logger.info("핫딜 %d건 DB 저장 완료 (총 %d건 처리)", inserted, len(deals))
    return inserted


# --- Enrichment Actions ---


def _fetch_html(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as f:
            return f.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        logger.error("HTML fetch 실패 (%s): %s", url, e)
        raise RuntimeError(f"페이지 로딩 실패: {e}") from e
    except TimeoutError as e:
        logger.error("HTML fetch 타임아웃 (%s): %s", url, e)
        raise RuntimeError(f"페이지 로딩 타임아웃: {e}") from e


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p>", "\n", s)
    s = re.sub(r"(?i)</li>", "\n", s)
    s = re.sub(r"(?is)<script.*?</script>", "", s)
    s = re.sub(r"(?is)<style.*?</style>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"\r", "", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def _extract_links(html_fragment: str) -> list[str]:
    if not html_fragment:
        return []
    links = re.findall(r'href=["\']([^"\']+)["\']', html_fragment, re.I)
    normalized = []
    for link in links:
        if not link:
            continue
        absolute = urllib.parse.urljoin("https://hotdeal.zip/", link)
        if absolute.startswith("http://") or absolute.startswith("https://"):
            normalized.append(absolute)
    return list(dict.fromkeys(normalized))


def _unwrap_redirect_link(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        for key in ("url", "target", "redirect", "out"):
            if key in qs and qs[key]:
                decoded = urllib.parse.unquote(qs[key][0])
                if decoded.startswith("http://") or decoded.startswith("https://"):
                    return decoded
    except Exception:
        return url
    return url


def _extract_naver_links_from_full_html(html_text: str) -> list[str]:
    raw_links = re.findall(r"https?://[^\"'\s<>]+", html_text)
    cleaned = []
    for u in raw_links:
        uu = html.unescape(u)
        if "naver.me/" in uu or ".naver.com/" in uu:
            cleaned.append(uu)
    return list(dict.fromkeys(cleaned))


def _pick_naver_product_url(out_links: list[str]) -> str | None:
    preferred = [
        "naver.me/",
        "smartstore.naver.com/",
        "brand.naver.com/",
        "shopping.naver.com/",
        "search.shopping.naver.com/",
    ]
    lowered = [(u, u.lower()) for u in out_links]
    for p in preferred:
        for raw, low in lowered:
            if p in low:
                return raw
    return None


def _clean_text(s: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in s.split("\n")]
    lines = [line for line in lines if line and line != "📝 상품 정보"]
    return "\n".join(lines)


def _parse_page(html_text: str):
    ps = re.search(r'<div class="price-summary">(.*?)</div>', html_text, re.S)
    price_summary = _clean_text(_html_to_text(ps.group(1))) if ps else None

    ai_m = re.search(r'<div class="ai-price-content">(.*?)</div>', html_text, re.S)
    ai_html = ai_m.group(1) if ai_m else ""

    details_m = re.search(
        r'<div\s+class="product-details"[^>]*>(.*?)</div>', html_text, re.S
    )  # Simplified
    details_html = details_m.group(1) if details_m else None

    details_text_clean = None
    if details_html:
        details_text_clean = _clean_text(_html_to_text(details_html))

    out_links = []
    out_links.extend(_extract_links(ai_html))
    out_links.extend(_extract_links(details_html or ""))
    out_links.extend(_extract_naver_links_from_full_html(html_text))
    out_links = [_unwrap_redirect_link(u) for u in out_links]
    out_links = list(dict.fromkeys(out_links))

    return price_summary, details_text_clean, out_links


def enrich_deal(deal_id: int) -> dict:
    try:
        with get_conn() as conn:
            _ensure_enrich_columns(conn)
            row = conn.execute(
                "SELECT seo_url FROM deals WHERE id = ?", (deal_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Deal {deal_id} not found")

            seo_url = row["seo_url"]
            if not seo_url:
                logger.warning("Deal %d의 seo_url이 비어있음", deal_id)
                return {"price_summary": None, "details_text_clean": None}

            safe_slug = urllib.parse.quote(seo_url, safe="-_.~")
            url = f"https://hotdeal.zip/{safe_slug}"

            logger.info("Deal %d 상세 정보 수집 시작: %s", deal_id, url)
            html_text = _fetch_html(url)
            price_summary, text_clean, out_links = _parse_page(html_text)

            candidate_url = _pick_naver_product_url(out_links)
            is_affiliate_candidate = None
            affiliate_url_type = None
            canonical_product_name = None
            canonical_product_url = None

            if candidate_url:
                canonical_product_name, canonical_product_url = (
                    _fetch_canonical_naver_product(candidate_url)
                )
                is_affiliate_candidate, affiliate_url_type = (
                    _classify_naver_url_with_redirect(
                        candidate_url, canonical_product_url
                    )
                )

            conn.execute(
                """
                UPDATE deals
                SET price_summary = ?,
                    details_text_clean = ?,
                    out_links_json = ?,
                    is_affiliate_candidate = ?,
                    affiliate_url_type = ?,
                    canonical_product_name = ?,
                    canonical_product_url = ?,
                    details_fetched_at = datetime('now')
                WHERE id = ?
                """,
                (
                    price_summary,
                    text_clean,
                    json.dumps(out_links, ensure_ascii=False),
                    is_affiliate_candidate,
                    affiliate_url_type,
                    canonical_product_name,
                    canonical_product_url,
                    deal_id,
                ),
            )
            conn.commit()
            logger.info("Deal %d 상세 정보 수집 완료", deal_id)
    except ValueError:
        raise
    except RuntimeError as e:
        logger.error("Deal %d 상세 페이지 로딩 실패: %s", deal_id, e)
        raise
    except sqlite3.Error as e:
        logger.error("Deal %d DB 업데이트 실패: %s", deal_id, e)
        raise RuntimeError(f"Deal {deal_id} DB 저장 실패: {e}") from e
    except Exception as e:
        logger.error("Deal %d 상세 정보 수집 중 예상치 못한 오류: %s", deal_id, e)
        raise RuntimeError(f"Deal {deal_id} 상세 정보 수집 실패: {e}") from e

    return {"price_summary": price_summary, "details_text_clean": text_clean}


# --- LLM Actions ---


def generate_promo_text(deal_id: int) -> str:
    load_dotenv(ENV_PATH)
    # OmniRoute free-stack 사용 (NVIDIA API 대체)
    omniroute_url = os.getenv("OMNIRITE_URL", "http://192.168.50.110:20128/v1/chat/completions")
    model_name = os.getenv("PROMO_MODEL", "plan")  # plan → free-stack 폴백 가능

    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT title, price_summary, details_text_clean FROM deals WHERE id = ?",
                (deal_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Deal {deal_id} not found")

            prompt_prefix = (
                '제품 홍보글 재가공 해줘. 홍보글의 전개는 "어떤 제품이 특가가 떴는데 어떻게 싸고, 제품이 어떤 장점으로 추천하는 이유"를 적는 흐름으로 가자. '
                "절대 ai 스럽지 않게 사람이 가볍게 홍보하는투의 글이어야 해. 존댓말로 작성. 이모지 금지. 필수사항, 반드시 2~3 문장으로만 작성해줘. 다른 문장 추가 금지. 내가 제공하는 정보"
            )
            parts = [prompt_prefix]
            parts.append(f"1. 제품명 {row['title'] or ''}")
            if row["price_summary"]:
                parts.append(f"2. 가격요약 {row['price_summary']}")
            if row["details_text_clean"]:
                details = row["details_text_clean"]
                if len(details) > 400:
                    details = details[:400] + "..."
                parts.append(f"3. 제품홍보글 {details}")
            prompt = " ".join(parts).strip()

            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 256,
                "temperature": 0.2,
                "top_p": 0.8,
                "stream": False,
            }

            logger.info("Deal %d 프로모 글 생성 시작 (model=%s)", deal_id, model_name)
            cmd = [
                "curl",
                "-sS",
                "--connect-timeout", "30",
                "--max-time", "180",
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps(payload, ensure_ascii=False),
                omniroute_url,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=200)

            if result.returncode != 0:
                error_detail = result.stderr.strip() or "알 수 없는 curl 오류"
                logger.error("Deal %d API 호출 실패: %s", deal_id, error_detail)
                raise RuntimeError(f"API 호출 실패: {error_detail}")

            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.error(
                    "Deal %d API 응답 파싱 실패: %s (stdout=%s)", deal_id, e, result.stdout[:200]
                )
                raise RuntimeError(f"API 응답 파싱 실패: {e}") from e

            # 에러 응답 체크
            if "error" in data:
                err_msg = data["error"].get("message", str(data["error"]))
                logger.error("Deal %d API 에러: %s", deal_id, err_msg)
                raise RuntimeError(f"API 에러: {err_msg}")

            try:
                promo = data["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError) as e:
                logger.error(
                    "Deal %d API 응답 구조 이상: %s (response=%s)",
                    deal_id, e, json.dumps(data, ensure_ascii=False)[:300],
                )
                raise RuntimeError(f"API 응답 구조 이상: {e}") from e

            conn.execute(
                "UPDATE deals SET promo_text = ?, promo_generated_at = datetime('now') WHERE id = ?",
                (promo, deal_id),
            )
            conn.commit()
            logger.info("Deal %d 프로모 글 생성 완료", deal_id)
    except ValueError:
        raise
    except RuntimeError:
        raise
    except sqlite3.Error as e:
        logger.error("Deal %d 프로모 글 DB 저장 실패: %s", deal_id, e)
        raise RuntimeError(f"Deal {deal_id} 프로모 글 DB 저장 실패: {e}") from e
    except Exception as e:
        logger.error("Deal %d 프로모 글 생성 중 예상치 못한 오류: %s", deal_id, e)
        raise RuntimeError(f"Deal {deal_id} 프로모 글 생성 실패: {e}") from e

    return promo
