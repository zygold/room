import sqlite3
import sys
sys.path.insert(0, r'h:\DAIMA\CJjiangxuej\score-management-system\backend')
from database import DB_PATH
from services.excel_parser import normalize_class_name

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Fetch all classes
classes = conn.execute("SELECT id, name, grade_id, major_id, class_type_id FROM classes").fetchall()
classes = [dict(c) for c in classes]

# Group by normalized key (grade_id, normalized_name)
groups = {}
for c in classes:
    norm = normalize_class_name(c['name'])
    key = (c['grade_id'], norm)
    groups.setdefault(key, []).append(c)

merged = 0
for (grade_id, norm), group in groups.items():
    if len(group) <= 1:
        continue
    print(f"Merging {len(group)} classes into '{norm}': {[c['name'] for c in group]}")
    # Choose keeper: prefer class with class_type_id != 1 (本方/融通), otherwise first
    keeper = None
    for c in group:
        if c['class_type_id'] != 1:
            keeper = c
            break
    if not keeper:
        keeper = group[0]
    keep_id = keeper['id']
    # Decide final name: use normalized name, but keep "（本方）" if original keeper has it
    final_name = norm
    if '本方' in keeper['name'] and '（本方）' not in final_name and '(本方)' not in final_name:
        final_name = final_name + '（本方）'

    # Update keeper name if needed
    if keeper['name'] != final_name:
        conn.execute("UPDATE classes SET name=? WHERE id=?", (final_name, keep_id))
        print(f"  Renamed keeper id={keep_id} to '{final_name}'")

    # Merge others into keeper
    for c in group:
        if c['id'] == keep_id:
            continue
        # Update students
        cur = conn.execute("UPDATE students SET class_id=? WHERE class_id=?", (keep_id, c['id']))
        print(f"  Moved {cur.rowcount} students from id={c['id']} ({c['name']}) to id={keep_id}")
        # Delete duplicate class
        conn.execute("DELETE FROM classes WHERE id=?", (c['id'],))
        print(f"  Deleted duplicate id={c['id']} ({c['name']})")
        merged += 1

# Recalculate student counts
conn.execute("""
    UPDATE classes SET student_count = (
        SELECT COUNT(*) FROM students WHERE students.class_id = classes.id
    )
""")
conn.commit()
print(f"\nTotal duplicate groups merged: {merged}")

# Verify remaining classes containing 计算机/电/数
print('\n=== Remaining classes ===')
rows = conn.execute("""
    SELECT id, name, grade_id, major_id, class_type_id, student_count
    FROM classes
    WHERE name LIKE '%计算机%' OR name LIKE '%电%' OR name LIKE '%数%'
    ORDER BY name
""").fetchall()
for r in rows:
    print(dict(r))

conn.close()
