import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from services.excel_parser import parse_score_file_with_meta

file_path = r'h:\DAIMA\CJjiangxuej\奖学金\2025-2026下期半期考试记分册.xlsx'

with open(file_path, 'rb') as f:
    content = f.read()

result = parse_score_file_with_meta(content, '2025-2026下期半期考试记分册.xlsx')
records = result['records']

print(f'Total records: {len(records)}')
print(f'Detected subjects: {result["detected_subjects"]}')
print(f'Professional subjects count: {len(result["professional_subjects"])}')

# Check for anomalies
bad_records = []
for r in records:
    prof = r.get('专业课')
    if prof is not None and isinstance(prof, (int, float)):
        if prof > 10000 or prof < 0:
            bad_records.append(r)

print(f'\nRecords with abnormal professional score: {len(bad_records)}')
for r in bad_records[:5]:
    print(r)

# Sample a few records from different classes
from collections import defaultdict
by_class = defaultdict(list)
for r in records:
    by_class[r.get('class_name')].append(r)

print('\nSample records by class:')
for cls, recs in list(by_class.items())[:5]:
    r = recs[0]
    print(f"{cls}: {r.get('name')}, 语文={r.get('语文')}, 数学={r.get('数学')}, 英语={r.get('英语')}, 专业课={r.get('专业课')}, 总分={r.get('总分')}, 明细={r.get('专业课明细')}")
