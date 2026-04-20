import sqlite3
import json
import re
import sys
import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

# had_backend 모듈을 임포트할 수 있도록 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from had_backend.affiliate_classifier import (
    classify_naver_url,
    classify_out_links,
    parse_out_links_json,
)

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

# DB 경로: 환경변수 우선, 없으면 프로젝트 루트 기준
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = Path(os.getenv("HOTDEAL_DB_PATH", str(PROJECT_ROOT / "hotdeal.db")))
STATIC_DIR = PROJECT_ROOT / "had_backend" / "static"
BRANDCONNECT_PENDING_SQL = "(brand_connector_status IN ('processing', 'pending') OR brand_connector_status IS NULL OR brand_connector_status = '')"
AUTO_RUN_BRANDCONNECT = os.getenv("AUTO_RUN_BRANDCONNECT", "1").strip() not in {
    "0",
    "false",
    "False",
}
BRANDCONNECT_PROCESSING_TIMEOUT_SEC = int(
    os.getenv("BRANDCONNECT_PROCESSING_TIMEOUT_SEC", "600")
)


def get_db_path() -> Path:
    return DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def ensure_runtime_indexes() -> None:
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_deals_site ON deals(site)",
        "CREATE INDEX IF NOT EXISTS idx_deals_bc_status ON deals(brand_connector_status)",
        "CREATE INDEX IF NOT EXISTS idx_deals_fetched_at ON deals(fetched_at)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_target_id ON jobs(target_id)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_preset_id ON jobs(preset_id)",
        "CREATE INDEX IF NOT EXISTS idx_presets_active ON presets(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_targets_active ON targets(is_active)",
    ]

    try:
        with get_conn() as conn:
            for statement in statements:
                conn.execute(statement)
            conn.commit()
    except sqlite3.OperationalError:
        return


def ensure_runtime_columns() -> None:
    columns = [
        ("is_affiliate_candidate", "INTEGER"),
        ("affiliate_url_type", "TEXT"),
        ("canonical_product_name", "TEXT"),
        ("canonical_product_url", "TEXT"),
    ]
    try:
        with get_conn() as conn:
            existing = {
                row[1] for row in conn.execute("PRAGMA table_info(deals)").fetchall()
            }
            for name, col_type in columns:
                if name not in existing:
                    conn.execute(f"ALTER TABLE deals ADD COLUMN {name} {col_type}")
            conn.commit()
    except sqlite3.OperationalError:
        return


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _error_response(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "message": message}, status_code=status_code)


def _start_brandconnect_link_generation(deal_ids: list[int]) -> int:
    """브랜드커넥터 링크 발급 v2 (xvfb + 헤풀 Playwright)"""
    script_path = PROJECT_ROOT / "brandconnect_v2.py"

    deal_id_arg = ",".join(str(i) for i in deal_ids)
    log_path = PROJECT_ROOT / ".debug" / "brandconnect" / "runner.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as log_file:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        args = [
            sys.executable,
            str(script_path),
            "--deal-id", deal_id_arg,
        ]

        process = subprocess.Popen(
            args,
            env=env,
            cwd=str(PROJECT_ROOT),
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
    return process.pid


def _classify_url_for_link_generation(conn: sqlite3.Connection, deal_id: int) -> tuple[int | None, str | None]:
    """링크 생성 전 최종 분류값을 계산.

    우선순위:
    1) out_links_json (가장 신뢰)
    2) canonical_product_url
    3) post_url
    """
    row = conn.execute(
        """
        SELECT out_links_json, canonical_product_url, post_url, is_affiliate_candidate, affiliate_url_type
        FROM deals
        WHERE id = ?
        """,
        (deal_id,),
    ).fetchone()
    if not row:
        return None, None

    out_links = parse_out_links_json(row["out_links_json"])
    cls, typ = classify_out_links(out_links)
    if cls is not None:
        return cls, typ

    for url in (row["canonical_product_url"], row["post_url"]):
        cls, typ = classify_naver_url(url)
        if cls is not None:
            return cls, typ

    # 기존값 fallback
    return row["is_affiliate_candidate"], row["affiliate_url_type"]


async def handle_http_exception(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"ok": False, "detail": exc.detail, "message": exc.detail},
            status_code=exc.status_code,
        )

    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


async def _read_json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="유효한 JSON 본문이 필요합니다."
        ) from exc

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON 객체 본문이 필요합니다.")

    return body


