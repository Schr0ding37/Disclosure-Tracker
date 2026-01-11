from fastapi import FastAPI, Body, HTTPException, Depends, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import subprocess
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext
import zipfile
import io
import json

# --- Configuration ---
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

# --- Security Setup ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- Models ---
class User(BaseModel):
    username: str
    role: str

class UserInDB(User):
    password_hash: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"  # 'admin' or 'user'

# --- Database & Auth Utils ---
def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://mops:mops123@db:5432/mops"))

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return User(username=username, role=role)

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

# --- Startup Event ---
@app.on_event("startup")
def startup_event():
    """Check DB for users table and create default admin if not exists"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Ensure users table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Ensure disclosures table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS disclosures (
                id SERIAL PRIMARY KEY,
                market VARCHAR(10),
                company_code VARCHAR(10),
                company_name VARCHAR(100),
                publish_date DATE,
                publish_time TIME,
                subject TEXT,
                content TEXT,
                source_date DATE,
                UNIQUE (company_code, publish_date, publish_time, subject)
            );
        """)
        
        # Ensure alerts table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                disclosure_id INTEGER REFERENCES disclosures(id),
                matched_keyword VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT unique_alert UNIQUE(disclosure_id, matched_keyword)
            );
        """)
        
        # Check for Admin user
        cur.execute("SELECT id FROM users WHERE username = 'Admin'")
        if not cur.fetchone():
            print("Creating default Admin user...")
            admin_pwd = get_password_hash("password")
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                ("Admin", admin_pwd, "admin")
            )
            conn.commit()
            print("Default Admin user created.")
        else:
            print("Admin user already exists.")
            
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Startup Error: {e}")

# --- Auth Endpoints ---
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s", (form_data.username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user or not verify_password(form_data.password, user['password_hash']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Store role in the token claims so we can check it
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user['username'], "role": user['role']},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(new_user: UserCreate, current_admin: User = Depends(get_current_admin)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check existing
        cur.execute("SELECT id FROM users WHERE username = %s", (new_user.username,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Username already registered")
        
        hashed_pw = get_password_hash(new_user.password)
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
            (new_user.username, hashed_pw, new_user.role)
        )
        conn.commit()
        return {"status": "success", "username": new_user.username, "role": new_user.role}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# --- Health Check Endpoint (Public) ---
@app.get("/health")
def health_check():
    """Health check endpoint for monitoring API status"""
    try:
        start_time = datetime.now()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        db_status = "connected"
        response_time = (datetime.now() - start_time).total_seconds() * 1000  # Convert to milliseconds
    except Exception as e:
        db_status = "disconnected"
        response_time = 0
    
    return {
        "status": "operational" if db_status == "connected" else "degraded",
        "database": db_status,
        "timestamp": datetime.now().isoformat(),
        "response_time_ms": round(response_time, 2)
    }

# --- Existing Endpoints (Protected) ---

# 關鍵字檔案路徑 (對應 Docker 掛載路徑)
KEYWORDS_FILE = "/app/keywords.txt"

def load_keywords_from_file():
    if not os.path.exists(KEYWORDS_FILE):
        return []
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def rescan_alerts(keywords):
    """Rebuild alerts table against all historical disclosures using current keywords."""
    conn = get_db_connection()
    select_cur = conn.cursor(cursor_factory=RealDictCursor)
    insert_cur = conn.cursor()
    alerts_created = 0
    disclosures_scanned = 0
    try:
        insert_cur.execute("DELETE FROM alerts")
        if not keywords:
            conn.commit()
            return {"disclosures_scanned": disclosures_scanned, "alerts_created": alerts_created}

        select_cur.execute("SELECT id, subject, content FROM disclosures")
        while True:
            batch = select_cur.fetchmany(500)
            if not batch:
                break
            disclosures_scanned += len(batch)
            for row in batch:
                full_text = f"{row.get('subject') or ''} {row.get('content') or ''}"
                for kw in keywords:
                    if kw in full_text:
                        insert_cur.execute("""
                            INSERT INTO alerts (disclosure_id, matched_keyword)
                            VALUES (%s, %s)
                            ON CONFLICT (disclosure_id, matched_keyword) DO NOTHING
                        """, (row["id"], kw))
                        if insert_cur.rowcount > 0:
                            alerts_created += 1
        conn.commit()
        return {"disclosures_scanned": disclosures_scanned, "alerts_created": alerts_created}
    finally:
        select_cur.close()
        insert_cur.close()
        conn.close()

@app.get("/keywords")
def get_keywords(current_user: User = Depends(get_current_user)):
    return {"keywords": load_keywords_from_file()}

@app.post("/keywords")
def save_keywords(data: dict = Body(...), current_admin: User = Depends(get_current_admin)):
    try:
        keywords = data.get("keywords", [])
        with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
            for kw in keywords:
                if kw.strip():
                    f.write(f"{kw.strip()}\n")
        
        # 【關鍵】儲存後立即在背景執行掃描腳本
        # 使用 Popen 不會阻塞 API 回傳
        subprocess.Popen(["python3", "/app/fetcher/fetch_daily.py"])

        # 重新掃描歷史資料，確保新增關鍵字會匹配既有公告
        rescan_result = rescan_alerts(load_keywords_from_file())
        
        return {"status": "success", "trigger": "scan_started", "rescan": rescan_result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 【新增】儀表板統計數據 API
@app.get("/stats/security")
def get_security_stats(current_user: User = Depends(get_current_user)):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. 計算日期範圍
        today = datetime.now().date()
        date_5_days_ago = today - timedelta(days=4)   # 含今天共5天
        date_30_days_ago = today - timedelta(days=29) # 含今天共30天
        
        stats = {
            "today_count": 0,
            "recent_5_days_count": 0,
            "recent_30_days_count": 0,
            "trend_30_days": [],
            "keyword_distribution_30_days": []
        }
        
        # 2. 查詢今日警示數
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM alerts a
            JOIN disclosures d ON a.disclosure_id = d.id
            WHERE d.publish_date = %s
        """, (today,))
        stats["today_count"] = cur.fetchone()["count"]
        
        # 3. 查詢近5日警示數
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM alerts a
            JOIN disclosures d ON a.disclosure_id = d.id
            WHERE d.publish_date >= %s
        """, (date_5_days_ago,))
        stats["recent_5_days_count"] = cur.fetchone()["count"]
        
        # 4. 查詢近30日警示數
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM alerts a
            JOIN disclosures d ON a.disclosure_id = d.id
            WHERE d.publish_date >= %s
        """, (date_30_days_ago,))
        stats["recent_30_days_count"] = cur.fetchone()["count"]
        
        # 5. 查詢近30日趨勢 (每天的警示數量)
        cur.execute("""
            SELECT d.publish_date, COUNT(*) as count
            FROM alerts a
            JOIN disclosures d ON a.disclosure_id = d.id
            WHERE d.publish_date >= %s
            GROUP BY d.publish_date
            ORDER BY d.publish_date ASC
        """, (date_30_days_ago,))
        rows = cur.fetchall()
        
        # 補齊沒有資料的日期為 0
        date_map = {row["publish_date"]: row["count"] for row in rows}
        current_date = date_30_days_ago
        while current_date <= today:
            stats["trend_30_days"].append({
                "date": current_date.isoformat(),
                "count": date_map.get(current_date, 0)
            })
            current_date += timedelta(days=1)
            
        # 6. 查詢近30日關鍵字分佈 (Top 10)
        cur.execute("""
            SELECT a.matched_keyword, COUNT(*) as count
            FROM alerts a
            JOIN disclosures d ON a.disclosure_id = d.id
            WHERE d.publish_date >= %s
            GROUP BY a.matched_keyword
            ORDER BY count DESC
            LIMIT 10
        """, (date_30_days_ago,))
        stats["keyword_distribution_30_days"] = cur.fetchall()

        # 7. 查詢近30日市場分佈 (上市/上櫃)
        cur.execute("""
            SELECT d.market, COUNT(*) as count
            FROM alerts a
            JOIN disclosures d ON a.disclosure_id = d.id
            WHERE d.publish_date >= %s
            GROUP BY d.market
        """, (date_30_days_ago,))
        stats["market_distribution_30_days"] = cur.fetchall()
        
        cur.close()
        conn.close()
        return stats
        
    except Exception as e:
        print(f"Stats Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/notifications")
