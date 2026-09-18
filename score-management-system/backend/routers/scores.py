"""Score management APIs — Repository 重构版."""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from repositories.scores import ScoreRepository
from repositories.exams import ExamRepository, ExamSubjectConfigRepository
from repositories.operation_logs import OperationLogRepository
from services.score_converter import convert_scores
from utils.logger import log_operation

router = APIRouter()

score_repo = ScoreRepository()
exam_repo = ExamRepository()
exam_config_repo = ExamSubjectConfigRepository()
log_repo = OperationLogRepository()


@router.get('/')
def list_scores(
    grade_id: Optional[int] = Query(None),
    major_id: Optional[int] = Query(None),
    class_type_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    exam_id: Optional[int] = Query(None),
    exam_type: Optional[str] = Query(None),
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    month: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    is_converted: Optional[int] = Query(None),
    sort_field: Optional[str] = Query(None),
    sort_order: Optional[str] = Query('desc'),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=10000),
):
    return score_repo.list_with_filters(
        grade_id=grade_id, major_id=major_id, class_type_id=class_type_id,
        class_id=class_id, exam_id=exam_id, exam_type=exam_type,
        school_year=school_year, semester=semester, month=month,
        keyword=keyword, is_converted=is_converted, sort_field=sort_field,
        sort_order=sort_order, page=page, page_size=page_size,
    )


class ScoreUpdate(BaseModel):
    chinese_score: Optional[float] = None
    math_score: Optional[float] = None
    english_score: Optional[float] = None
    professional_score: Optional[float] = None


@router.put('/{score_id}')
def update_score(score_id: int, item: ScoreUpdate):
    score = score_repo.get_by_id(score_id)
    if not score:
        raise HTTPException(status_code=404, detail='成绩不存在')

    updates = []
    values = []
    for field in ['chinese_score', 'math_score', 'english_score', 'professional_score']:
        val = getattr(item, field)
        if val is not None:
            updates.append(f'{field}=?')
            values.append(val)
    if not updates:
        return {'id': score_id}

    total_fields = ['chinese_score', 'math_score', 'english_score', 'professional_score']
    new_total = 0.0
    for field in total_fields:
        val = getattr(item, field)
        if val is None:
            val = score[field]
        try:
            new_total += float(val or 0)
        except (TypeError, ValueError):
            pass
    updates.append('total_score=?')
    values.append(round(new_total, 2))

    if score['is_converted']:
        updates.extend([
            'is_converted=0',
            'chinese_converted=NULL',
            'math_converted=NULL',
            'english_converted=NULL',
            'professional_converted=NULL',
            'total_converted=NULL',
        ])

    score_repo.update(score_id, updates, values)
    log_operation('成绩修改', f'修改成绩 id={score_id}')
    return {'id': score_id}


class ConvertPayload(BaseModel):
    exam_id: int
    score_ids: Optional[List[int]] = None
    original_max: dict = {}


@router.post('/convert')
def convert_score_endpoint(payload: ConvertPayload):
    updated = convert_scores(payload.exam_id, payload.score_ids, payload.original_max)
    log_operation('分值换算', f'考试 id={payload.exam_id} 换算 {updated} 条成绩')
    return {'updated': updated}


@router.get('/exam-subject-configs/{exam_id}')
def get_exam_subject_configs_endpoint(exam_id: int):
    return exam_config_repo.get_for_exam(exam_id)


class ExamSubjectConfigPayload(BaseModel):
    configs: dict


@router.post('/exam-subject-configs/{exam_id}')
def set_exam_subject_configs_endpoint(exam_id: int, payload: ExamSubjectConfigPayload):
    if not exam_repo.get_by_id(exam_id):
        raise HTTPException(status_code=404, detail='考试不存在')
    exam_config_repo.set_for_exam(exam_id, payload.configs)
    log_operation('考试科目满分配置', f'考试 id={exam_id} 配置 {len(payload.configs)} 门科目')
    return {'exam_id': exam_id, 'configs': payload.configs}


@router.get('/conversion-log')
def conversion_log(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1)):
    rows = log_repo.list(operation_type='分值换算', page=page, page_size=page_size)['items']
    return {'items': rows}


@router.get('/exams')
def list_exams(
    school_year: str = None,
    semester: str = None,
    exam_type: str = None,
):
    return exam_repo.list_with_filters(school_year, semester, exam_type)


@router.delete('/exams/{exam_id}')
def delete_exam(exam_id: int):
    exam, score_count = exam_repo.delete_cascade(exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail='考试不存在')
    log_operation('考试删除', f'删除考试 id={exam_id} {exam["name"]} 及 {score_count} 条成绩')
    return {'deleted': exam_id, 'score_count': score_count}


class BatchDeletePayload(BaseModel):
    ids: List[int]


@router.delete('/batch')
def batch_delete_scores(payload: BatchDeletePayload):
    if not payload.ids:
        raise HTTPException(status_code=400, detail='未选择要删除的成绩')
    deleted = score_repo.delete_by_ids(payload.ids)
    log_operation('成绩删除', f'批量删除 {deleted} 条成绩')
    return {'deleted': deleted}


@router.delete('/batch-by-filter')
def batch_delete_scores_by_filter(
    grade_id: Optional[int] = Query(None),
    major_id: Optional[int] = Query(None),
    class_type_id: Optional[int] = Query(None),
    class_id: Optional[int] = Query(None),
    exam_id: Optional[int] = Query(None),
    exam_type: Optional[str] = Query(None),
    school_year: Optional[str] = Query(None),
    semester: Optional[str] = Query(None),
    month: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    is_converted: Optional[int] = Query(None),
):
    deleted = score_repo.delete_by_filter_ids(
        grade_id=grade_id, major_id=major_id, class_type_id=class_type_id,
        class_id=class_id, exam_id=exam_id, exam_type=exam_type,
        school_year=school_year, semester=semester, month=month,
        keyword=keyword, is_converted=is_converted,
    )
    if deleted == 0:
        return {'deleted': 0}
    log_operation('成绩删除', f'按筛选条件批量删除 {deleted} 条成绩')
    return {'deleted': deleted}


class SubjectDetailsQuery(BaseModel):
    score_ids: List[int]


@router.post('/subject-details')
def get_subject_details(payload: SubjectDetailsQuery):
    return score_repo.get_subject_details(payload.score_ids)