def _require_fields(body: dict[str, Any], *fields: str) -> None:
    missing = [field for field in fields if body.get(field) in (None, "")]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"필수 필드가 없습니다: {', '.join(missing)}",
        )


def _parse_positive_int(value: str | None, default: int, field_name: str) -> int:
    if value in (None, ""):
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"{field_name}는 정수여야 합니다."
        ) from exc

    if parsed < 1:
        raise HTTPException(
            status_code=400, detail=f"{field_name}는 1 이상이어야 합니다."
        )

    return parsed


def _count_rows(conn: sqlite3.Connection, sql: str, default: int = 0) -> int:
    try:
        return conn.execute(sql).fetchone()[0]
    except sqlite3.OperationalError:
        return default


def _serve_static_page(filename: str) -> FileResponse:
    return FileResponse(str(STATIC_DIR / filename))


def _parse_naver_cafe_url(url: str) -> tuple[str | None, str | None]:
    cafe_id = None
    menu_id = None
    m_cafe = re.search(r"cafes/(\d+)", url)
    if m_cafe:
        cafe_id = m_cafe.group(1)
    m_menu = re.search(r"menus/(\d+)", url)
    if m_menu:
        menu_id = m_menu.group(1)
    return cafe_id, menu_id


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


# --- API 엔드포인트 ---


