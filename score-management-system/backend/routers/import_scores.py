"""Score data import APIs — thin Router (delegates to services/import_service.py)."""
import os, re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import pandas as pd

from database import get_db
from services.excel_parser import _read_with_engines, _clean_value
from services.import_service import (
    import_file_repo, exam_repo, exam_cfg_repo, student_repo, class_repo,
    score_repo,
    load_records, load_records_with_meta,
    validate_import_file, confirm_import_file, confirm_batch_import_files,
)
from utils.logger import log_operation
from config import UPLOAD_DIR
from utils.common import now_str

# 兼容旧引用 (upload_teachers 用 student_repo.update_homeroom_by_class_name)
from repositories.students import StudentRepository
_homeroom_helper = StudentRepository()

router = APIRouter()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(filename: str) -> str:
    name = os.path.basename(filename.replace("\\", "/"))
    name = re.sub(r"[^\w\.\-\u4e00-\u9fa5]", "_", name)
    return name


def _parse_teacher_file(content: bytes, filename: str) -> List[Dict[str, str]]:
    import io
    try:
        df = _read_with_engines(io.BytesIO(content), sheet_name=0, header=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法读取文件：{e}")
    header_row = None
    for idx, row in df.iterrows():
        row_text = " ".join(str(x) for x in row if pd.notna(x))
        if "班主任" in row_text and "班级" in row_text:
            header_row = idx
            break
    if header_row is None:
        raise HTTPException(status_code=400, detail="无法识别班主任明细表头")
    df = pd.read_excel(io.BytesIO(content), header=header_row)
    teacher_col = class_col = None
    for col in df.columns:
        col_str = str(col)
        if "班主任" in col_str and teacher_col is None:
            teacher_col = col
        if "班级" in col_str and class_col is None:
            class_col = col
    if teacher_col is None or class_col is None:
        raise HTTPException(status_code=400, detail="无法定位'班主任'或'班级'列")
    results = []
    for _, row in df.iterrows():
        teacher = _clean_value(row[teacher_col])
        class_name = _clean_value(row[class_col])
        if teacher is not None and class_name is not None:
            results.append({"teacher_name": str(teacher).strip(), "class_name": str(class_name).strip()})
    return results


@router.post("/upload-teachers")
async def upload_teachers(file: UploadFile = File(...)):
    """上传班主任名单 -> 更新 students.homeroom_teacher."""
    from services.excel_parser import normalize_class_name
    content = await file.read()
    mappings = _parse_teacher_file(content, file.filename)
    safe_name = _safe_filename(file.filename)
    saved_path = UPLOAD_DIR / f"teacher_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    with open(saved_path, "wb") as f:
        f.write(content)
    with get_db() as conn:
        before = _homeroom_helper.count_homeroom_set()
        updated_classes = 0
        for item in mappings:
            class_name = normalize_class_name(item["class_name"], conn=conn)
            teacher = item["teacher_name"]
            if not class_name or not teacher:
                continue
            cur = _homeroom_helper.update_homeroom_by_class_name(teacher, class_name, conn=conn)
            if cur > 0:
                updated_classes += 1
        conn.commit()
        after = _homeroom_helper.count_homeroom_set()
    log_operation("班主任导入", f"上传 {file.filename}，更新 {updated_classes} 个班级，{after - before} 名学生")
    return {"file_name": file.filename, "mappings": len(mappings),
            "updated_classes": updated_classes, "updated_students": after - before}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    grade_id: Optional[int] = Form(None),
    major_id: Optional[int] = Form(None),
    exam_type: Optional[str] = Form("月考"),
    school_year: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    month: Optional[int] = Form(None),
    subject_config: Optional[str] = Form(None),
):
    """上传单个成绩文件 — 创建 import_files 记录."""
    from services.excel_parser import parse_score_file
    import zipfile, io
    content = await file.read()
    file_id = import_file_repo.create(file.filename, grade_id, major_id, exam_type,
                                      school_year, semester, month, subject_config=subject_config)
    safe_name = _safe_filename(file.filename)
    saved_path = UPLOAD_DIR / f"{file_id}_{safe_name}"
    with open(saved_path, "wb") as f:
        f.write(content)
    student_count = 0
    if file.filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for ef in [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls", ".csv"))]:
                student_count += len(parse_score_file(zf.read(ef), ef))
    else:
        student_count = len(parse_score_file(content, file.filename))
    import_file_repo.update_file_info(file_id, str(saved_path), student_count)
    log_operation("数据导入", f"上传文件 {file.filename} ({student_count}条)")
    return {"id": file_id, "file_name": file.filename, "student_count": student_count}


@router.post("/upload-multi")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    grade_id: Optional[int] = Form(None),
    major_id: Optional[int] = Form(None),
    exam_type: Optional[str] = Form("月考"),
    school_year: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    month: Optional[int] = Form(None),
    subject_config: Optional[str] = Form(None),
):
    """批量上传成绩文件."""
    from services.excel_parser import parse_score_file
    import zipfile, io
    results = []
    for upload in files:
        content = await upload.read()
        file_id = import_file_repo.create(upload.filename, grade_id, major_id, exam_type,
                                          school_year, semester, month, subject_config=subject_config)
        safe_name = _safe_filename(upload.filename)
        saved_path = UPLOAD_DIR / f"{file_id}_{safe_name}"
        with open(saved_path, "wb") as f:
            f.write(content)
        student_count = 0
        if upload.filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for ef in [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls", ".csv"))]:
                    student_count += len(parse_score_file(zf.read(ef), ef))
        else:
            student_count = len(parse_score_file(content, upload.filename))
        import_file_repo.update_file_info(file_id, str(saved_path), student_count)
        results.append({"id": file_id, "file_name": upload.filename, "student_count": student_count})
        log_operation("数据导入", f"上传文件 {upload.filename} ({student_count}条)")
    return {"uploaded": results}


@router.get("/files")
def list_import_files():
    """列出所有 import_files 记录."""
    return import_file_repo.list_all()


@router.post("/validate/{file_id}")
def validate_file(file_id: int):
    """校验 import file — 委托 service."""
    return validate_import_file(file_id)


class ConfirmImport(BaseModel):
    exam_name: str
    exam_date: Optional[str] = None
    school_year: Optional[str] = None
    semester: Optional[str] = None
    month: Optional[int] = None
    merge_exam_id: Optional[int] = None
    subject_config: Optional[Dict[str, Dict[str, float]]] = None
    class_mapping: Optional[Dict[str, int]] = None
    overwrite_existing: Optional[bool] = False


class BatchFileConfig(BaseModel):
    file_id: int
    exam_name: Optional[str] = None
    class_mapping: Optional[Dict[str, int]] = None
    overwrite_existing: Optional[bool] = False


class ConfirmBatchImport(BaseModel):
    files: List[BatchFileConfig]
    exam_date: Optional[str] = None
    subject_config: Optional[Dict[str, Dict[str, float]]] = None


@router.post("/confirm/{file_id}")
def confirm_import(file_id: int, payload: ConfirmImport):
    """确认单个文件导入 — 委托 service."""
    return confirm_import_file(file_id, payload)


@router.post("/confirm-batch")
def confirm_batch_import(payload: ConfirmBatchImport):
    """批量确认导入 — 委托 service."""
    return confirm_batch_import_files(payload)


@router.delete("/delete/{file_id}")
def delete_import_file(file_id: int):
    """删除 import file 记录及关联文件."""
    row = import_file_repo.get_by_id(file_id)
    if row and row["file_path"]:
        try:
            Path(row["file_path"]).unlink(missing_ok=True)
        except Exception as e:
            log_operation("数据导入", f"删除上传文件失败 id={file_id}：{e}", status="警告")
    import_file_repo.delete_record(file_id)
    return {"deleted": file_id}
