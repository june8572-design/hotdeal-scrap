import json
import logging
import sqlite3
import random
import traceback
from datetime import datetime
from pathlib import Path
from .hotdeal_actions import (
    fetch_latest_deals,
    save_deals_to_db,
    enrich_deal,
    generate_promo_text,
    get_conn,
)

logger = logging.getLogger(__name__)

# todayhumor 모듈 import (프로젝트 루트 기준)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from todayhumor_tip_scraper import search_tips, enrich_with_details, save_posts
    TODAYHUMOR_AVAILABLE = True
except ImportError:
    TODAYHUMOR_AVAILABLE = False
    logger.warning("todayhumor_tip_scraper 모듈을 불러올 수 없습니다.")

try:
    from had_backend.actions.article_generator import process_pending_articles
    ARTICLE_GEN_AVAILABLE = True
except ImportError:
    ARTICLE_GEN_AVAILABLE = False
    logger.warning("article_generator 모듈을 불러올 수 없습니다.")


def log_message(conn: sqlite3.Connection, level: str, message: str, details: str = ""):
    """로그 테이블에 메시지 기록 + Python logging 연동"""
    try:
        conn.execute(
            "INSERT INTO logs (level, message, details, created_at) VALUES (?, ?, ?, datetime('now'))",
            (level, message[:500], details[:2000]),
        )
        conn.commit()
    except Exception as e:
        # 로그 기록 실패 시 Python logging으로 fallback
        logger.error("DB 로그 기록 실패: %s - %s", message, e)

    # Python logging에도 동시 기록
    log_func = getattr(logger, level.lower(), logger.info)
    log_func("%s%s", message, f" | {details}" if details else "")


