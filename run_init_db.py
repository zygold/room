import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import init_db

init_db()
print('数据库初始化完成')
