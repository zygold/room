import pandas as pd
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from services.excel_parser import _list_sheets, _read_with_engines, _find_detail_header_row

file_path = r'h:\DAIMA\CJjiangxuej\奖学金\2025-2026下期半期考试记分册.xlsx'

sheets, engine = _list_sheets(file_path)

for sheet in sheets:
    if '电子' not in sheet:
        continue
    df_raw = _read_with_engines(file_path, sheet_name=sheet, header=None, engine=engine)
    detail_row = _find_detail_header_row(df_raw)
    if detail_row is None:
        continue
    df = _read_with_engines(file_path, sheet_name=sheet, header=detail_row, engine=engine)
    for idx, row in df.iterrows():
        name = str(row.iloc[1]) if len(row) > 1 else ''
        if '杨卿' in name:
            print(f'\n=== Sheet: {sheet}, Row: {idx} ===')
            print('Headers:', df.columns.tolist())
            print('Row values:')
            for col, val in zip(df.columns, row.values):
                print(f'  {col}: {val}')