class PipelineRunner:
    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn

    def process_hotdeal_presets(self):
        presets = self.conn.execute(
            "SELECT * FROM presets WHERE is_active = 1"
        ).fetchall()
        if not presets:
            log_message(self.conn, "INFO", "활성화된 hotdeal 프리셋 없음", "")
            return

        log_message(
            self.conn, "INFO", f"Hotdeal 프리셋 처리 시작 ({len(presets)}개)", ""
        )

        for p in presets:
            preset_name = p["name"]
            try:
                log_message(
                    self.conn,
                    "INFO",
                    f"프리셋 '{preset_name}' 처리 시작",
                    f"preset_id={p['id']}",
                )
                # 1. Fetch latest deals
                deals = fetch_latest_deals()
                save_deals_to_db(deals)

                if not deals:
                    continue

                # For MVP, process the most recent deal
                target_deal = deals[0]
                deal_id = target_deal["id"]

                # 중복 체크: 이미 해당 deal_id로 생성된 대기열이 있는지 확인
                exists = self.conn.execute(
                    "SELECT id FROM jobs WHERE job_type = 'HOTDEAL' AND post_url LIKE ?",
                    (f"%{deal_id}%",),
                ).fetchone()
                if exists:
                    continue

                # 2. Enrich & LLM (Always needed for promo)
                enrich_deal(deal_id)
                promo = generate_promo_text(deal_id)

                # 3. Create Job (PENDING status for user confirmation)
                self.conn.execute(
                    """
                    INSERT INTO jobs (preset_id, job_type, status, post_title, post_url, content)
                    VALUES (?, 'HOTDEAL', 'PENDING', ?, ?, ?)
                    """,
                    (p["id"], target_deal["title"], target_deal["post_url"], promo),
                )
                self.conn.commit()
                log_message(
                    self.conn,
                    "INFO",
                    f"프리셋 '{preset_name}' 처리 완료",
                    f"deal_id={deal_id}, job 생성됨",
                )
            except Exception as e:
                error_msg = f"프리셋 '{preset_name}' 처리 실패: {str(e)}"
                error_details = traceback.format_exc()[:1500]
                log_message(self.conn, "ERROR", error_msg, error_details)
                print(f"Error processing hotdeal preset {p['id']}: {e}")

    def process_cafe_targets(self):
        targets = self.conn.execute(
            "SELECT * FROM targets WHERE is_active = 1"
        ).fetchall()
        if not targets:
            log_message(self.conn, "INFO", "활성화된 카페 타겟 없음", "")
            return

        log_message(self.conn, "INFO", f"카페 타겟 처리 시작 ({len(targets)}개)", "")

        for t in targets:
            target_name = t["name"]
            try:
                log_message(
                    self.conn,
                    "INFO",
                    f"타겟 '{target_name}' 처리 시작",
                    f"target_id={t['id']}",
                )
                # [TODO] 실제 네이버 카페 최신글 스캔 로직 (adapter.discover_join_posts 등) 연결 필요
                # 현재는 구조적 구현만 진행

                # 일일 제한 체크
                today = datetime.now().strftime("%Y-%m-%d")
                done_today = self.conn.execute(
                    "SELECT count(*) as count FROM jobs WHERE target_id = ? AND date(created_at) = ?",
                    (t["id"], today),
                ).fetchone()["count"]

                if done_today >= t["daily_limit"]:
                    continue

                # 샘플 문구 하나 선택
                comment = self._get_random_comment()

                # 임시: 스캔된 글이 있다고 가정하고 대기열 생성 (실제 구현 시 스캔 결과 루프)
                # self.conn.execute(...)

                self.conn.commit()
                log_message(
                    self.conn,
                    "INFO",
                    f"타겟 '{target_name}' 처리 완료",
                    f"일일 제한 {done_today}/{t['daily_limit']}",
                )
            except Exception as e:
                error_msg = f"타겟 '{target_name}' 처리 실패: {str(e)}"
                error_details = traceback.format_exc()[:1500]
                log_message(self.conn, "ERROR", error_msg, error_details)
                print(f"Error processing cafe target {t['id']}: {e}")

    def _get_random_comment(self) -> str:
        try:
            row = self.conn.execute(
                "SELECT content FROM comment_pool ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
            return row["content"] if row else "안녕하세요! 반가워요."
        except Exception as e:
            # 댓글 풀에서 무작위 댓글 가져오기 실패 시 기본 반환
            log_message(
                self.conn,
                "WARNING",
                f"댓글 풀에서 무작위 댓글 가져오기 실패: {str(e)}",
                "",
            )
            return "안녕하세요! 반가워요."

    def process_todayhumor_presets(self):
        """오늘의유머 프리셋 처리 - 수집 → todayhumor_tips 저장 → article_sources 저장"""
        if not TODAYHUMOR_AVAILABLE:
            log_message(self.conn, "WARNING", "todayhumor_tip_scraper 모듈 없음", "")
            return

        presets = self.conn.execute(
            "SELECT * FROM presets WHERE is_active = 1 AND source_type LIKE 'todayhumor_%'"
        ).fetchall()
        if not presets:
            log_message(self.conn, "INFO", "활성화된 오늘의유머 프리셋 없음", "")
            return

        log_message(self.conn, "INFO", f"오늘의유머 프리셋 처리 시작 ({len(presets)}개)", "")

        # source_type → 검색 키워드 매핑
        keyword_map = {
            "todayhumor_tip": "꿀팁",
            "todayhumor_good": "좋은글",
            "todayhumor_fun": "유머",
        }

        for p in presets:
            preset_name = p["name"]
            source_type = p["source_type"]
            keyword = keyword_map.get(source_type, "꿀팁")
            category = source_type.replace("todayhumor_", "")  # tip, good, fun

            try:
                log_message(
                    self.conn, "INFO",
                    f"프리셋 '{preset_name}' 처리 시작",
                    f"keyword={keyword}, category={category}"
                )

                # 1. 검색 수집
                items = search_tips(keyword, pages=2)
                if not items:
                    continue

                # 2. 상세 본문 수집 (최대 5건)
                enrich_with_details(items[:5])

                # 3. todayhumor_tips 테이블에 저장
                saved = save_posts(self.conn.cursor(), items, keyword)

                # 4. article_sources 테이블에도 저장 (신규만)
                source_saved = 0
                for item in items:
                    if not item.get("content_text"):
                        continue

                    # 중복 체크 (source_url 기준)
                    exists = self.conn.execute(
                        "SELECT id FROM article_sources WHERE source_url = ?",
                        (item["url"],)
                    ).fetchone()
                    if exists:
                        continue

                    self.conn.execute(
                        """INSERT INTO article_sources
                        (source_type, title, content_text, source_url, category, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            source_type,
                            item["title"],
                            item["content_text"][:2000],  # 너무 긴 본문 절단
                            item["url"],
                            category,
                            json.dumps({
                                "writer": item.get("writer", ""),
                                "views": item.get("views", 0),
                                "reco": item.get("reco", 0),
                                "comments": item.get("comments", 0),
                            }, ensure_ascii=False),
                        ),
                    )
                    source_saved += 1

                self.conn.commit()
                log_message(
                    self.conn, "INFO",
                    f"프리셋 '{preset_name}' 처리 완료",
                    f"수집 {len(items)}건, tips 저장 {saved}건, sources 저장 {source_saved}건"
                )

            except Exception as e:
                error_msg = f"프리셋 '{preset_name}' 처리 실패: {str(e)}"
                error_details = traceback.format_exc()[:1500]
                log_message(self.conn, "ERROR", error_msg, error_details)
                print(f"Error processing todayhumor preset {p['id']}: {e}")

    def process_article_generation(self):
        """PENDING 상태의 article_queue 항목을 LLM으로 글 생성"""
        if not ARTICLE_GEN_AVAILABLE:
            log_message(self.conn, "WARNING", "article_generator 모듈 없음", "")
            return

        try:
            results = process_pending_articles(self.conn)
            if results:
                generated = sum(1 for r in results if r["status"] == "generated")
                errors = sum(1 for r in results if r["status"] == "error")
                log_message(
                    self.conn, "INFO",
                    f"자동글 생성 완료: {generated}건 성공, {errors}건 실패",
                    ""
                )
        except Exception as e:
            log_message(
                self.conn, "ERROR",
                f"자동글 생성 중 오류: {str(e)}",
                traceback.format_exc()[:1500]
            )


def run_all_pipelines():
    from datetime import datetime

    with get_conn() as conn:
        log_message(conn, "INFO", "파이프라인 전체 실행 시작", "")
        runner = PipelineRunner(conn)

        try:
            runner.process_hotdeal_presets()
        except Exception as e:
            log_message(
                conn,
                "ERROR",
                f"Hotdeal 파이프라인 실행 중 오류: {str(e)}",
                traceback.format_exc()[:1500],
            )

        try:
            runner.process_todayhumor_presets()
        except Exception as e:
            log_message(
                conn,
                "ERROR",
                f"오늘의유머 파이프라인 실행 중 오류: {str(e)}",
                traceback.format_exc()[:1500],
            )

        try:
            runner.process_article_generation()
        except Exception as e:
            log_message(
                conn,
                "ERROR",
                f"자동글 생성 파이프라인 실행 중 오류: {str(e)}",
                traceback.format_exc()[:1500],
            )

        try:
            runner.process_cafe_targets()
        except Exception as e:
            log_message(
                conn,
                "ERROR",
                f"카페 파이프라인 실행 중 오류: {str(e)}",
                traceback.format_exc()[:1500],
            )

        log_message(conn, "INFO", "파이프라인 전체 실행 완료", "")
