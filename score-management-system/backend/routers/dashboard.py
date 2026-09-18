"""Dashboard statistics APIs — Repository refactored."""
from datetime import datetime
from fastapi import APIRouter
from repositories.dashboard import DashboardRepository

router = APIRouter()
repo = DashboardRepository()


@router.get('/stats')
def dashboard_stats():
    counts = repo.overview_counts()
    grade_stats = repo.grade_stats()
    recent_exams = repo.recent_exams(5)
    recent_logs = repo.recent_logs(5)
    scores = counts['scores']
    pending_scores = counts['pending_scores']
    conversion_rate = round((scores - pending_scores) / scores * 100, 1) if scores else 0
    return {
        'counts': counts, 'conversion_rate': conversion_rate,
        'last_sync_time': datetime.now().isoformat(timespec='seconds'),
        'grade_stats': grade_stats, 'recent_exams': recent_exams, 'recent_logs': recent_logs,
    }


@router.get('/recent-ops')
def recent_operations(limit: int = 10):
    return {'items': repo.recent_operations(limit)}


@router.get('/tasks')
def dashboard_tasks():
    tasks = []
    d = repo.tasks_data()
    if d['pending_conversion']:
        tasks.append({'title': f'有 {d["pending_conversion"]} 条成绩未换算',
                      'link': '/pages/score-management.html',
                      'urgency': 'high' if d['pending_conversion'] > 100 else 'medium'})
    if d['pending_reviews']:
        tasks.append({'title': f'有 {d["pending_reviews"]} 条奖学金候选待复核',
                      'link': '/pages/scholarship.html',
                      'urgency': 'high' if d['pending_reviews'] > 20 else 'medium'})
    if d['pending_validation']:
        tasks.append({'title': f'有 {d["pending_validation"]} 个文件待校验',
                      'link': '/pages/data-import.html', 'urgency': 'medium'})
    if not d['latest_backup'] or (datetime.now() - datetime.fromisoformat(d['latest_backup'])).days > 7:
        tasks.append({'title': '已超过 7 天未备份, 建议立即备份',
                      'link': '/pages/backup-restore.html', 'urgency': 'low'})
    return {'items': tasks}
