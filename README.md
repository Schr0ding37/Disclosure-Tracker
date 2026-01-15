# 📊 重訊監控與資安事件追蹤系統 (Disclosure-Tracker)

本系統專為追蹤台灣上市櫃公司「重大訊息」設計，特別強化「資安事件」追蹤。透過「當日監控 (Daily)」與「歷史補件 (Backfill)」雙軌機制，確保資料不漏抓。

---

## 🏗️ 系統架構

系統採用 Docker 容器化部署：
- mops-db: PostgreSQL 15 核心資料庫。
- major_backend: API 服務與每日定時抓取 (fetch_daily.py)。
- backfill_worker: 專門回溯過往年份的歷史數據 (backfill_history.py)。
- major_frontend: Nginx 網頁介面。



---

## 🚀 快速開始

1. 環境需求：Docker 與 Docker Compose。
2. 啟動核心服務：sudo docker compose up -d
3. 啟動歷史回補：sudo docker compose -f docker-compose.backfill.yml up -d

---

## 🔍 資料庫與查詢機制

### 資料表設計 (Database Schema)



系統使用 PostgreSQL 15，核心欄位說明如下：

- company_code: 公司股票代號
- publish_date: 西元發布日期 (格式為 YYYY-MM-DD)
- subject: 公告主旨 (建立 DESC 索引加速搜尋)
- fetch_status: 抓取狀態 (TRUE 代表成功，FALSE 代表待抓取)

#### 核心約束與優化：
- UNIQUE 唯一鍵: (company_code, publish_date, publish_time, subject)。
- 防止重複：確保每日抓取與歷史補件程序不會寫入重複資料。
- 索引優化: 針對日期與公司代號建立索引，支援數十萬筆資料的毫秒級查詢。

---

## 🛠️ 進階管理

### A. 修改歷史補件目標年份
若要修改補件目標（預設為民國 114 年），可透過環境變數修改：
指令範例：sudo docker compose -f docker-compose.backfill.yml run -e BACKFILL_TARGET_YEAR=110 backfill_worker

### B. 斷點續傳機制
系統會將進度儲存於 progress.json 檔案中。
若程式中斷或容器重啟，系統會自動讀取該檔案，從最後處理的「年、月、分頁」位置繼續執行，無需手動干預。



---

## 📁 資料夾結構說明
- backend/ : 存放 API 核心程式碼。
- fetcher/ : 包含當日抓取與歷史回補腳本。
- frontend/ : 網頁介面資源。
- keywords.txt : 監控關鍵字清單。
- postgres_data/ : 資料庫檔案持久化目錄。

---

## ❓ 常見問題 (FAQ)

Q1：如何確認歷史補件正在執行？
答：觀察 backfill.log 檔案內容，或執行指令 docker logs -f backfill_worker。

Q2：如何更新監控關鍵字？
答：直接透過網頁介面的「系統設定」修改，系統會自動同步至 keywords.txt 並在下次抓取時生效。
