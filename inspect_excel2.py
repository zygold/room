import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\services')
from excel_parser import parse_score_file_with_meta

def inspect(path):
    print(f'=== {path} ===')
    with open(path, 'rb') as f:
        content = f.read()
    result = parse_score_file_with_meta(content, path)
    print('records:', len(result['records']))
    print('detected subjects:', result['detected_subjects'])
    from collections import Counter
    grades = Counter(r['class_name'][:2] if r['class_name'] else '' for r in result['records'])
    print('grade distribution:', dict(grades))
    classes = Counter(r['class_name'] for r in result['records'] if r['class_name'])
    print('classes:', sorted(classes.items()))
    print()

files = [
    (54, r'h:\DAIMA\CJjiangxuej\score-management-system\data\uploads\54_2025-2026上期高二期末成绩.xlsx'),
    (55, r'h:\DAIMA\CJjiangxuej\score-management-system\data\uploads\55_2025-2026上期高二专业期末成绩.xlsx'),
    (56, r'h:\DAIMA\CJjiangxuej\score-management-system\data\uploads\56_2025-2026上期高一期末成绩.xlsx'),
    (57, r'h:\DAIMA\CJjiangxuej\score-management-system\data\uploads\57_2025-2026上期高一专业期末成绩.xlsx'),
]
for fid, f in files:
    print('file_id:', fid)
    inspect(f)
