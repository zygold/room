"""Dashboard statistics APIs."""
from datetime import datetime

from fastapi import APIRouter

from database import get_db

router = APIRouter()


@router.get("/stats")
def dashboard_stats():
    with get_db() as conn:
        students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        exams = conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0]
        scores = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        pending_scores = conn.execute(
            "SELECT COUNT(*) FROM scores WHERE is_converted=0"
        ).fetchone()[0]
        scholarships = conn.execute(
            "SELECT COUNT(*) FROM scholarships WHERE review_status='待复核'"
        ).fetchone()[0]
        backups = conn.execute("SELECT COUNT(*) FROM backups").fetchone()[0]
        imports = conn.execute("SELECT COUNT(*) FROM import_files").fetchone()[0]

        grade_stats = conn.execute(
            """
            SELECT g.name, COUNT(s.id) as student_count
            FROM grades g
            LEFT JOIN students s ON s.grade_id = g.id
            GROUP BY g.id
            ORDER BY g.id
            """
        ).fetchall()

        recent_exams = conn.execute(
            """
            SELECT id, name, exam_type, exam_date
            FROM exams
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()

        recent_logs = conn.execute(
            """
            SELECT operation_type, operation_detail, status, created_at
            FROM operation_logs
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()

    conversion_rate = round((scores - pending_scores) / scores * 100, 1) if scores else 0

    return {
        "counts": {
            "students": students,
            "exams": exams,
            "scores": scores,
            "pending_scores": pending_scores,
            "pending_scholarships": scholarships,
            "backups": backups,
            "imports": imports,
        },
        "conversion_rate": conversion_rate,
        "last_sync_time": datetime.now().isoformat(timespec='seconds'),
        "grade_stats": [dict(r) for r in grade_stats],
        "recent_exams": [dict(r) for r in recent_exams],
        "recent_logs": [dict(r) for r in recent_logs],
    }


@router.get("/recent-ops")
def recent_operations(limit: int = 10):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT operation_type, operation_detail, status, created_at
            FROM operation_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/tasks")
def dashboard_tasks():
    """Generate actionable to-do items with links to relevant pages."""
    tasks = []
    with get_db() as conn:
        pending_conversion = conn.execute(
            "SELECT COUNT(*) FROM scores WHERE is_converted=0"
        ).fetchone()[0]
        pending_reviews = conn.execute(
            "SELECT COUNT(*) FROM scholarships WHERE review_status='待复核'"
        ).fetchone()[0]
        pending_validation = conn.execute(
            "SELECT COUNT(*) FROM import_files WHERE validation_status='待校验'"
        ).fetchone()[0]
        latest_backup = conn.execute(
            "SELECT MAX(created_at) FROM backups"
        ).fetchone()[0]

    if pending_conversion:
        tasks.append({
            "title": f"有 {pending_conversion} 条成绩未换算",
            "link": "/pages/score-management.html",
            "urgency": "high" if pending_conversion > 100 else "medium",
        })
    if pending_reviews:
        tasks.append({
            "title": f"有 {pending_reviews} 条奖学金候选待复核",
            "link": "/pages/scholarship.html",
            "urgency": "high" if pending_reviews > 20 else "medium",
        })
    if pending_validation:
        tasks.append({
            "title": f"有 {pending_validation} 个文件待校验",
            "link": "/pages/data-import.html",
            "urgency": "medium",
        })
    if not latest_backup or (datetime.now() - datetime.fromisoformat(latest_backup)).days > 7:
        tasks.append({
            "title": "已超过 7 天未备份，建议立即备份",
            "link": "/pages/backup-restore.html",
            "urgency": "low",
        })

    return {"items": tasks}
