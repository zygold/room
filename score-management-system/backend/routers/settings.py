"""System settings APIs — grades, majors, class types, classes, subject standards."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from repositories.grades import GradeRepository
from repositories.majors import MajorRepository
from repositories.class_types import ClassTypeRepository
from repositories.classes import ClassRepository
from repositories.students import StudentRepository
from repositories.subject_standards import SubjectStandardRepository
from repositories.settings_table import SettingsTableRepository
from config import DB_PATH

router = APIRouter()

grade_repo = GradeRepository()
major_repo = MajorRepository()
ct_repo = ClassTypeRepository()
class_repo = ClassRepository()
student_repo = StudentRepository()
std_repo = SubjectStandardRepository()
settings_repo = SettingsTableRepository()


# ========== Grades ==========
class GradeIn(BaseModel):
    name: str
    status: str = '在读'


@router.get('/grades')
def list_grades():
    return grade_repo.get_all()


@router.post('/grades')
def create_grade(item: GradeIn):
    try:
        new_id = grade_repo.create(item.name, item.status)
        return {'id': new_id, 'name': item.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'年级已存在或数据错误: {e}')


@router.put('/grades/{grade_id}')
def update_grade(grade_id: int, item: GradeIn):
    grade_repo.update(grade_id, item.name, item.status)
    return {'id': grade_id}


@router.delete('/grades/{grade_id}')
def delete_grade(grade_id: int):
    grade_repo.delete_cascade(grade_id)
    return {'deleted': grade_id}


# ========== Majors ==========
class MajorIn(BaseModel):
    name: str


@router.get('/majors')
def list_majors(grade_id: Optional[int] = None):
    return major_repo.list_with_optional_grade(grade_id)


@router.post('/majors')
def create_major(item: MajorIn):
    try:
        new_id = major_repo.create(item.name)
        return {'id': new_id, 'name': item.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'专业已存在或数据错误: {e}')


@router.put('/majors/{major_id}')
def update_major(major_id: int, item: MajorIn):
    major_repo.update(major_id, item.name)
    return {'id': major_id}


@router.delete('/majors/{major_id}')
def delete_major(major_id: int):
    major_repo.delete_cascade(major_id)
    return {'deleted': major_id}


# ========== Class Types ==========
@router.get('/class-types')
def list_class_types(grade_id: Optional[int] = None, major_id: Optional[int] = None):
    return ct_repo.list_with_filters(grade_id, major_id)


@router.put('/class-types/{ct_id}')
def update_class_type(ct_id: int, is_active: int):
    ct_repo.update_active(ct_id, is_active)
    return {'id': ct_id, 'is_active': is_active}


# ========== Students ==========
@router.get('/students')
def list_students(
    class_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    keyword: Optional[str] = None,
):
    return student_repo.list_with_filters(class_id, grade_id, keyword)


# ========== Classes ==========
class ClassIn(BaseModel):
    name: str
    grade_id: int
    major_id: int
    class_type_id: int


@router.get('/classes')
def list_classes(
    grade_id: Optional[int] = None,
    major_id: Optional[int] = None,
    class_type_id: Optional[int] = None,
):
    return class_repo.list_with_filters_joined(grade_id, major_id, class_type_id)


@router.post('/classes')
def create_class(item: ClassIn):
    try:
        new_id = class_repo.create(item.name, item.grade_id, item.major_id, item.class_type_id)
        return {'id': new_id, 'name': item.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'班级已存在或数据错误: {e}')


@router.put('/classes/{class_id}')
def update_class(class_id: int, item: ClassIn):
    class_repo.update_basic(class_id, item.name, item.grade_id, item.major_id, item.class_type_id)
    return {'id': class_id}


@router.delete('/classes/{class_id}')
def delete_class(class_id: int):
    class_repo.delete_cascade(class_id)
    return {'deleted': class_id}


# ========== Subject Standards ==========
class StandardIn(BaseModel):
    max_score: float
    pass_score: float
    is_fixed: Optional[int] = None


@router.get('/subject-standards')
def list_subject_standards(major_id: Optional[int] = None):
    return std_repo.list_with_major(major_id)


@router.put('/subject-standards/{std_id}')
def update_subject_standard(std_id: int, item: StandardIn):
    ok = std_repo.update(std_id, item.max_score, item.pass_score, item.is_fixed)
    if not ok:
        raise HTTPException(status_code=404, detail='分值标准不存在')
    return {'id': std_id}


# ========== Settings ==========
@router.get('/settings/security')
def get_security_settings():
    return settings_repo.get_security_settings()


@router.put('/settings/security')
def update_security_settings(payload: dict):
    updated_keys = settings_repo.upsert_many(payload)
    return {'updated': updated_keys}


@router.get('/settings/info')
def get_system_info():
    import os
    size = os.path.getsize(DB_PATH) if DB_PATH.exists() else 0
    return {
        'version': '1.0.0',
        'db_path': str(DB_PATH),
        'db_size': f'{size / 1024 / 1024:.2f}MB',
    }


@router.get('/settings/school-years')
def list_school_years():
    return ['2024-2025', '2025-2026', '2026-2027', '2027-2028']


@router.get('/settings/semesters')
def list_semesters():
    return ['第一学期', '第二学期']