async def create_preset(request: Request) -> JSONResponse:
    body = await _read_json(request)
    _require_fields(body, "name", "target_url", "action_type")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO presets (name, target_url, action_type, source_type, interval_min, needs_confirmation, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (
                body["name"],
                body["target_url"],
                body["action_type"],
                body.get("source_type", "hotdeal"),
                body.get("interval_min", 60),
                int(body.get("needs_confirmation", 1)),
            ),
        )
        row = conn.execute(
            "SELECT * FROM presets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        conn.commit()
    return JSONResponse(_row_to_dict(row), status_code=201)


async def list_presets(request: Request) -> JSONResponse:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM presets ORDER BY id DESC").fetchall()
    return JSONResponse({"items": [_row_to_dict(r) for r in rows]})


async def delete_preset(request: Request) -> JSONResponse:
    preset_id = int(request.path_params["preset_id"])
    with get_conn() as conn:
        conn.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
        conn.commit()
    return JSONResponse({"ok": True, "message": f"프리셋 {preset_id} 삭제됨"})


async def toggle_preset(request: Request) -> JSONResponse:
    preset_id = int(request.path_params["preset_id"])
    body = await _read_json(request)
    with get_conn() as conn:
        # 업데이트할 필드 동적 구성
        updates = []
        params = []
        if "is_active" in body:
            updates.append("is_active = ?")
            params.append(body["is_active"])
        if "interval_min" in body:
            updates.append("interval_min = ?")
            params.append(int(body["interval_min"]))
        if not updates:
            return _error_response("업데이트할 필드가 없습니다.")
        updates.append("updated_at = datetime('now')")
        params.append(preset_id)
        sql = f"UPDATE presets SET {', '.join(updates)} WHERE id = ?"
        conn.execute(sql, tuple(params))
        conn.commit()
        row = conn.execute("SELECT * FROM presets WHERE id = ?", (preset_id,)).fetchone()
    return JSONResponse(_row_to_dict(row))


async def update_preset(request: Request) -> JSONResponse:
    """프리셋 부분 업데이트 (interval_min 등)"""
    preset_id = int(request.path_params["preset_id"])
    body = await _read_json(request)
    with get_conn() as conn:
        updates = []
        params = []
        for field in ["interval_min", "is_active", "needs_confirmation", "name", "source_type"]:
            if field in body:
                updates.append(f"{field} = ?")
                params.append(body[field])
        if not updates:
            return _error_response("업데이트할 필드가 없습니다.")
        updates.append("updated_at = datetime('now')")
        params.append(preset_id)
        conn.execute(f"UPDATE presets SET {', '.join(updates)} WHERE id = ?", tuple(params))
        conn.commit()
        row = conn.execute("SELECT * FROM presets WHERE id = ?", (preset_id,)).fetchone()
    return JSONResponse(_row_to_dict(row))


async def create_target(request: Request) -> JSONResponse:
    body = await _read_json(request)
    _require_fields(body, "name", "target_url")
    url = body.get("target_url")
    cafe_id, menu_id = _parse_naver_cafe_url(url)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO targets (name, target_url, cafe_id, menu_id, activity_type, daily_limit, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (
                body.get("name", "신규 타겟"),
                url,
                cafe_id,
                menu_id,
                body.get("activity_type", "COMMENT"),
                body.get("daily_limit", 3),
            ),
        )
        row = conn.execute(
            "SELECT * FROM targets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        conn.commit()
    return JSONResponse(_row_to_dict(row), status_code=201)


async def list_targets(request: Request) -> JSONResponse:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM targets ORDER BY id DESC").fetchall()
    return JSONResponse({"items": [_row_to_dict(r) for r in rows]})


async def delete_target(request: Request) -> JSONResponse:
    target_id = int(request.path_params["target_id"])
    with get_conn() as conn:
        conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
        conn.commit()
    return JSONResponse({"ok": True, "message": f"타겟 {target_id} 삭제됨"})


async def list_jobs(request: Request) -> JSONResponse:
    status = request.query_params.get("status", "PENDING")
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT j.*, t.name as target_name, p.name as preset_name
            FROM jobs j
            LEFT JOIN targets t ON j.target_id = t.id
            LEFT JOIN presets p ON j.preset_id = p.id
            WHERE j.status = ?
            ORDER BY j.created_at ASC
            """,
            (status,),
        ).fetchall()
    return JSONResponse({"items": [_row_to_dict(r) for r in rows]})


async def approve_job(request: Request) -> JSONResponse:
    job_id = int(request.path_params["job_id"])
    body = await _read_json(request)
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'APPROVED', content = ?, updated_at = datetime('now') WHERE id = ?",
            (body.get("content"), job_id),
        )
        conn.commit()
    return JSONResponse({"ok": True})


async def reject_job(request: Request) -> JSONResponse:
    job_id = int(request.path_params["job_id"])
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'REJECTED', updated_at = datetime('now') WHERE id = ?",
            (job_id,),
        )
        conn.commit()
    return JSONResponse({"ok": True})


async def process_approved_jobs(request: Request) -> JSONResponse:
    body = await _read_json(request)
    job_ids = body.get("job_ids", [])

    if job_ids and not isinstance(job_ids, list):
        raise HTTPException(status_code=400, detail="job_ids는 배열이어야 합니다.")

    with get_conn() as conn:
        if job_ids:
            placeholders = ",".join("?" * len(job_ids))
            rows = conn.execute(
                f"SELECT * FROM jobs WHERE id IN ({placeholders}) AND status = 'APPROVED'",
                job_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = 'APPROVED' ORDER BY created_at LIMIT 10"
            ).fetchall()

        results = []
        for row in rows:
            job_id = row["id"]
            try:
                conn.execute(
                    "UPDATE jobs SET status = 'COMPLETED', updated_at = datetime('now') WHERE id = ?",
                    (job_id,),
                )
                results.append({"job_id": job_id, "status": "processed"})
            except Exception as e:
                results.append({"job_id": job_id, "status": "failed", "error": str(e)})

        conn.commit()

    return JSONResponse({"processed": results})


async def list_logs(request: Request) -> JSONResponse:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, level, message, details, created_at
            FROM logs
            ORDER BY created_at DESC
            LIMIT 30
            """
        ).fetchall()
    # logs 테이블 구조에 맞게 변환
    items = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "level": row["level"],
                "message": row["message"],
                "details": row["details"] or "",
                "created_at": row["created_at"],
            }
        )
    return JSONResponse({"items": items})


async def delete_all_logs(_: Request) -> JSONResponse:
    with get_conn() as conn:
        conn.execute("DELETE FROM logs")
        conn.commit()
    return JSONResponse({"message": "전체 로그가 삭제되었습니다."})


async def list_deals(request: Request) -> JSONResponse:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM deals ORDER BY fetched_at DESC LIMIT 30"
        ).fetchall()
    return JSONResponse({"items": [_row_to_dict(r) for r in rows]})


async def get_stats(_: Request) -> JSONResponse:
    with get_conn() as conn:
        total_deals = _count_rows(conn, "SELECT count(*) FROM deals")
        active_presets = _count_rows(
            conn, "SELECT count(*) FROM presets WHERE is_active = 1"
        )
        active_targets = _count_rows(
            conn, "SELECT count(*) FROM targets WHERE is_active = 1"
        )
        pending_jobs = _count_rows(
            conn, "SELECT count(*) FROM jobs WHERE status = 'PENDING'"
        )
    return JSONResponse(
        {
            "active_presets": active_presets,
            "active_targets": active_targets,
            "pending_jobs": pending_jobs,
            "total_deals": total_deals,
            "scheduler_active": True,
        }
    )


