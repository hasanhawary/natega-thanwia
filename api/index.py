from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import urllib.parse

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Helper to find and load SQLite database (supports decompression to /tmp on Vercel)
import gzip
import shutil

DATABASE_PATH = '/tmp/students.db'

if not os.path.exists(DATABASE_PATH):
    POSSIBLE_GZ_PATHS = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), 'students.db.gz')),
        os.path.abspath(os.path.join(os.getcwd(), 'public', 'students.db.gz')),
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'public', 'students.db.gz')),
        os.path.abspath(os.path.join(os.getcwd(), 'students.db.gz')),
        os.path.abspath(os.path.join(os.getcwd(), 'students.db')),
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'students.db'))
    ]
    
    gz_path = None
    for p in POSSIBLE_GZ_PATHS:
        if os.path.exists(p):
            gz_path = p
            break
            
    if gz_path:
        if gz_path.endswith('.gz'):
            print(f"Decompressing {gz_path} to {DATABASE_PATH}...")
            with gzip.open(gz_path, 'rb') as f_in:
                with open(DATABASE_PATH, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out, length=1024*1024)
            print("Decompression finished.")
        else:
            print(f"Copying {gz_path} to {DATABASE_PATH}...")
            shutil.copyfile(gz_path, DATABASE_PATH)
    else:
        # Final fallback
        DATABASE_PATH = os.path.abspath(os.path.join(os.getcwd(), 'students.db'))

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Helper to normalize Arabic names
def normalize_arabic(text):
    return text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ة', 'ه').replace('ى', 'ي').strip()

