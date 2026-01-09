from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"],  # 必須是星號，確保外部電腦瀏覽器能存取
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"]
)

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://mops:mops123@db:5432/mops"))

# 關鍵字檔案路徑 (對應 Docker 掛載路徑)
KEYWORDS_FILE = "/app/keywords.txt"

@app.get("/keywords")
def get_keywords():
    if not os.path.exists(KEYWORDS_FILE):
        return {"keywords": []}
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        # 讀取並去除空白行
        kws = [line.strip() for line in f if line.strip()]
    return {"keywords": kws}

@app.post("/keywords")
def save_keywords(data: dict = Body(...)):
    keywords = data.get("keywords", [])
    with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
        for kw in keywords:
            if kw.strip():
                f.write(f"{kw.strip()}\n")
    return {"status": "success"}

@app.get("/notifications")
def get_notifications():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # 抓取最近 20 筆命中的通知
    query = """
        SELECT a.matched_keyword, d.company_name, d.subject, d.publish_date, d.publish_time
        FROM alerts a
        JOIN disclosures d ON a.disclosure_id = d.id
        ORDER BY a.created_at DESC
        LIMIT 20
    """
    cur.execute(query)
    res = cur.fetchall()
    cur.close(); conn.close()
    return res

@app.get("/filter")
def filter_records(start_date: str = None, end_date: str = None, keyword: str = None):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    query = "SELECT * FROM disclosures WHERE 1=1"
    params = []
    if start_date: 
        query += " AND publish_date >= %s"; params.append(start_date)
    if end_date: 
        query += " AND publish_date <= %s"; params.append(end_date)
    if keyword: 
        query += " AND (subject ILIKE %s OR content ILIKE %s)"; 
        params.append(f"%{keyword}%"); params.append(f"%{keyword}%")
    
    query += " ORDER BY publish_date DESC, publish_time DESC LIMIT 100"
    cur.execute(query, tuple(params))
    res = cur.fetchall()
    cur.close(); conn.close()
    return res