async def run_pipelines_endpoint(_: Request) -> JSONResponse:
    try:
        from had_backend.actions.pipeline import run_all_pipelines

        run_all_pipelines()
        return JSONResponse({"ok": True, "message": "성공"})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


async def serve_index(_: Request) -> FileResponse:
    return _serve_static_page("index.html")


async def serve_brandconnect(_: Request) -> FileResponse:
    return _serve_static_page("brandconnect.html")


async def serve_naver(_: Request) -> FileResponse:
    return _serve_static_page("naver.html")


async def serve_approve(_: Request) -> FileResponse:
    return _serve_static_page("approve.html")


async def brandconnect_stats(_: Request) -> JSONResponse:
    with get_conn() as conn:
        # 비제휴 미처리 건 자동 failed 처리
        conn.execute(
            """
            UPDATE deals
            SET brand_connector_status = 'failed',
                brand_connector_error = '비제휴/미분류 URL (type=' || COALESCE(affiliate_url_type, 'unknown') || ')'
            WHERE site IN ('네이버', '네이버쇼핑')
              AND (brand_connector_status IS NULL OR brand_connector_status = '')
              AND is_affiliate_candidate = 0
              AND out_links_json IS NOT NULL
            """,
        )
        conn.commit()
        total = _count_rows(
            conn,
            """
            SELECT COUNT(*) FROM deals WHERE site IN ('네이버', '네이버쇼핑')
            """,
        )
        success = _count_rows(
            conn,
            """
            SELECT COUNT(*) FROM deals
            WHERE site IN ('네이버', '네이버쇼핑')
            AND brand_connector_status = 'success'
            """,
        )
        failed = _count_rows(
            conn,
            """
            SELECT COUNT(*) FROM deals
            WHERE site IN ('네이버', '네이버쇼핑')
            AND brand_connector_status = 'failed'
            """,
        )
        pending = _count_rows(
            conn,
            f"""
            SELECT COUNT(*) FROM deals
            WHERE site IN ('네이버', '네이버쇼핑')
            AND {BRANDCONNECT_PENDING_SQL}
            """,
        )

        success_rate = round((success / total * 100), 1) if total > 0 else 0

        return JSONResponse(
            {
                "total": total,
                "success": success,
                "failed": failed,
                "pending": pending,
                "success_rate": success_rate,
            }
        )


async def brandconnect_list(request: Request) -> JSONResponse:
    status_filter = request.query_params.get("status")
    limit = _parse_positive_int(request.query_params.get("limit"), 100, "limit")

    with get_conn() as conn:
        # 비제휴 미처리 건 자동 failed 처리
        conn.execute(
            """
            UPDATE deals
            SET brand_connector_status = 'failed',
                brand_connector_error = '비제휴/미분류 URL (type=' || COALESCE(affiliate_url_type, 'unknown') || ')'
            WHERE site IN ('네이버', '네이버쇼핑')
              AND (brand_connector_status IS NULL OR brand_connector_status = '')
              AND is_affiliate_candidate = 0
              AND out_links_json IS NOT NULL
            """,
        )
        conn.commit()
        sql = """
            SELECT id, title, site, brand_connector_link as link, 
                   brand_connector_status as status, 
                   brand_connector_error as error,
                   brand_connector_retry_count as retry_count,
                   brand_connector_last_attempt as last_attempt,
                   brand_connector_generated_at as generated_at,
                   is_affiliate_candidate,
                   affiliate_url_type,
                   canonical_product_name,
                   canonical_product_url
            FROM deals
            WHERE site IN ('네이버', '네이버쇼핑')
        """
        params = []

        if status_filter:
            if status_filter == "success":
                sql += " AND brand_connector_status = 'success'"
            elif status_filter == "failed":
                sql += " AND brand_connector_status = 'failed'"
            elif status_filter in ("pending", "processing"):
                sql += f" AND {BRANDCONNECT_PENDING_SQL}"

        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, tuple(params)).fetchall()

    items = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "title": row["title"],
                "site": row["site"],
                "link": row["link"],
                "status": row["status"] or "processing",
                "error": row["error"],
                "retry_count": row["retry_count"] or 0,
                "last_attempt": row["last_attempt"],
                "generated_at": row["generated_at"],
                "is_affiliate_candidate": row["is_affiliate_candidate"],
                "affiliate_url_type": row["affiliate_url_type"],
                "canonical_product_name": row["canonical_product_name"],
                "canonical_product_url": row["canonical_product_url"],
            }
        )

    return JSONResponse({"items": items})