@app.route('/api/search', methods=['GET'])
def search():
    try:
        # 1. Parse Query Parameters
        q = request.args.get('q', '').strip()
        search_mode = request.args.get('mode', 'name') # 'name' | 'seating'
        match_mode = request.args.get('match', 'prefix') # 'prefix' | 'exact' | 'contains'
        sectors = request.args.get('sectors', '').split(',')
        statuses = request.args.get('statuses', '').split(',')
        min_grade = float(request.args.get('min_grade', 0))
        max_grade = float(request.args.get('max_grade', 320))
        limit = int(request.args.get('limit', 100))

        # Filter empty strings from list
        sectors = [s for s in sectors if s]
        statuses = [s for s in statuses if s]

        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = []
        params = []

        # Filter: Status
        if statuses:
            placeholders = ','.join('?' for _ in statuses)
            conditions.append(f"s.status_id IN ({placeholders})")
            params.extend(map(int, statuses))
        else:
            return jsonify({"results": [], "charts": {"grades": {}, "statuses": {}}})

        # Filter: Grade
        conditions.append("s.grade >= ? AND s.grade <= ?")
        params.extend([min_grade, max_grade])

        # Filter: Sectors (Seating Range mapping)
        sector_conditions = []
        if 'cairo' in sectors:
            sector_conditions.append("(s.seating_no >= 2000000 AND s.seating_no <= 2380000)")
        if 'alex' in sectors:
            sector_conditions.append("(s.seating_no >= 2380001 AND s.seating_no <= 2550000)")
        if 'mansoura' in sectors:
            sector_conditions.append("(s.seating_no >= 2550001 AND s.seating_no <= 2820000)")
        if 'assiut' in sectors:
            sector_conditions.append("(s.seating_no >= 2820001 AND s.seating_no <= 3000000)")

        if sector_conditions:
            conditions.append(f"({ ' OR '.join(sector_conditions) })")
        else:
            return jsonify({"results": [], "charts": {"grades": {}, "statuses": {}}})

        # Filter: Search query
        show_leaderboard = True
        if q:
            show_leaderboard = False
            if search_mode == 'seating':
                try:
                    sno = int(q)
                    conditions.append("s.seating_no = ?")
                    params.append(sno)
                except ValueError:
                    return jsonify({"results": [], "charts": {"grades": {}, "statuses": {}}})
            else:
                prefix = normalize_arabic(q)
                if match_mode == 'exact':
                    conditions.append("s.name = ?")
                    params.append(prefix)
                elif match_mode == 'contains':
                    conditions.append("s.name LIKE ?")
                    params.append(f"%{prefix}%")
                else:
                    # 'prefix' range query for maximum B-Tree index utilization
                    conditions.append("s.name >= ? AND s.name < ?")
                    params.append(prefix)
                    
                    last_char = prefix[-1]
                    prefix_upper = prefix[:-1] + chr(ord(last_char) + 1)
                    params.append(prefix_upper)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Query 1: Get results
        results_query = f"""
            SELECT s.seating_no, s.name, s.grade, c.name as status_name 
            FROM students s 
            JOIN statuses c ON s.status_id = c.id
            {where_clause}
            ORDER BY s.grade DESC
            LIMIT ?
        """
        
        results_params = params.copy()
        results_params.append(limit)
        cursor.execute(results_query, results_params)
        rows = cursor.fetchall()
        
        results_list = []
        for r in rows:
            results_list.append({
                "seating_no": r["seating_no"],
                "name": r["name"],
                "grade": r["grade"],
                "status": r["status_name"]
            })

        # Query 2: Aggregate charts data (Combined scan for grades and statuses)
        agg_query = f"""
            SELECT 
                SUM(CASE WHEN grade >= 288 THEN 1 ELSE 0 END) as g90,
                SUM(CASE WHEN grade >= 256 AND grade < 288 THEN 1 ELSE 0 END) as g80,
                SUM(CASE WHEN grade >= 224 AND grade < 256 THEN 1 ELSE 0 END) as g70,
                SUM(CASE WHEN grade >= 192 AND grade < 224 THEN 1 ELSE 0 END) as g60,
                SUM(CASE WHEN grade >= 160 AND grade < 192 THEN 1 ELSE 0 END) as g50,
                SUM(CASE WHEN grade < 160 THEN 1 ELSE 0 END) as g_fail,
                SUM(CASE WHEN status_id = 1 THEN 1 ELSE 0 END) as s1,
                SUM(CASE WHEN status_id = 2 THEN 1 ELSE 0 END) as s2,
                SUM(CASE WHEN status_id = 3 THEN 1 ELSE 0 END) as s3,
                SUM(CASE WHEN status_id = 4 THEN 1 ELSE 0 END) as s4
            FROM students s
            {where_clause}
        """
        cursor.execute(agg_query, params)
        agg_row = cursor.fetchone()
        
        charts_grade = {
            "g90": agg_row["g90"] or 0,
            "g80": agg_row["g80"] or 0,
            "g70": agg_row["g70"] or 0,
            "g60": agg_row["g60"] or 0,
            "g50": agg_row["g50"] or 0,
            "g_fail": agg_row["g_fail"] or 0
        }
        
        charts_status = {
            "passed": agg_row["s1"] or 0,
            "second": agg_row["s2"] or 0,
            "failed": agg_row["s3"] or 0,
            "absent": agg_row["s4"] or 0
        }

        conn.close()

        return jsonify({
            "results": results_list,
            "charts": {
                "grades": charts_grade,
                "statuses": charts_status
            }
        })
    except Exception as e:
        print("API Search Error:", str(e))
        return jsonify({"error": str(e), "results": [], "charts": {"grades": {}, "statuses": {}}}), 500

@app.route('/api/rank', methods=['GET'])
def get_rank():
    try:
        grade = float(request.args.get('grade', 0))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Count rank using index on grade
        cursor.execute("SELECT COUNT(*) + 1 as rank FROM students WHERE grade > ?", (grade,))
        row = cursor.fetchone()
        rank = row["rank"]
        
        conn.close()
        
        # Calculate Percentile
        total_students = 919396
        percentile = ((total_students - rank) / total_students) * 100
        percentile = max(0.1, min(100.0, percentile))
        
        return jsonify({
            "rank": rank,
            "percentile": percentile
        })
    except Exception as e:
        print("API Rank Error:", str(e))
        return jsonify({"error": str(e)}), 500
