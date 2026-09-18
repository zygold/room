"""FastAPI entry point for score management system."""
import time

import urllib.parse
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from config import ALLOWED_ORIGINS, BASE_DIR
from database import init_db
from routers import settings, import_scores, scores, scholarship, export_data, backup, dashboard, logs, timetable, stats, auth, headteacher

app = FastAPI(title="成绩管理系统", version="1.0.0")

# CORS
app.add_middleware(GZipMiddleware, minimum_size=1024)  # >=1KB 自动 gzip
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """拦截 /api/* (放行 /api/auth/*) 和 /pages/* (放行 login.html)."""
    from fastapi.responses import RedirectResponse as _RedirectResponse
    path = request.url.path

    # --- /pages/* protection (always enforce) ---
    if path.startswith("/pages/") and not path.endswith("/login.html"):
        token = request.cookies.get("token")
        from routers.auth import SESSIONS, _gc_sessions, SESSION_TTL
        _gc_sessions()
        valid = token and token in SESSIONS and time.time() - SESSIONS[token]["created_at"] <= SESSION_TTL
        if not valid:
            if token and token in SESSIONS:
                SESSIONS.pop(token, None)
            target = f"/pages/login.html?redirect={urllib.parse.quote(path)}"
            return _RedirectResponse(url=target, status_code=302)

    # --- /api/* protection ---
    if path.startswith("/api/") and not path.startswith("/api/auth/"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        # 无 Origin/Referer -> TestClient/内部调用, 放行
        if not origin:
            return await call_next(request)
        token = request.cookies.get("token")
        from routers.auth import SESSIONS, _gc_sessions, SESSION_TTL
        _gc_sessions()
        if not token or token not in SESSIONS:
            return JSONResponse(status_code=401, content={"detail": "未登录"})
        if time.time() - SESSIONS[token]["created_at"] > SESSION_TTL:
            SESSIONS.pop(token, None)
            return JSONResponse(status_code=401, content={"detail": "会话已过期"})
    response = await call_next(request)
    # 给静态资源加合理缓存头 (不影响上面的鉴权 401/302)
    if path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache"  # 协商缓存
    elif path.startswith("/static/") or path.endswith((".js", ".css", ".png", ".jpg", ".svg", ".woff2", ".ico")):
        response.headers["Cache-Control"] = "public, max-age=3600"  # 1h 强缓存
    return response


app.mount("/pages", StaticFiles(directory=BASE_DIR / "pages"), name="pages")
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(auth.router, prefix="/api/auth", tags=["鉴权"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["仪表盘"])
app.include_router(settings.router, prefix="/api", tags=["系统设置"])
app.include_router(import_scores.router, prefix="/api/import", tags=["数据导入"])
app.include_router(scores.router, prefix="/api/scores", tags=["成绩管理"])
app.include_router(scholarship.router, prefix="/api/scholarship", tags=["奖学金评定"])
app.include_router(export_data.router, prefix="/api/export", tags=["数据导出"])
app.include_router(backup.router, prefix="/api/backup", tags=["备份还原"])
app.include_router(timetable.router, prefix="/api/timetable", tags=["课表管理"])
app.include_router(logs.router, prefix="/api/logs", tags=["操作日志"])
app.include_router(stats.router, prefix="/api/stats", tags=["统计分析"])
app.include_router(headteacher.router, prefix="/api", tags=["班主任管理"])


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {"message": "成绩管理系统 API 运行中", "docs": "/docs"}
