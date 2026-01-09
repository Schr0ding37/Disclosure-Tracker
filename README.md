# 🚀 Disclosure-Tracker

這是一個基於 Docker 開發的自動化股市重大訊息監控系統。系統能定時追蹤公開資訊觀測站（MOPS）的最新動態，並根據使用者設定的關鍵字進行即時比對與主動通知。

## ✨ 核心功能
* **自動化追蹤 (Auto-Tracking)**：每日定時從證交所 (TWSE) 與櫃買中心 (TPEx) 獲取最新重訊。
* **智慧監控 (Smart Monitoring)**：後端自動比對關鍵字，命中時立即存入 Alerts 資料表。
* **同步設定 (Server-side Config)**：監控清單儲存於伺服器端，支援多裝置同步設定。
* **持久化存儲 (Data Persistence)**：資料庫掛載至本機 `./postgres_data`，確保數據安全性。
* **資料導出 (Data Export)**：支持一鍵導出包含完整內文的 CSV 報表。

---

## 🚀 快速建置步驟

### 1. 準備環境
確保電腦已安裝 Docker 與 Docker Desktop。

### 2. 檔案結構
在專案根目錄 `Disclosure-Tracker/` 下：
- backend/ (FastAPI 與 Dockerfile)
- db/ (init.sql)
- fetcher/ (fetch_daily.py)
- frontend/ (index.html)
- docker-compose.yml
- keywords.txt (手動先 touch 一個空白檔)

### 3. 啟動系統
docker compose up -d --build

---

## 🛠️ 管理員工具箱 (Debug 指令)

### 🔍 數據庫操作
- 統計總追蹤筆數：
  docker exec -it mops-db psql -U mops -d mops -c "SELECT count(*) FROM disclosures;"

- 查詢最新 5 筆監測紀錄：
  docker exec -it mops-db psql -U mops -d mops -c "SELECT publish_date, company_name, subject FROM disclosures ORDER BY publish_date DESC LIMIT 5;"

- 查看關鍵字命中列表：
  docker exec -it mops-db psql -U mops -d mops -c "SELECT * FROM alerts;"

### 🚀 手動任務
- 強制立即觸發全球抓取任務：
  docker exec -it major_backend python3 /app/fetcher/fetch_daily.py

### 🐞 故障排除
- 實時查看系統日誌：
  docker logs major_backend -f

- 重置所有容器與數據：
  docker compose down -v