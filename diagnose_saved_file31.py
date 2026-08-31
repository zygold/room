import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from services.excel_parser import parse_score_file_with_meta

file_path = r'h:\DAIMA\CJjiangxuej\score-management-system\data\uploads\31_2025-2026下期半期考试记分册.xlsx'

with open(file_path, 'rb') as f:
    content = f.read()

result = parse_score_file_with_meta(content, '2025-2026下期半期考试记分册.xlsx')
records = result['records']

yangqing = [r for r in records if '杨卿' in r.get('name', '')]
print(f'Found {len(yangqing)} records for 杨卿 in saved file id=31')
for r in yangqing:
    print(r)

print('\n=== Records with professional > 100000 ===')
for r in records:
    prof = r.get('专业课')
    if prof is not None and isinstance(prof, (int, float)) and prof > 100000:
        print(r.get('name'), r.get('class_name'), prof, r.get('专业课明细'))

print('\n=== Detected subjects ===')
print(result['detected_subjects'])
