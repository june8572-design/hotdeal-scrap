import json
import logging
import sqlite3
import random
import traceback
from datetime import datetime
from .hotdeal_actions import (
    fetch_latest_deals,
    save_deals_to_db,
    enrich_deal,
    generate_promo_text,
    get_conn,
)

logger = logging.getLogger(__name__)


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
            runner.process_cafe_targets()
        except Exception as e:
            log_message(
                conn,
                "ERROR",
                f"카페 파이프라인 실행 중 오류: {str(e)}",
                traceback.format_exc()[:1500],
            )

        log_message(conn, "INFO", "파이프라인 전체 실행 완료", "")