async def brandconnect_retry(request: Request) -> JSONResponse:
    deal_id = int(request.path_params["deal_id"])
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE deals
            SET brand_connector_status = 'processing',
                brand_connector_link = NULL,
                brand_connector_error = NULL,
                brand_connector_generated_at = NULL,
                brand_connector_last_attempt = CAST(strftime('%s', 'now') AS INTEGER)
            WHERE id = ?
            """,
            (deal_id,),
        )
        conn.commit()

    return JSONResponse({"ok": True, "message": f"#{deal_id} 재시도가 예약되었습니다."})


# --- 네이버 스토어 딜 조회 (페이지네이션) ---
def _parse_price(price_str: str) -> int | None:
    if not price_str:
        return None
    numbers = re.findall(r"[\d,]+", price_str)
    if numbers:
        return int(numbers[0].replace(",", ""))
    return None


async def list_naver_deals(request: Request) -> JSONResponse:
    page = _parse_positive_int(request.query_params.get("page"), 1, "page")
    page_size = _parse_positive_int(
        request.query_params.get("page_size"), 10, "page_size"
    )
    offset = (page - 1) * page_size

    now_epoch = int(datetime.now().timestamp())
    stale_cutoff = now_epoch - BRANDCONNECT_PROCESSING_TIMEOUT_SEC

    with get_conn() as conn:
        # 오랫동안 processing에 머문 건을 자동으로 failed로 전환해 대시보드 정체를 줄임
        conn.execute(
            """
            UPDATE deals
            SET brand_connector_status = 'failed',
                brand_connector_error = '처리 타임아웃(자동 전환)',
                brand_connector_last_attempt = CAST(strftime('%s','now') AS INTEGER)
            WHERE site IN ('네이버', '네이버쇼핑')
              AND brand_connector_status = 'processing'
              AND brand_connector_last_attempt IS NOT NULL
              AND brand_connector_last_attempt < ?
            """,
            (stale_cutoff,),
        )
        # 비제휴인데 아직 미처리인 건 자동으로 failed 처리 (UI 정체 방지)
        conn.execute(
            """
            UPDATE deals
            SET brand_connector_status = 'failed',
                brand_connector_error = '비제휴/미분류 URL (type=' || COALESCE(affiliate_url_type, 'unknown') || ')'
            WHERE site IN ('네이버', '네이버쇼핑')
              AND (brand_connector_status IS NULL OR brand_connector_status = '')
              AND is_affiliate_candidate = 0
              AND out_links_json IS NOT NULL
            """,
        )
        conn.commit()

        total = conn.execute(
            "SELECT COUNT(*) FROM deals WHERE site IN ('네이버', '네이버쇼핑')"
        ).fetchone()[0]

        rows = conn.execute(
            """
            SELECT id, title, site, price, category, fetched_at,
                   brand_connector_link, brand_connector_status, brand_connector_error, 
                   brand_connector_retry_count, brand_connector_last_attempt,
                   price_table_json,
                   is_affiliate_candidate, affiliate_url_type,
                   canonical_product_name, canonical_product_url
            FROM deals
            WHERE site IN ('네이버', '네이버쇼핑')
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()

    items = []
    for r in rows:
        row_dict = {k: r[k] for k in r.keys()}
        bc_link = row_dict.get("brand_connector_link", "")
        bc_status = row_dict.get("brand_connector_status", "")
        affiliate_candidate = row_dict.get("is_affiliate_candidate")

        is_affiliate = None
        if affiliate_candidate in (0, 1):
            is_affiliate = affiliate_candidate
        elif bc_link and bc_link.startswith("https://naver.me/"):
            is_affiliate = 1
        elif bc_status == "failed" or (bc_link and "smartstore.naver.com" in bc_link):
            is_affiliate = 0
        elif bc_status == "success" and bc_link:
            is_affiliate = 0

        price_table = row_dict.get("price_table_json")
        naver_price = _parse_price(row_dict.get("price", ""))

        discount_rate = None
        commission = None

        if is_affiliate == 1 and price_table and naver_price:
            try:
                table = (
                    json.loads(price_table)
                    if isinstance(price_table, str)
                    else price_table
                )
                if table and isinstance(table, list):
                    other_prices = []
                    for item in table:
                        seller = item.get("seller", "")
                        if seller not in ("네이버", "네이버쇼핑", "핫딜모음"):
                            p = _parse_price(item.get("price", ""))
                            if p and p > 0:
                                other_prices.append(p)

                    if other_prices:
                        lowest_other = min(other_prices)
                        if lowest_other > naver_price:
                            discount_rate = round(
                                (lowest_other - naver_price) / lowest_other * 100, 1
                            )

                    if naver_price >= 50000:
                        commission = 2.0
                    elif naver_price >= 30000:
                        commission = 2.5
                    elif naver_price >= 10000:
                        commission = 3.0
                    else:
                        commission = 3.5
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        elif is_affiliate == 0:
            discount_rate = None
            commission = None

        row_dict["is_affiliate"] = is_affiliate
        row_dict["discount_rate"] = discount_rate
        row_dict["commission"] = commission
        items.append(row_dict)

    return JSONResponse(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    )


