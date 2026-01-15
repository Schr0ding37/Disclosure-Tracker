import requests
import re
import time
import json
import random
import os
import psycopg2
import logging
import datetime  # 必須導入整個模組， logging 轉換器才抓得到
from datetime import date
from bs4 import BeautifulSoup
from collections import OrderedDict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time

# --- 配置 ---
DB_URL = os.getenv("DATABASE_URL", "postgresql://mops:mops123@mops-db:5432/mops")
PROGRESS_FILE = "/app/fetcher/progress.json"
KEYWORDS_FILE = "/app/keywords.txt"
TARGET_YEAR = int(os.getenv("BACKFILL_TARGET_YEAR", 114))

# 定義一個回傳台北時間的函數 (修正版)
def taipei_time(*args):
    # 使用 timezone 指定 UTC+8，避免與 from datetime import date 衝突
    tz_plus8 = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_plus8).timetuple()

# 關鍵設定：將 logging 的時間轉換器替換為台北時間
logging.Formatter.converter = taipei_time

# 設定日誌格式
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'  # 指定時間顯示格式
)
logger = logging.getLogger("Backfiller")

class MOPSHistoryManager:
    def __init__(self):
        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

        self.keywords = self.load_keywords()

        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://mopsov.twse.com.tw/mops/web/t51sb10_q1",
        }

    def load_keywords(self):
        if os.path.exists(KEYWORDS_FILE):
            with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def load_progress(self):
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        return {"current_year": 115, "current_month": 1, "current_kind_idx": 0, "current_page": 1}

    def save_progress(self, year, month, kind_idx, page):
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({"current_year": year, "current_month": month, "current_kind_idx": kind_idx, "current_page": page}, f)

    def fetch_list(self, year, month, kind, page=1):
        """
        kind: 'L' 為上市, 'O' 為上櫃
        """
        url = "https://mopsov.twse.com.tw/mops/web/ajax_t51sb10"

        payload = {
            "encodeURIComponent": "1", "step": "1", "firstin": "true",
            "TYPEK": "", "Stp": "4", "r1": "1", 
            "KIND": kind, 
            "year": str(year), "month1": str(month), 
            "begin_day": "1", "end_day": "31", 
            "Orderby": "1", "PCount": "100", "pagenum": str(page)
        }

        logger.info(f"  [Wait] 靜置後發送請求 (模擬閱讀時間)...")
        time.sleep(random.uniform(10, 15))

        try:
            res = self.session.post(url, data=payload, headers=self.base_headers, timeout=30)
            if "FOR SECURITY REASONS" in res.text: return "BLOCKED"
            res.encoding = 'utf-8'
            return res.text
        except: return "FETCH_FAILED"

    def extract_params(self, html):
        """
        使用 BeautifulSoup 精準提取表格中的公告參數
        """
        results = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. 找到所有資料列 (odd, even)
        rows = soup.find_all('tr', {'class': ['odd', 'even']})
        
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 6:
                continue
                
            # 取得公司基本資訊 (從表格欄位)
            co_code = tds[0].get_text(strip=True)
            co_name = tds[1].get_text(strip=True)
            
            # 2. 找到「詳細資料」按鈕，提取裡面的 onclick JS 程式碼
            btn = row.find('input', {'type': 'button', 'value': '詳細資料'})
            if btn and btn.get('onclick'):
                onclick_text = btn.get('onclick')
                
                # 使用 Regex 專門抓取 onclick 裡面的變數賦值
                # 這裡加入了 \s* 來處理可能的空格或換行
                pattern = (
                    r'seq_no\.value\s*=\s*["\'](\d+)["\'];.*?'
                    r'spoke_time\.value\s*=\s*["\'](\d+)["\'];.*?'
                    r'spoke_date\.value\s*=\s*["\'](\d+)["\'];.*?'
                    r'co_id\.value\s*=\s*["\'](\d+)["\'];.*?'
                    r'TYPEK\.value\s*=\s*["\'](\w+)["\']'
                )
                
                m = re.search(pattern, onclick_text, re.DOTALL)
                if m:
                    # 組合結果：(代號, 名稱, seq_no, 語音時間, 日期, co_id, 市場類型)
                    results.append((
                        co_code, 
                        co_name, 
                        m.group(1), 
                        m.group(2), 
                        m.group(3), 
                        m.group(4), 
                        m.group(5)
                    ))
        
        return results

    def fetch_detail(self, p):
        seq_no, spoke_time, spoke_date, co_id, typek = p
        url = "https://mopsov.twse.com.tw/mops/web/ajax_t05st01"
        payload = {
            "encodeURIComponent": "1", "step": "2", "firstin": "1", "off": "1",
            "co_id": co_id, "TYPEK": typek, "spoke_date": spoke_date,
            "spoke_time": spoke_time, "seq_no": seq_no
        }
        
        time.sleep(random.uniform(10, 15)) 
        res = self.session.post(url, data=payload, headers=self.base_headers, timeout=30)
        res.encoding = 'utf-8'
        return res.text

    def parse_detail(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table', {'class': 'hasBorder'})
        if not table: return None
        data = {}
        for tr in table.find_all('tr'):
            heads = tr.find_all('td', {'class': 'tblHead'})
            values = tr.find_all('td', {'class': 'odd'})
            if len(heads) == len(values) or (len(heads)==1 and len(values)==1):
                for h, v in zip(heads, values):
                    key = h.get_text(strip=True)
                    pre = v.find('pre')
                    val = pre.get_text().strip() if pre else v.get_text(strip=True)
                    data[key] = val.replace('\xa0', '')
        return data

    def roc_to_ad(self, date_str):
        s = str(date_str).strip()
        # 如果已經是 8 位數(西元)，直接格式化
        if len(s) == 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:]}"
        # 如果是 7 位數(民國)，才做轉換
        try:
            y = int(s[:-4]) + 1911
            return f"{y:04d}-{s[-4:-2]}-{s[-2:]}"
        except:
            return None

    def normalize_time(self, t):
        s = re.sub(r'[^0-9]', '', str(t)).zfill(6)
        return f"{s[:2]}:{s[2:4]}:{s[4:]}"

    def start_loop(self):
        prog = self.load_progress()
        curr_y, curr_m, curr_k_idx, curr_p = prog["current_year"], prog["current_month"], prog["current_kind_idx"], prog["current_page"]
        markets = [('L', '上市'), ('O', '上櫃')]
        
        logger.info(f"🚀 啟動歷史補件：{curr_y}年{curr_m}月 往回補至 {TARGET_YEAR}年")

        while curr_y >= TARGET_YEAR:
            while curr_m >= 1:
                try:
                    conn = psycopg2.connect(DB_URL)
                    cur = conn.cursor()
                    while curr_k_idx < len(markets):
                        m_kind, m_name = markets[curr_k_idx]
                        logger.info(f"📂 處理：{curr_y}年{curr_m}月 | 市場：{m_name}")
                        html = self.fetch_list(curr_y, curr_m, m_kind, curr_p)
                        
                        if html == "BLOCKED":
                            logger.error("🛑 偵測到行為封鎖！請暫停 30 分鐘再試。")
                            return
                        
                        if html != "NO_DATA" and html != "ERROR":
                            # logger.info(html)
                            matches = self.extract_params(html)
                            logger.info(f"  [+] 發現 {len(matches)} 筆公告")
                            for match in matches:
                                # 1. 拆解 match 參數 (順序須與 extract_params 一致)
                                # match = (co_code, co_name, seq_no, s_time, s_date, co_id_param, typek)
                                co_code, co_name = match[0], match[1].strip()
                                seq_no, s_time, s_date = match[2], match[3], match[4]
                                co_id_param, typek = match[5], match[6]

                                logger.info(f"    - 處理 {co_name} ({co_code})")
                                
                                # 2. 抓取詳細內文
                                detail_html = self.fetch_detail((seq_no, s_time, s_date, co_id_param, typek))
                                d = self.parse_detail(detail_html)

                                if d:
                                    # 3. 格式化日期與時間
                                    # p_date: 從 '20260115' 轉為 '2026-01-15'
                                    # p_time: 從 '85759' 轉為 '08:57:59'
                                    p_date = self.roc_to_ad(s_date)
                                    p_time = self.normalize_time(s_time)
                                    
                                    # 4. 存入資料庫
                                    cur.execute("""
                                        INSERT INTO disclosures (
                                            market, company_code, company_name, 
                                            publish_date, publish_time, subject, 
                                            content, source_date, fetch_status
                                        )
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                                        ON CONFLICT DO NOTHING RETURNING id
                                    """, (m_name, co_code, co_name, p_date, p_time, d.get("主旨", ""), d.get("說明", ""), date.today()))

                                    res = cur.fetchone()
                                    if res:
                                        # 5. 關鍵字比對與警報
                                        disclosure_id = res[0]
                                        full_text = f"{d.get('主旨','')}{d.get('說明','')}"
                                        for kw in self.keywords:
                                            if kw in full_text:
                                                cur.execute("""
                                                    INSERT INTO alerts (disclosure_id, matched_keyword) 
                                                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                                                """, (disclosure_id, kw))

                                    conn.commit() # 每處理完一筆就提交，確保進度存檔

                                # 遵守爬蟲禮節，每筆詳細資料間隔一下
                                time.sleep(random.uniform(2, 3.5))
                        curr_k_idx += 1
                        self.save_progress(curr_y, curr_m, curr_k_idx, curr_p)
                    cur.close(); conn.close()
                    time.sleep(5) # 切換市場時多休息一下
                except Exception as e: logger.error(f"❌ 錯誤: {e}"); time.sleep(10)
                curr_m -= 1; curr_k_idx = 0; self.save_progress(curr_y, curr_m, curr_k_idx, curr_p)
                
            curr_y -= 1; curr_m = 12

if __name__ == "__main__":
    MOPSHistoryManager().start_loop()