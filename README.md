# 📊 重訊監控與資安事件追蹤系統 (Disclosure-Tracker)

專為追蹤台灣上市櫃公司「重大訊息」設計的自動化監控系統，強化資安事件偵測並提供行動優先的儀表板體驗。系統會自動抓取證交所與櫃買中心公告，依照自訂關鍵字比對並推送通知。

> **✨ 2026/01 更新**：全新 **帳號權限系統**、**Mobile-First Deloitte Global Timesaver UI**、強化匯出/匯入及儀表板統計。

## 🌟 核心功能
- **帳號/角色**：JWT 登入，角色區分 Admin / User。Admin 可新增帳號、管理關鍵字、匯入匯出、清除通知；User 可查詢與瀏覽。
- **儀表板統計**：近 30 天趨勢、關鍵字分佈、上市/上櫃分佈，提供資安警示概況。
- **自動抓取**：開機即抓取一次，並由排程每日 14:00、22:00 重新抓取。
- **關鍵字管理**：即時新增/刪除，儲存後自動重掃歷史資料並重新產生警示。
- **匯出/匯入**：`.dtt`（ZIP）資料包，具備跳過重複與關鍵字合併策略。
- **歷史查詢與通知**：公司代號/名稱 + 關鍵字交叉搜尋；通知可一鍵展開或清空。
- **Mobile-First UI**：全站採 Deloitte Timesaver 配色與字體，桌面與行動裝置一致。

## 🧱 架構總覽
- `docker-compose.yml` 服務：
  - `db`：PostgreSQL 15，資料存放在 `postgres_data/`。
  - `backend`：FastAPI + JWT，路由經 Nginx 以 `/api` 轉發。
  - `frontend`：Nginx 伺服靜態檔 (`frontend/`)，提供 `index.html` 與 `login.html`。
  - `scheduler`：Ofelia 定時呼叫 `fetcher/fetch_daily.py`（14:00、22:00）。
- 初次啟動時 backend 會建立資料表並生成預設 `Admin` 帳號。
- API 健康檢查：`GET http://localhost:9000/health`。

## 🚀 快速開始
1. **環境需求**：Docker + Docker Compose，確保 5432/9000/8080 port 未被佔用。
2. **取得程式碼**
   ```bash
   git clone https://github.com/你的帳號/Disclosure-Tracker.git
   cd Disclosure-Tracker
   ```
3. **啟動服務**
   ```bash
   docker-compose up -d --build
   docker-compose ps              # 確認容器都在 Up 狀態
   curl http://localhost:9000/health
   ```
   首次啟動 backend 會先跑一次 `fetch_daily.py` 再啟動 API。
4. **登入**
   - 瀏覽器前往 `http://localhost:8080/login.html`（無 token 會自動導向此頁）。
   - 預設管理員：`Admin` / `password`。登入後 token 儲存在 localStorage。
   - 建議立即新增專屬帳號並停用預設密碼（目前介面提供新增帳號；如需修改 Admin 密碼請在 DB 更新後重新登入）。

## 🛠️ 使用說明
- **登入/登出**：登入後頂部會顯示使用者資訊；點擊 Logout 會清除 token 並回到 login。
- **使用者管理（Admin）**：頁面頂部的「用戶管理」卡片可新增使用者並查看列表。
- **關鍵字管理（Admin）**：左側「⚙️ 編輯監控關鍵字」儲存後會觸發重新抓取與歷史重掃。
- **通知區塊**：點擊項目可展開公告全文；Admin 可「🗑️ 清除所有通知」重置警示。
- **歷史查詢**：公司代號/名稱 + 關鍵字交叉過濾，表格支援滑鼠懸停高亮。
- **匯出/匯入（Admin）**：
  - 匯出按鈕下載 `.dtt`（ZIP）檔，檔名含時間戳。
  - 匯入按鈕上傳 `.dtt`，會跳過重複紀錄並合併關鍵字後儲存到 `keywords.txt`。

## 🧪 測試與驗證
- **匯出回歸測試（推薦）**：啟動容器後執行  
  ```bash
  ./test_export.sh
  # 或
  python3 test_export.py
  ```
  成功時會在專案根目錄得到 `test_export.dtt`，並印出 ZIP 內容。
- **瀏覽器驗證**：開啟 `test_export.html` → 點擊 `Test Export` 查看結果。
- **API 驗證**：取得 token 後可直接呼叫  
  ```bash
  curl -H "Authorization: Bearer <token>" http://localhost:9000/notifications
  ```

## 🧭 排程與維運
- 排程：Ofelia 於每日 14:00、22:00 執行 `python3 /app/fetcher/fetch_daily.py`。
- 手動重抓：`docker-compose exec backend python3 /app/fetcher/fetch_daily.py`。
- 主要資料：`postgres_data/`（資料庫）、`keywords.txt`（關鍵字檔，需為檔案而非資料夾）。
- 停止/重啟：`docker-compose restart` 或 `docker-compose down` / `up -d`。

## 📁 資料夾結構說明
- `backend/`：FastAPI + JWT 後端；`main.py` 提供 `/token`、`/users`、`/keywords`、`/notifications`、`/export`、`/import` 等端點。
- `fetcher/`：抓取證交所/櫃買中心資料腳本。
- `frontend/`：靜態前端（Deloitte Timesaver 風格）。
  - `login.html`：登入頁面。
  - `index.html`：主儀表板。
  - `style.css`、`assets/`：樣式與圖示。
  - `nginx.conf`：前端 Nginx 設定，將 `/api` 代理到 backend:9000。
- `keywords.txt`：監控關鍵字清單（由 UI 或匯入流程寫入）。
- `test_export.*`：匯出回歸測試腳本與 HTML 測試頁。
- `postgres_data/`：PostgreSQL 持久化資料目錄。

## ❓ 常見問題 (FAQ)
- **無法連線後端**：`docker-compose ps` 確認容器狀態；若 `keywords.txt` 不慎變成資料夾，請刪除資料夾並重建同名檔案。
- **401/403 驗證錯誤**：確認已透過 `login.html` 登入並持有最新 token；Admin 才能存取 `/users`、`/keywords`、`/export`、`/import`、`DELETE /notifications`。
- **匯出檔案為空**：先確認 backend log、`./test_export.sh` 是否通過，並確保已登入 Admin 角色。
- **更新關鍵字**：建議透過前端介面編輯；也可直接修改 `keywords.txt` 後重新啟動容器。

---
*本專案僅供學術研究與投資參考，資料來源為公開資訊觀測站 (MOPS)。*
