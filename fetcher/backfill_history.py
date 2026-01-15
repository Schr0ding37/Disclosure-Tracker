import requests
import re
import time
import json
import random
import os
import psycopg2
import logging
import datetime
from datetime import date
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- 配置 ---
DB_URL = os.getenv("DATABASE_URL", "postgresql://mops:mops123@mops-db:5432/mops")
PROGRESS_FILE = "/app/fetcher/progress.json"
KEYWORDS_FILE = "/app/keywords.txt"
TARGET_YEAR = int(os.getenv("BACKFILL_TARGET_YEAR", 114))
MAX_WORKERS = 3  # 建議 3 即可，平衡速度與安全

def taipei_time(*args):
    tz_plus8 = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_plus8).timetuple()

logging.Formatter.converter = taipei_time
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
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
            try:
                with open(PROGRESS_FILE, 'r') as f:
                    return json.load(f)
            except: pass
        return {"current_year": 115, "current_month": 1, "current_kind_idx": 0, "current_page": 1}

    def save_progress(self, year, month, kind_idx, page):
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({"current_year": year, "current_month": month, "current_kind_idx": kind_idx, "current_page": page}, f)

    def fetch_list(self, year, month, kind, page=1):
        url = "https://mopsov.twse.com.tw/mops/web/ajax_t51sb10"
        payload = {
            "encodeURIComponent": "1", "step": "1", "firstin": "true",
            "TYPEK": "", "Stp": "4", "r1": "1", "KIND": kind, 
            "year": str(year), "month1": str(month), "begin_day": "1", "end_day": "31", 
            "Orderby": "1", "PCount": "15", "pagenum": str(page)
        }
        time.sleep(random.uniform(4, 7)) # 抓清單稍微快一點
        try:
            res = self.session.post(url, data=payload, headers=self.base_headers, timeout=30)
            if "FOR SECURITY REASONS" in res.text: return "BLOCKED"
            res.encoding = 'utf-8'
            return res.text
        except: return None

    def process_single_disclosure(self, match, m_name):
        """Worker 任務：抓取單筆詳細資料"""
        co_code, co_name, seq_no, s_time, s_date, co_id_param, typek = match
        # --- 在這裡加入 Log ---
        logger.info(f"   [Worker] 開始抓取: {co_code} {co_name}")

        try:
            url = "https://mopsov.twse.com.tw/mops/web/ajax_t05st01"
            payload = {
                "encodeURIComponent": "1", "step": "2", "firstin": "1", "off": "1",
                "co_id": co_id_param, "TYPEK": typek, "spoke_date": s_date,
                "spoke_time": s_time, "seq_no": seq_no
            }
            # 每個 worker 獨立隨機靜置，分散併發壓力
            time.sleep(random.uniform(6, 10)) 
            res = self.session.post(url, data=payload, headers=self.base_headers, timeout=30)
            res.encoding = 'utf-8'
            
            d = self.parse_detail(res.text)
            if not d: return None

            return {
                "market": m_name, "code": co_code, "name": co_name.strip(),
                "date": self.roc_to_ad(s_date), "time": self.normalize_time(s_time),
                "subject": d.get("主旨", ""), "content": d.get("說明", ""),
            }
        except Exception as e:
            logger.error(f"⚠️ 抓取 {co_name} 失敗: {e}")
            return None

    def parse_detail(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table', {'class': 'hasBorder'})
        if not table: return None

        # 1. 建立一個對應字典，把所有標籤與內容配對
        raw_data = {}
        rows = table.find_all('tr')
        for tr in rows:
            # 標題可能是 td 或 th，且 class 包含 tblHead 或 tt
            heads = tr.find_all(['td', 'th'], {'class': ['tblHead', 'tt']})
            # 內容通常是 odd 或 even，或是任何沒有 tblHead 的 td
            values = tr.find_all('td', {'class': ['odd', 'even']})
            
            # 情況 A：標題與內容在同一列交替出現 (115/01/14 版本)
            if len(heads) == len(values) or (len(heads) > 0 and len(values) > 0):
                for h, v in zip(heads, values):
                    k = h.get_text(strip=True)
                    pre = v.find('pre')
                    val = pre.get_text().strip() if pre else v.get_text(strip=True)
                    raw_data[k] = val.replace('\xa0', ' ')

        # 2. 語義化提取：用「關鍵字集合」來找主旨與說明
        # 這樣即使未來變成「公告主旨」、「全文說明」也能抓到
        subject_keys = ['主旨', '公告主題', '主題']
        content_keys = ['說明', '當日重大訊息之詳細內容', '詳細內容', '事實發生日', '發生緣由']

        # 提取所有命中關鍵字的內容
        subject = next((raw_data[k] for k in subject_keys if k in raw_data), "")
        
        # 說明部分比較特殊：我們把所有看起來像內容的欄位串起來
        # 這樣可以確保關鍵字過濾（如：新藥、授權）絕對不會漏掉
        content_parts = [raw_data[k] for k in content_keys if k in raw_data]
        content = "\n".join(content_parts)

        # 3. 終極保底：如果還是空的，把整個表格的文字都塞進去
        if not subject and not content:
            content = table.get_text(separator="\n", strip=True)
            subject = "（特殊格式解析）"

        return {
            "主旨": subject,
            "說明": content
        }

    def roc_to_ad(self, date_str):
        s = str(date_str).strip()
        if len(s) == 8: return f"{s[:4]}-{s[4:6]}-{s[6:]}"
        try:
            y = int(s[:-4]) + 1911
            return f"{y:04d}-{s[-4:-2]}-{s[-2:]}"
        except: return None

    def normalize_time(self, t):
        s = re.sub(r'[^0-9]', '', str(t)).zfill(6)
        return f"{s[:2]}:{s[2:4]}:{s[4:]}"

    def get_total_pages(self, html):
        page_numbers = re.findall(r"pagenum\.value='(\d+)'", html)
        return max(int(n) for n in page_numbers) if page_numbers else 1

    def extract_params(self, html):
        results = []
        soup = BeautifulSoup(html, 'html.parser')
        rows = soup.find_all('tr', {'class': ['odd', 'even']})
        pattern = r'seq_no\.value\s*=\s*["\'](\d+)["\'];.*?spoke_time\.value\s*=\s*["\'](\d+)["\'];.*?spoke_date\.value\s*=\s*["\'](\d+)["\'];.*?co_id\.value\s*=\s*["\'](\d+)["\'];.*?TYPEK\.value\s*=\s*["\'](\w+)["\']'
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 6: continue
            btn = row.find('input', {'type': 'button', 'value': '詳細資料'})
            if btn and btn.get('onclick'):
                m = re.search(pattern, btn.get('onclick'), re.DOTALL)
                if m:
                    results.append((tds[0].get_text(strip=True), tds[1].get_text(strip=True), 
                                    m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)))
        return results

    def start_loop(self):
        prog = self.load_progress()
        curr_y, curr_m, curr_k_idx, curr_p = prog["current_year"], prog["current_month"], prog["current_kind_idx"], prog["current_page"]
        markets = [('L', '上市'), ('O', '上櫃')]
        
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        while curr_y >= TARGET_YEAR:
            while curr_m >= 1:
                try:
                    while curr_k_idx < len(markets):
                        m_kind, m_name = markets[curr_k_idx]
                        while True:
                            html = self.fetch_list(curr_y, curr_m, m_kind, curr_p)
                            if html == "BLOCKED":
                                logger.error("🛑 行為封鎖！停止執行。")
                                return
                            if not html or "查詢無資料" in html: break
                            
                            total_pages = self.get_total_pages(html)
                            matches = self.extract_params(html)
                            logger.info(f"📂 {curr_y}/{curr_m} | {m_name} | P.{curr_p}/{total_pages} | 發現 {len(matches)} 筆")

                            # --- 併行抓取機制 ---
                            success_count = 0
                            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                                futures = {executor.submit(self.process_single_disclosure, m, m_name): m for m in matches}
                                for future in as_completed(futures):
                                    data = future.result()
                                    if data:
                                        cur.execute("""
                                            INSERT INTO disclosures (market, company_code, company_name, publish_date, publish_time, subject, content, source_date, fetch_status)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE) ON CONFLICT DO NOTHING RETURNING id
                                        """, (data['market'], data['code'], data['name'], data['date'], data['time'], data['subject'], data['content'], date.today()))
                                        
                                        res = cur.fetchone()
                                        if res:
                                            full_text = f"{data['subject']}{data['content']}"
                                            for kw in self.keywords:
                                                if kw in full_text:
                                                    cur.execute("INSERT INTO alerts (disclosure_id, matched_keyword) VALUES (%s, %s) ON CONFLICT DO NOTHING", (res[0], kw))

                                        # --- 在這裡加入 Log ---
                                        logger.info(f"   [DB] 已存入: {data['code']} {data['name']}")  

                                        conn.commit()
                                        success_count += 1

                            # --- 安全存檔判斷 ---
                            threshold = 0.4  # 設定成功率閾值，例如 80% 以上就允許跳過
                            success_rate = success_count / len(matches) if len(matches) > 0 else 0

                            if success_count == len(matches):
                                logger.info(f"✅ 第 {curr_p} 頁全數處理成功 ({success_count}/{len(matches)})")
                            elif success_rate >= threshold:
                                logger.warning(f"⚠️ 第 {curr_p} 頁部分失敗 ({success_count}/{len(matches)})，但達到門檻 {threshold}，跳過繼續。")
                            else:
                                logger.error(f"❌ 第 {curr_p} 頁失敗過多 ({success_count}/{len(matches)})")

                            # 往下執行換頁
                            if curr_p < total_pages:
                                curr_p += 1
                                self.save_progress(curr_y, curr_m, curr_k_idx, curr_p)
                            else:
                                curr_p = 1
                                break # 換市場
                        
                        curr_k_idx += 1
                        self.save_progress(curr_y, curr_m, curr_k_idx, curr_p)
                    
                    curr_m -= 1
                    curr_k_idx = 0
                    self.save_progress(curr_y, curr_m, curr_k_idx, curr_p)
                except Exception as e:
                    logger.error(f"❌ 迴圈異常: {e}")
                    time.sleep(20)
            
            curr_y -= 1
            curr_m = 12
            self.save_progress(curr_y, curr_m, curr_k_idx, curr_p)

        cur.close()
        conn.close()

if __name__ == "__main__":
    MOPSHistoryManager().start_loop()