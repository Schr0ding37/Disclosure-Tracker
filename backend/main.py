from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import subprocess
import json

app = FastAPI()

# 允許跨域請求
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"]
)

# 配置路徑
KEYWORDS_FILE = "/app/keywords.txt"
PROGRESS_FILE = "/app/fetcher/progress.json"
LOG_FILE = "/app/backfill.log"

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://mops:mops123@db:5432/mops"))

# --- 關鍵字管理 ---

@app.get("/keywords")
def get_keywords():
    if not os.path.exists(KEYWORDS_FILE):
        return {"keywords": []}
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        kws = [line.strip() for line in f if line.strip()]
    return {"keywords": kws}

@app.post("/keywords")
def save_keywords(data: dict = Body(...)):
    try:
        keywords = data.get("keywords", [])
        with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
            for kw in keywords:
                if kw.strip():
                    f.write(f"{kw.strip()}\n")
        
        # 儲存後立即執行「當日最新」掃描
        subprocess.Popen(["python3", "/app/fetcher/fetch_daily.py"])
        
        return {"status": "success", "trigger": "scan_started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 通知與資料查詢 ---

@app.get("/notifications")
def get_notifications():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    query = """
        SELECT a.matched_keyword, d.company_name, d.company_code, d.subject, 
               d.publish_date, d.publish_time, d.content
        FROM alerts a
        JOIN disclosures d ON a.disclosure_id = d.id
        ORDER BY a.created_at DESC
    """
    cur.execute(query)
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

@app.delete("/notifications")
def clear_notifications():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM alerts")
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "All notifications cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/filter")
def filter_data(start_date: str, end_date: str, company: str = "", keyword: str = ""):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM disclosures WHERE publish_date BETWEEN %s AND %s"
    params = [start_date, end_date]
    
    if company:
        query += " AND (company_name ILIKE %s OR company_code ILIKE %s)"
        params.extend([f"%{company}%", f"%{company}%"])
        
    if keyword:
        query += " AND (subject ILIKE %s OR content ILIKE %s)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
        
    query += " ORDER BY publish_date DESC, publish_time DESC"
    
    cur.execute(query, tuple(params))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

# --- 歷史補件進度監控 ---

@app.get("/backfill/status")
def get_backfill_status():
    """ 讀取 progress.json 傳回目前進度 """
    if not os.path.exists(PROGRESS_FILE):
        return {"status": "no_progress_file", "details": "尚未開始歷史補件或檔案未建立"}
    
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            prog = json.load(f)
        return prog
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/backfill/log")
def get_backfill_log(lines: int = 20):
    """ 讀取最後幾行 backfill.log """
    if not os.path.exists(LOG_FILE):
        return {"log": "Log file not found."}
    
    try:
        # 使用系統指令 tail 快速抓取最後幾行
        result = subprocess.check_output(["tail", f"-n {lines}", LOG_FILE])
        return {"log": result.decode("utf-8")}
    except Exception as e:
        return {"log": f"Error reading log: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)