# --- 선택한 딜의 브랜드커넥터 링크 일괄 생성 ---
async def generate_links(request: Request) -> JSONResponse:
    body = await _read_json(request)
    deal_ids = body.get("deal_ids", [])

    if not isinstance(deal_ids, list):
        return _error_response("deal_ids는 배열이어야 합니다.")

    if not deal_ids:
        return _error_response("선택된 딜이 없습니다.")

    eligible_ids: list[int] = []
    skipped: list[dict[str, Any]] = []

    with get_conn() as conn:
        for deal_id in deal_ids:
            cls, typ = _classify_url_for_link_generation(conn, int(deal_id))

            # 분류값을 최신화해서 대시보드 표시에 즉시 반영
            conn.execute(
                """
                UPDATE deals
                SET is_affiliate_candidate = ?,
                    affiliate_url_type = COALESCE(?, affiliate_url_type)
                WHERE id = ?
                """,
                (cls, typ, int(deal_id)),
            )

            # 비제휴(0) 또는 unknown(None/unknown)은 링크 생성 대상에서 제외
            if cls != 1:
                reason = f"비제휴/미분류 URL (type={typ or 'unknown'})"
                conn.execute(
                    """
                    UPDATE deals
                    SET brand_connector_status = 'failed',
                        brand_connector_link = NULL,
                        brand_connector_error = ?,
                        brand_connector_last_attempt = CAST(strftime('%s', 'now') AS INTEGER)
                    WHERE id = ?
                    """,
                    (reason, int(deal_id)),
                )
                skipped.append({"deal_id": int(deal_id), "reason": reason})
                continue

            # 제휴 후보(1)만 실제 발급 큐에 넣음
            conn.execute(
                """
                UPDATE deals
                SET brand_connector_status = 'processing',
                    brand_connector_link = NULL,
                    brand_connector_error = NULL,
                    brand_connector_generated_at = NULL,
                    brand_connector_last_attempt = CAST(strftime('%s', 'now') AS INTEGER)
                WHERE id = ?
                """,
                (int(deal_id),),
            )
            eligible_ids.append(int(deal_id))

        conn.commit()

    if not eligible_ids:
        return JSONResponse(
            {
                "ok": True,
                "message": "링크 생성 대상이 없습니다. (모두 비제휴/미분류)",
                "deal_ids": [],
                "pid": None,
                "skipped": skipped,
            }
        )

    pid = None
    if AUTO_RUN_BRANDCONNECT:
        try:
            pid = _start_brandconnect_link_generation(eligible_ids)
        except Exception as e:
            with get_conn() as conn:
                for deal_id in eligible_ids:
                    conn.execute(
                        """
                        UPDATE deals
                        SET brand_connector_status = 'failed',
                            brand_connector_error = ?,
                            brand_connector_last_attempt = CAST(strftime('%s', 'now') AS INTEGER)
                        WHERE id = ?
                        """,
                        (f"실행 실패: {e}", deal_id),
                    )
                conn.commit()
            return _error_response(f"링크 생성 프로세스 시작 실패: {e}", 500)

    msg = f"{len(eligible_ids)}개 딜의 링크 생성이 시작되었습니다."
    if skipped:
        msg += f" ({len(skipped)}개 제외)"

    return JSONResponse(
        {
            "ok": True,
            "message": msg,
            "deal_ids": eligible_ids,
            "pid": pid,
            "skipped": skipped,
        }
    )


# --- Article Sources API (수집된 글 소스 관리) ---

