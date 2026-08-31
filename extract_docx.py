from docx import Document
import sys

doc = Document(r'H:\DAIMA\CJjiangxuej\智能纪要：成绩管理系统功能规划.docx')
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    if text:
        print(f'{i+1}→{text}')
