import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from services.excel_parser import parse_score_file_with_meta

file_path = r'h:\DAIMA\CJjiangxuej\score-management-system\data\uploads\32_2025-2026下期半期考试记分册.xlsx'

with open(file_path, 'rb') as f:
    content = f.read()

result = parse_score_file_with_meta(content, '2025-2026下期半期考试记分册.xlsx')
records = result['records']

yangqing = [r for r in records if '杨卿' in r.get('name', '')]
print('杨卿 records:')
for r in yangqing:
    print(f"  班级: {r.get('class_name')}")
    print(f"  语文: {r.get('语文')}, 数学: {r.get('数学')}, 英语: {r.get('英语')}")
    print(f"  专业课: {r.get('专业课')}")
    print(f"  专业课明细: {r.get('专业课明细')}")
    print(f"  总分: {r.get('总分')}")

print('\nDetected subjects:', result['detected_subjects'])
print('Professional max total:', next((s['max_score'] for s in result['detected_subjects'] if s['name'] == '专业课'), None))
