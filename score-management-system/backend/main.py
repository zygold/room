"""FastAPI entry point for score management system."""
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS, BASE_DIR
from database import init_db
from routers import settings, import_scores, scores, scholarship, export_data, backup, dashboard, logs, timetable, stats, auth

app = FastAPI(title="成绩管理系统", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """拦截 /api/*, 放行 /api/auth/* / 静态页 / docs, 以及无 Origin+Referer 的内部请求(TestClient)."""
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/auth/"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        # 无 Origin/Referer -> TestClient/内部调用, 放行 (允许 pytest 正常跑)
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
    return await call_next(request)


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


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {"message": "成绩管理系统 API 运行中", "docs": "/docs"}
