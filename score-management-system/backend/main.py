"""FastAPI entry point for score management system."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS, BASE_DIR
from database import init_db
from routers import settings, import_scores, scores, scholarship, export_data, backup, dashboard, logs

app = FastAPI(title="成绩管理系统", version="1.0.0")

# CORS: 仅允许本地开发前端访问；生产环境应收紧为实际域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)

# Static frontend pages
app.mount("/pages", StaticFiles(directory=BASE_DIR / "pages"), name="pages")
# 安全静态目录：仅挂载显式创建的 public 目录，避免暴露数据库/源码/上传文件
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# API routers
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["仪表盘"])
app.include_router(settings.router, prefix="/api", tags=["系统设置"])
app.include_router(import_scores.router, prefix="/api/import", tags=["数据导入"])
app.include_router(scores.router, prefix="/api/scores", tags=["成绩管理"])
app.include_router(scholarship.router, prefix="/api/scholarship", tags=["奖学金评定"])
app.include_router(export_data.router, prefix="/api/export", tags=["数据导出"])
app.include_router(backup.router, prefix="/api/backup", tags=["备份还原"])
app.include_router(logs.router, prefix="/api/logs", tags=["操作日志"])


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {"message": "成绩管理系统 API 运行中", "docs": "/docs"}
