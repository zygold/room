import pandas as pd

file_path = r'h:\DAIMA\CJjiangxuej\test_export_4.xlsx'

xl = pd.ExcelFile(file_path)
print('Sheets:', xl.sheet_names)

for sheet in xl.sheet_names:
    print(f'\n=== Sheet: {sheet} ===')
    df = pd.read_excel(file_path, sheet_name=sheet)
    print('Shape:', df.shape)
    print('Columns:', df.columns.tolist())
    print(df.head(3).to_string())
