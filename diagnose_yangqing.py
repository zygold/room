import pandas as pd
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from services.excel_parser import parse_score_file_with_meta, _list_sheets, _read_with_engines, _find_detail_header_row

file_path = r'h:\DAIMA\CJjiangxuej\奖学金\2025-2026下期半期考试记分册.xlsx'

# List sheets
sheets, engine = _list_sheets(file_path)
print('Sheets:', sheets)

# Read raw first sheet
print('\n=== First sheet raw preview ===')
df_raw = _read_with_engines(file_path, sheet_name=sheets[0], header=None, engine=engine)
print(df_raw.head(10).to_string())
print('Shape:', df_raw.shape)

# Find detail header row
detail_row = _find_detail_header_row(df_raw)
print('\nDetail header row:', detail_row)
if detail_row is not None:
    print('Header row content:', df_raw.iloc[detail_row].tolist())

# Parse full file
print('\n=== Parse result for 杨卿 ===')
with open(file_path, 'rb') as f:
    content = f.read()
result = parse_score_file_with_meta(content, '2025-2026下期半期考试记分册.xlsx')
records = result['records']
yangqing = [r for r in records if '杨卿' in r.get('name', '')]
print(f'Found {len(yangqing)} records for 杨卿')
for r in yangqing:
    print(r)

print('\n=== Detected subjects ===')
print(result['detected_subjects'])
print('\n=== Professional subjects ===')
print(result['professional_subjects'])
