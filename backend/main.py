from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import subprocess

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
    try:
        keywords = data.get("keywords", [])
        with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
            for kw in keywords:
                if kw.strip():
                    f.write(f"{kw.strip()}\n")
        
        # 【關鍵】儲存後立即在背景執行掃描腳本
        # 使用 Popen 不會阻塞 API 回傳
        subprocess.Popen(["python3", "/app/fetcher/fetch_daily.py"])
        
        return {"status": "success", "trigger": "scan_started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
def filter_data(start_date: str, end_date: str, company: str = "", keyword: str = ""):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 基礎查詢：日期區間
    query = "SELECT * FROM disclosures WHERE publish_date BETWEEN %s AND %s"
    params = [start_date, end_date]
    
    # 動態增加公司過濾 (代號或名稱)
    if company:
        query += " AND (company_name ILIKE %s OR company_code ILIKE %s)"
        params.extend([f"%{company}%", f"%{company}%"])
        
    # 動態增加關鍵字過濾 (主旨或內文)
    if keyword:
        query += " AND (subject ILIKE %s OR content ILIKE %s)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
        
    query += " ORDER BY publish_date DESC, publish_time DESC"
    
    cur.execute(query, tuple(params))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

# 【新增】清除所有通知的接口
@app.delete("/notifications")
def clear_notifications():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # 刪除 alerts 表中所有資料
        cur.execute("DELETE FROM alerts")
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "All notifications cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))