async def list_article_sources(request: Request) -> JSONResponse:
    """수집된 글 소스 목록 조회"""
    category = request.query_params.get("category")  # product, tip, good, fun
    source_type = request.query_params.get("source_type")  # hotdeal, todayhumor_tip, etc.
    page = _parse_positive_int(request.query_params.get("page"), 1, "page")
    page_size = _parse_positive_int(request.query_params.get("page_size"), 20, "page_size")
    offset = (page - 1) * page_size

    with get_conn() as conn:
        where_clauses = ["is_archived = 0"]
        params = []

        if category:
            where_clauses.append("category = ?")
            params.append(category)
        if source_type:
            where_clauses.append("source_type = ?")
            params.append(source_type)

        where_sql = " AND ".join(where_clauses)

        total = conn.execute(
            f"SELECT COUNT(*) FROM article_sources WHERE {where_sql}", tuple(params)
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT * FROM article_sources WHERE {where_sql}
            ORDER BY collected_at DESC LIMIT ? OFFSET ?""",
            (*params, page_size, offset)
        ).fetchall()

    return JSONResponse({
        "items": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    })


async def create_article_source(request: Request) -> JSONResponse:
    """새 글 소스 추가"""
    body = await _read_json(request)
    _require_fields(body, "source_type", "title")

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO article_sources
            (source_type, title, content_text, content_html, source_url, thumbnail_url, category, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                body["source_type"],
                body["title"],
                body.get("content_text"),
                body.get("content_html"),
                body.get("source_url"),
                body.get("thumbnail_url"),
                body.get("category", "tip"),
                json.dumps(body.get("metadata", {}), ensure_ascii=False) if body.get("metadata") else None,
            ),
        )
        row = conn.execute(
            "SELECT * FROM article_sources WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        conn.commit()

    return JSONResponse(_row_to_dict(row), status_code=201)


async def delete_article_source(request: Request) -> JSONResponse:
    """글 소스 아카이브 (soft delete)"""
    source_id = int(request.path_params["source_id"])
    with get_conn() as conn:
        conn.execute(
            "UPDATE article_sources SET is_archived = 1 WHERE id = ?",
            (source_id,),
        )
        conn.commit()
    return JSONResponse({"ok": True, "message": f"소스 {source_id} 아카이브됨"})


# --- Article Queue API (자동글 작성 큐 관리) ---

async def list_article_queue(request: Request) -> JSONResponse:
    """자동글 작성 큐 조회"""
    status = request.query_params.get("status", "PENDING")
    category = request.query_params.get("category")

    with get_conn() as conn:
        where_clauses = ["aq.status = ?"]
        params = [status]

        if category:
            where_clauses.append("aq.category = ?")
            params.append(category)

        where_sql = " AND ".join(where_clauses)

        rows = conn.execute(
            f"""SELECT aq.*, t.name as target_name, p.name as preset_name
            FROM article_queue aq
            LEFT JOIN targets t ON aq.target_id = t.id
            LEFT JOIN presets p ON aq.preset_id = p.id
            WHERE {where_sql}
            ORDER BY aq.created_at ASC""",
            tuple(params)
        ).fetchall()

    return JSONResponse({"items": [_row_to_dict(r) for r in rows]})


async def approve_article(request: Request) -> JSONResponse:
    """자동글 승인"""
    article_id = int(request.path_params["article_id"])
    body = await _read_json(request)

    with get_conn() as conn:
        conn.execute(
            """UPDATE article_queue
            SET status = 'APPROVED', content = ?, updated_at = datetime('now'), approved_at = datetime('now')
            WHERE id = ?""",
            (body.get("content"), article_id),
        )
        conn.commit()

    return JSONResponse({"ok": True})


async def reject_article(request: Request) -> JSONResponse:
    """자동글 거부"""
    article_id = int(request.path_params["article_id"])
    with get_conn() as conn:
        conn.execute(
            """UPDATE article_queue
            SET status = 'REJECTED', updated_at = datetime('now')
            WHERE id = ?""",
            (article_id,),
        )
        conn.commit()
    return JSONResponse({"ok": True})


async def generate_article(request: Request) -> JSONResponse:
    """소스 기반 자동글 생성 요청"""
    body = await _read_json(request)
    _require_fields(body, "target_id", "category", "source_ids")

    target_id = body["target_id"]
    category = body["category"]
    source_ids = body["source_ids"]  # JSON 배열

    if not isinstance(source_ids, list) or not source_ids:
        return _error_response("source_ids는 비어있지 않은 배열이어야 합니다.")

    with get_conn() as conn:
        # 타겟 확인
        target = conn.execute(
            "SELECT * FROM targets WHERE id = ?", (target_id,)
        ).fetchone()
        if not target:
            return _error_response("존재하지 않는 타겟입니다.", 404)

        # 소스 조회
        placeholders = ",".join("?" * len(source_ids))
        sources = conn.execute(
            f"SELECT * FROM article_sources WHERE id IN ({placeholders})",
            tuple(source_ids)
        ).fetchall()

        if not sources:
            return _error_response("선택된 소스가 없습니다.")

        # 소스 내용 결합
        source_contents = []
        for s in sources:
            content = s["content_text"] or s["title"]
            source_contents.append(f"[{s['source_type']}] {content}")

        combined_content = "\n\n---\n\n".join(source_contents)

        # 큐에 추가 (LLM 생성은 별도 처리)
        cur = conn.execute(
            """INSERT INTO article_queue (target_id, category, title, content, source_ids, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')""",
            (
                target_id,
                category,
                f"{target['name']} - {category} 글",
                combined_content,
                json.dumps(source_ids),
            ),
        )

        # 소스 사용 횟수 증가
        for sid in source_ids:
            conn.execute(
                "UPDATE article_sources SET used_count = used_count + 1 WHERE id = ?",
                (sid,),
            )

        conn.commit()

    return JSONResponse({
        "ok": True,
        "message": f"{len(sources)}개 소스로 글 생성 큐에 추가됨",
        "queue_id": cur.lastrowid,
    }, status_code=201)


# --- 라우팅 ---
routes = [
    Route("/", serve_index),
    Route("/brandconnect", serve_brandconnect),
    Route("/naver", serve_naver),
    Route("/approve", serve_approve),
    Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
    Route("/api/v1/stats", get_stats),
    Route("/api/v1/presets", list_presets, methods=["GET"]),
    Route("/api/v1/presets", create_preset, methods=["POST"]),
    Route("/api/v1/presets/{preset_id:int}", delete_preset, methods=["DELETE"]),
    Route("/api/v1/presets/{preset_id:int}", update_preset, methods=["PATCH"]),
    Route("/api/v1/presets/{preset_id:int}/toggle", toggle_preset, methods=["PATCH"]),
    Route("/api/v1/targets", list_targets, methods=["GET"]),
    Route("/api/v1/targets", create_target, methods=["POST"]),
    Route("/api/v1/targets/{target_id:int}", delete_target, methods=["DELETE"]),
    Route("/api/v1/jobs", list_jobs, methods=["GET"]),
    Route("/api/v1/jobs/{job_id:int}/approve", approve_job, methods=["POST"]),
    Route("/api/v1/jobs/{job_id:int}/reject", reject_job, methods=["POST"]),
    Route("/api/v1/jobs/process-approved", process_approved_jobs, methods=["POST"]),
    Route("/api/v1/logs", list_logs, methods=["GET"]),
    Route("/api/v1/logs", delete_all_logs, methods=["DELETE"]),
    Route("/api/v1/deals", list_deals, methods=["GET"]),
    Route("/api/v1/pipelines/run", run_pipelines_endpoint, methods=["POST"]),
    Route("/api/v1/brandconnect/stats", brandconnect_stats, methods=["GET"]),
    Route("/api/v1/brandconnect/list", brandconnect_list, methods=["GET"]),
    Route(
        "/api/v1/brandconnect/retry/{deal_id:int}", brandconnect_retry, methods=["POST"]
    ),
    Route("/api/v1/naver/deals", list_naver_deals, methods=["GET"]),
    Route("/api/v1/naver/generate-links", generate_links, methods=["POST"]),
    # Article Sources API
    Route("/api/v1/sources", list_article_sources, methods=["GET"]),
    Route("/api/v1/sources", create_article_source, methods=["POST"]),
    Route("/api/v1/sources/{source_id:int}", delete_article_source, methods=["DELETE"]),
    # Article Queue API
    Route("/api/v1/article-queue", list_article_queue, methods=["GET"]),
    Route("/api/v1/article-queue/{article_id:int}/approve", approve_article, methods=["POST"]),
    Route("/api/v1/article-queue/{article_id:int}/reject", reject_article, methods=["POST"]),
    Route("/api/v1/article-queue/generate", generate_article, methods=["POST"]),
]

app = Starlette(
    debug=True, routes=routes, exception_handlers={HTTPException: handle_http_exception}
)
ensure_runtime_indexes()
ensure_runtime_columns()

if __name__ == "__main__":
    import uvicorn

    # 단순화된 실행 방식
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
