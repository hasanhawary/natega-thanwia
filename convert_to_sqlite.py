import sqlite3
import openpyxl
import os
import time
import gzip
import shutil

excel_path = "/Users/hassanelhawary/Work/Elhawary/Projects/natega-thanwia/نتيجة ثانوية عامة نظام حديث.xlsx"
db_path = "/Users/hassanelhawary/Work/Elhawary/Projects/natega-thanwia/students.db"
gz_path = "/Users/hassanelhawary/Work/Elhawary/Projects/natega-thanwia/public/students.db.gz"

if os.path.exists(db_path):
    os.remove(db_path)

print("Connecting to SQLite...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS statuses (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    seating_no INTEGER PRIMARY KEY,
    name TEXT,
    grade REAL,
    status_id INTEGER,
    FOREIGN KEY(status_id) REFERENCES statuses(id)
)
""")

conn.commit()

print("Loading workbook...")
wb = openpyxl.load_workbook(excel_path, read_only=True)
sheet = wb.active

statuses_map = {}
def get_status_id(status_name):
    if not status_name:
        return None
    status_name = status_name.strip()
    if status_name not in statuses_map:
        cursor.execute("INSERT OR IGNORE INTO statuses (name) VALUES (?)", (status_name,))
        cursor.execute("SELECT id FROM statuses WHERE name = ?", (status_name,))
        row = cursor.fetchone()
        statuses_map[status_name] = row[0]
    return statuses_map[status_name]

print("Reading Excel and inserting into SQLite...")
batch = []
start_time = time.time()

for i, row in enumerate(sheet.iter_rows(min_row=2, values_only=True)):
    if row[0] is None:
        continue
    
    seating_no = int(row[0])
    name = row[1].strip() if row[1] else ""
    try:
        grade = float(row[2]) if row[2] is not None else 0.0
    except ValueError:
        grade = 0.0
        
    status_id = get_status_id(row[3])
    
    batch.append((seating_no, name, grade, status_id))
    
    if len(batch) >= 10000:
        cursor.executemany("INSERT INTO students (seating_no, name, grade, status_id) VALUES (?, ?, ?, ?)", batch)
        batch = []
        if (i+1) % 100000 == 0:
            print(f"  Inserted {i+1} rows...")

if batch:
    cursor.executemany("INSERT INTO students (seating_no, name, grade, status_id) VALUES (?, ?, ?, ?)", batch)

print("Committing inserts...")
conn.commit()

print("Creating indexes...")
cursor.execute("CREATE INDEX idx_students_name ON students(name)")
cursor.execute("CREATE INDEX idx_students_grade ON students(grade)")
conn.commit()

# Optimize database
print("Vacuuming database...")
cursor.execute("VACUUM")
conn.commit()

conn.close()

db_size = os.path.getsize(db_path)
print(f"Database size: {db_size / (1024*1024):.2f} MB")

# Create public directory if not exists
os.makedirs(os.path.dirname(gz_path), exist_ok=True)

print("Compressing database to public/students.db.gz...")
with open(db_path, 'rb') as f_in:
    with gzip.open(gz_path, 'wb', compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)

gz_size = os.path.getsize(gz_path)
print(f"Gzipped database size: {gz_size / (1024*1024):.2f} MB")
print(f"Finished in {time.time() - start_time:.2f} seconds.")