def get_notifications(current_user: User = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 計算30天前的日期（與趨勢圖保持一致）
    today = datetime.now().date()
    date_30_days_ago = today - timedelta(days=29)  # 含今天共30天
    
    # 只抓取近30天的命中紀錄，與趨勢圖數據保持一致
    query = """
        SELECT a.matched_keyword, d.company_name, d.company_code, d.subject, 
               d.publish_date, d.publish_time, d.content
        FROM alerts a
        JOIN disclosures d ON a.disclosure_id = d.id
        WHERE d.publish_date >= %s
        ORDER BY a.created_at DESC
    """
    cur.execute(query, (date_30_days_ago,))
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

@app.get("/filter")
def filter_data(start_date: str, end_date: str, company: str = "", keyword: str = "", current_user: User = Depends(get_current_user)):
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
def clear_notifications(current_admin: User = Depends(get_current_admin)):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # 刪除 alerts 表中所有資料
        cur.execute("DELETE FROM alerts")
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "All notifications cleared"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 【新增】匯出資料包為 .dtt 檔案
@app.get("/export")
def export_data_package(current_admin: User = Depends(get_current_admin)):
    """Export all disclosures and keywords as a .dtt package (ZIP format)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. 查詢所有 disclosures 資料
        cur.execute("SELECT * FROM disclosures ORDER BY id")
        disclosures = cur.fetchall()
        
        # Convert datetime objects to strings for JSON serialization
        for disclosure in disclosures:
            if disclosure.get('publish_date'):
                disclosure['publish_date'] = str(disclosure['publish_date'])
            if disclosure.get('publish_time'):
                disclosure['publish_time'] = str(disclosure['publish_time'])
            if disclosure.get('source_date'):
                disclosure['source_date'] = str(disclosure['source_date'])
        
        cur.close()
        conn.close()
        
        # 2. 讀取 keywords
        keywords = []
        if os.path.exists(KEYWORDS_FILE):
            with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
                keywords = [line.strip() for line in f if line.strip()]
        
        # 3. 建立 manifest
        manifest = {
            "export_date": datetime.now().isoformat(),
            "version": "1.0",
            "record_count": len(disclosures),
            "keywords_count": len(keywords)
        }
        
        # 4. 建立 ZIP 檔案於記憶體中
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 寫入 manifest
            zip_file.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            
            # 寫入 disclosures
            zip_file.writestr('disclosures.json', json.dumps(disclosures, ensure_ascii=False, indent=2))
            
            # 寫入 keywords
            zip_file.writestr('keywords.txt', '\n'.join(keywords))
        
        # 5. 準備回傳 - 讀取完整的 bytes 資料
        zip_buffer.seek(0)
        zip_data = zip_buffer.read()
        filename = f"disclosure_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dtt"
        
        # 使用 io.BytesIO 包裝 bytes 資料以供 StreamingResponse 使用
        return StreamingResponse(
            io.BytesIO(zip_data),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        print(f"Export Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 【新增】匯入資料包從 .dtt 檔案
@app.post("/import")
async def import_data_package(file: UploadFile = File(...), current_admin: User = Depends(get_current_admin)):
    """Import disclosures and keywords from a .dtt package (ZIP format)"""
    try:
        # 1. 驗證檔案副檔名
        if not file.filename.endswith('.dtt'):
            raise HTTPException(status_code=400, detail="檔案格式錯誤，請上傳 .dtt 檔案")
        
        # 2. 讀取上傳的檔案
        contents = await file.read()
        zip_buffer = io.BytesIO(contents)
        
        # 3. 解壓縮並讀取內容
        with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
            # 驗證檔案結構
            required_files = ['manifest.json', 'disclosures.json', 'keywords.txt']
            zip_files = zip_file.namelist()
            
            for required in required_files:
                if required not in zip_files:
                    raise HTTPException(status_code=400, detail=f"資料包格式錯誤：缺少 {required}")
            
            # 讀取 manifest
            manifest_data = json.loads(zip_file.read('manifest.json').decode('utf-8'))
            
            # 讀取 disclosures
            disclosures_data = json.loads(zip_file.read('disclosures.json').decode('utf-8'))
            
            # 讀取 keywords
            keywords_data = zip_file.read('keywords.txt').decode('utf-8').strip().split('\n')
            keywords_data = [kw.strip() for kw in keywords_data if kw.strip()]
        
        # 4. 匯入到資料庫（使用 MERGE 策略 - 跳過重複）
        conn = get_db_connection()
        cur = conn.cursor()
        
        imported_count = 0
        skipped_count = 0
        
        for disclosure in disclosures_data:
            try:
                cur.execute("""
                    INSERT INTO disclosures 
                    (market, company_code, company_name, publish_date, publish_time, subject, content, source_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (company_code, publish_date, publish_time, subject) DO NOTHING
                """, (
                    disclosure.get('market'),
                    disclosure.get('company_code'),
                    disclosure.get('company_name'),
                    disclosure.get('publish_date'),
                    disclosure.get('publish_time'),
                    disclosure.get('subject'),
                    disclosure.get('content'),
                    disclosure.get('source_date')
                ))
                
                if cur.rowcount > 0:
                    imported_count += 1
                else:
                    skipped_count += 1
                    
            except Exception as e:
                print(f"Skip record due to error: {e}")
                skipped_count += 1
                continue
        
        conn.commit()
        
        # 5. 處理 keywords（使用 MERGE 策略 - 合併關鍵字）
        existing_keywords = []
        if os.path.exists(KEYWORDS_FILE):
            with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
                existing_keywords = [line.strip() for line in f if line.strip()]
        
        # 合併關鍵字（去除重複）
        merged_keywords = list(set(existing_keywords + keywords_data))
        merged_keywords.sort()  # 排序以便閱讀
        
        # 寫入合併後的關鍵字
        with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
            for kw in merged_keywords:
                f.write(f"{kw}\n")
        
        keywords_added = len(merged_keywords) - len(existing_keywords)
        
        cur.close()
        conn.close()
        
        # 6. 回傳匯入結果
        return {
            "status": "success",
            "message": "資料包匯入完成",
            "details": {
                "records_imported": imported_count,
                "records_skipped": skipped_count,
                "total_records": len(disclosures_data),
                "keywords_before": len(existing_keywords),
                "keywords_after": len(merged_keywords),
                "keywords_added": keywords_added,
                "export_date": manifest_data.get("export_date"),
                "export_version": manifest_data.get("version")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Import Error: {e}")
        raise HTTPException(status_code=500, detail=f"匯入失敗: {str(e)}")
