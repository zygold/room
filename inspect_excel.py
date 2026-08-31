import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend\services')
from excel_parser import parse_score_file_with_meta

def inspect(path):
    print(f'=== {path} ===')
    with open(path, 'rb') as f:
        content = f.read()
    result = parse_score_file_with_meta(content, path)
    print('detected subjects:', result['detected_subjects'])
    print('professional subjects:', result['professional_subjects'])
    # find 杨璐瑜
    found = []
    for rec in result['records']:
        if rec['name'] == '杨璐瑜':
            found.append(rec)
    print(f'杨璐瑜 found {len(found)} times')
    for rec in found:
        print('  ', rec)
    # print unique class names
    classes = set(r['class_name'] for r in result['records'] if r['class_name'])
    print('classes:', sorted(classes)[:20], '... total', len(classes))
    # sample keys and record
    if result['records']:
        print('sample keys:', list(result['records'][0].keys()))
        print('first record:', result['records'][0])
    print()

files = [
    r'h:\DAIMA\CJjiangxuej\score-management-system\data\uploads\51_24级10月月考成绩.xlsx',
    r'h:\DAIMA\CJjiangxuej\score-management-system\data\uploads\54_2025-2026上期高二期末成绩.xlsx',
    r'h:\DAIMA\CJjiangxuej\score-management-system\data\uploads\55_2025-2026上期高二专业期末成绩.xlsx',
]
for f in files:
    inspect(f)
