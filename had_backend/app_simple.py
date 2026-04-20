import sqlite3
import json
import re
from pathlib import Path
from typing import Any
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse
from starlette.routing import Route

# DB 경로: 환경변수 우선, 없으면 프로젝트 루트 기준
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = Path(os.getenv("HOTDEAL_DB_PATH", str(PROJECT_ROOT / "hotdeal.db")))

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

async def get_stats(_):
    with get_conn() as conn:
        res = conn.execute("SELECT count(*) FROM deals").fetchone()
        count = res[0] if res else 0
    return JSONResponse({"active_presets": 1, "active_targets": 0, "pending_jobs": 0, "total_deals": count, "scheduler_active": False})

async def list_deals(_):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM deals ORDER BY fetched_at DESC LIMIT 30").fetchall()
    return JSONResponse({"items": [{k: r[k] for k in r.keys()} for r in rows]})

async def serve_index(_):
    return FileResponse("/home/luisuh/hotdeal-scrap/had_backend/static/index.html")

routes = [
    Route("/", serve_index),
    Route("/api/v1/stats", get_stats),
    Route("/api/v1/deals", list_deals),
]

app = Starlette(routes=routes)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
