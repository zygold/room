import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from services.excel_parser import parse_score_file_with_meta

file_path = r'h:\DAIMA\CJjiangxuej\奖学金\2025-2026下期半期考试记分册.xlsx'

with open(file_path, 'rb') as f:
    content = f.read()

result = parse_score_file_with_meta(content, '2025-2026下期半期考试记分册.xlsx')
records = result['records']

yangqing = [r for r in records if '杨卿' in r.get('name', '')]
print(f'Found {len(yangqing)} records for 杨卿')
for r in yangqing:
    print(f"Sheet: {r.get('sheet_name')}, Class: {r.get('class_name')}, 语文: {r.get('语文')}, 数学: {r.get('数学')}, 英语: {r.get('英语')}, 专业课: {r.get('专业课')}, 总分: {r.get('总分')}")
