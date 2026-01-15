import requests
import psycopg2
from datetime import date
import os

DB_URL = os.getenv("DATABASE_URL", "postgresql://mops:mops123@db:5432/mops")
KEYWORDS_FILE = "/app/keywords.txt"

def roc_to_ad(roc_str):
    if not roc_str: return None
    try:
        s = str(roc_str).replace("/", "").replace("-", "").strip()
        if len(s) == 7:
            y, m, d = int(s[:3]), int(s[3:5]), int(s[5:])
            return f"{y + 1911:04d}-{m:02d}-{d:02d}"
        elif len(s) == 6:
            y, m, d = int(s[:2]), int(s[2:4]), int(s[4:])
            return f"{y + 1911:04d}-{m:02d}-{d:02d}"
        return None
    except:
        return None

def normalize_time(t):
    """將 API 數字時間(如 65141) 轉為標準 06:51:41"""
    if not t: return "00:00:00"
    s = str(t).strip().zfill(6)
    return f"{s[:2]}:{s[2:4]}:{s[4:]}"

def load_keywords():
    if not os.path.exists(KEYWORDS_FILE): return []
    try:
        with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except: return []

def save(records, market):
    keywords = load_keywords()
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    print(f"正在處理 {market}，共 {len(records)} 筆...")

    for r in records:
        # 處理 API 可能出現的各種欄位變體
        code = r.get("公司代號") or r.get("SecuritiesCompanyCode")
        name = r.get("公司名稱") or r.get("CompanyName")
        p_date = roc_to_ad(r.get("發言日期") or r.get("Date"))
        p_time = normalize_time(r.get("發言時間"))
        # 特別處理 "主旨 " (帶空格)
        subject = (r.get("主旨") or r.get("主旨 ") or "").strip()
        content = (r.get("說明") or "").strip()

        if not code or not p_date: continue

        try:
            # 使用 ON CONFLICT DO UPDATE 確保一定能拿到 ID (RETURNING id)
            # 1. 確保 INSERT 欄位與你的 Schema 完全一致
            # 2. 加入 fetch_status 預設為 TRUE (因為 API 抓下來就是完整的)
            # 3. 加入 raw_onclick_params 預設為 NULL (API 資料沒有這個)
            cur.execute("""
                INSERT INTO disclosures 
                (market, company_code, company_name, publish_date, publish_time, 
                 subject, content, source_date, fetch_status, raw_onclick_params)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, NULL)
                ON CONFLICT (company_code, publish_date, publish_time, subject) 
                DO UPDATE SET company_name = EXCLUDED.company_name
                RETURNING id
            """, (market, code, name, p_date, p_time, subject, content, date.today()))
            
            res = cur.fetchone()
            if res:
                disclosure_id = res[0]
                # 比對關鍵字
                full_text = f"{subject} {content}"
                for kw in keywords:
                    if kw in full_text:
                        cur.execute("""
                            INSERT INTO alerts (disclosure_id, matched_keyword)
                            VALUES (%s, %s)
                            ON CONFLICT (disclosure_id, matched_keyword) DO NOTHING
                        """, (disclosure_id, kw))
        except Exception as e:
            print(f"跳過一筆資料: {e}")
            continue
                
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    TWSE = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
    TPEX = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O"
    try:
        # 加入 headers 模擬瀏覽器，防止被 API 阻擋
        headers = {'User-Agent': 'Mozilla/5.0'}
        save(requests.get(TWSE, headers=headers).json(), "TWSE")
        save(requests.get(TPEX, headers=headers).json(), "TPEx")
        print(f"✅ 監控完成! 目前時間: {date.today()}，監控中關鍵字: {load_keywords()}")
    except Exception as e:
        print(f"❌ 嚴重錯誤: {e}")