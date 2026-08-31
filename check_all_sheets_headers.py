import pandas as pd
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from services.excel_parser import _list_sheets, _read_with_engines, _find_detail_header_row

file_path = r'h:\DAIMA\CJjiangxuej\奖学金\2025-2026下期半期考试记分册.xlsx'

sheets, engine = _list_sheets(file_path)

print('All sheet headers:')
for sheet in sheets:
    try:
        df_raw = _read_with_engines(file_path, sheet_name=sheet, header=None, engine=engine)
        detail_row = _find_detail_header_row(df_raw)
        if detail_row is None:
            print(f'\n{sheet}: no detail row found')
            continue
        df = _read_with_engines(file_path, sheet_name=sheet, header=detail_row, engine=engine)
        headers = [str(h) for h in df.columns.tolist()]
        print(f'\n{sheet}: {headers}')
    except Exception as e:
        print(f'\n{sheet}: ERROR {e}')
