"""Scholarship APIs — Repository refactored."""
import json
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_db
from repositories.scholarships import ScholarshipRuleRepository, ScholarshipCandidateRepository
from repositories.students import StudentRepository
from repositories.exams import ExamRepository
from repositories.classes import ClassRepository
from services.scholarship_engine import run_screen
from utils.common import now_str
from utils.logger import log_operation

router = APIRouter()
rule_repo = ScholarshipRuleRepository()
cand_repo = ScholarshipCandidateRepository()
student_repo = StudentRepository()
exam_repo = ExamRepository()
class_repo = ClassRepository()


class RuleIn(BaseModel):
    name: str
    conditions: dict
    grade_ids: List[int]
    class_type_ids: List[int]
    is_active: bool = True


@router.get('/rules')
def list_rules():
    return rule_repo.list_all()


@router.post('/rules')
def create_rule(item: RuleIn):
    new_id = rule_repo.create(item.name, item.conditions, item.grade_ids, item.class_type_ids, item.is_active)
    return {'id': new_id}


@router.put('/rules/{rule_id}')
def update_rule(rule_id: int, item: RuleIn):
    rule_repo.update(rule_id, item.name, item.conditions, item.grade_ids, item.class_type_ids, item.is_active)
    return {'id': rule_id}


@router.delete('/rules/{rule_id}')
def delete_rule(rule_id: int):
    rule_repo.delete(rule_id)
    return {'deleted': rule_id}


class ScreenPayload(BaseModel):
    grade_id: int
    class_type_ids: List[int]
    exam_ids: List[int]
    category: str
    name: Optional[str] = ''
    class_id: Optional[int] = None
    options: Optional[dict] = {}


@router.post('/run-screen')
def run_screen_endpoint(payload: ScreenPayload):
    try:
        count = run_screen(payload.grade_id, payload.class_type_ids, payload.exam_ids,
                           payload.category, payload.name, payload.class_id, payload.options)
        log_operation('奖学金筛选', f'年级 id={payload.grade_id} 类别 {payload.category} 候选 {count} 人')
        return {'candidates': count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/candidates')
def list_candidates(
    exam_id: Optional[int] = Query(None), class_id: Optional[int] = Query(None),
    review_status: Optional[str] = Query(None), award_level: Optional[str] = Query(None),
    grade_id: Optional[int] = Query(None), class_type_ids: Optional[str] = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
):
    return cand_repo.list_with_filters(exam_id, class_id, review_status, award_level,
                                         grade_id, class_type_ids, page, page_size)


class ReviewIn(BaseModel):
    review_status: str
    review_note: Optional[str] = ''
    reviewed_by: str = '管理员'


@router.put('/candidates/{candidate_id}/review')
def review_candidate(candidate_id: int, item: ReviewIn):
    cand_repo.review(candidate_id, item.review_status, item.review_note or '', item.reviewed_by)
    log_operation('奖学金复核', f'候选 id={candidate_id} 标记为 {item.review_status}')
    return {'id': candidate_id}


@router.post('/candidates/batch-confirm')
def batch_confirm(payload: dict):
    ids = payload.get('ids', [])
    updated = cand_repo.batch_confirm(ids)
    log_operation('奖学金复核', f'批量确认 {updated} 条候选')
    return {'updated': updated}


@router.put('/candidates/{candidate_id}/special-first-prize')
def special_first_prize(candidate_id: int):
    cand_repo.special_first_prize(candidate_id)
    log_operation('奖学金特评', f'候选 id={candidate_id} 手动特评一等奖')
    return {'id': candidate_id}


class ManualFirstPrizeIn(BaseModel):
    student_id: int
    exam_id: int
    class_id: int
    note: Optional[str] = '手动特评一等奖'


@router.post('/manual-first-prize')
def manual_first_prize(item: ManualFirstPrizeIn):
    if not student_repo.get_by_id(item.student_id):
        raise HTTPException(status_code=404, detail='学生不存在')
    if not exam_repo.get_by_id(item.exam_id):
        raise HTTPException(status_code=404, detail='考试不存在')
    if not class_repo.get_by_id(item.class_id):
        raise HTTPException(status_code=404, detail='班级不存在')
    lang_avg, prof_avg = cand_repo.get_averages(item.student_id, item.exam_id)
    new_id = cand_repo.manual_first_prize(item.student_id, item.exam_id, item.class_id,
                                           lang_avg + prof_avg, lang_avg, prof_avg, item.note)
    log_operation('奖学金特评', f'手动添加学生 id={item.student_id} 为特评一等奖')
    return {'id': new_id}


@router.get('/stats')
def scholarship_stats():
    return cand_repo.stats()
