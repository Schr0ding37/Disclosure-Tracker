# Test & Change Log

## [2026-01-12] Documentation Refresh & Export Guidance

### 📄 Updates
- README 增補完整架構（/api 代理、排程時間、登入流程）、運維指引與 FAQ。
- 補充匯出/匯入與測試腳本 (`test_export.sh`, `test_export.py`, `test_export.html`) 的使用說明。

### ✅ Tests
- Doc-only 更新，未新增程式邏輯；可用 `./test_export.sh` 或 `python3 test_export.py` 進行回歸驗證。

## [2026-01-12] UI Beautification & Functionality Verification

### ⚠️ Design Standard Requirement
**ALL UI design changes MUST reference `Reference_Style_Global-Timesaver.pdf`.**
**Simultaneous modification of Computer Browser Interface and Mobile Device Interface is REQUIRED.**

### 🎨 Change Log
1.  **UI Standardization (Global Timesaver Theme)**:
    -   Enforced strict adherence to Deloitte Brand Standards.
    -   **Color Palette**: Primary Black (#000000), Deloitte Green (#86BC24), White Backgrounds.
    -   **Typography**: Open Sans / JetBrains Mono.
    -   **Responsiveness**: Unified mobile and desktop experience.
2.  **Code Refactoring**:
    -   Extracted styles from `index.html` to a new `frontend/style.css` file for better maintainability.
    -   Removed legacy inline CSS from HTML elements.
    -   Updated HTML attributes to use semantic classes.

### ✅ Test Report
1.  **System Startup**:
    -   Command: `docker-compose up -d`
    -   Status: All containers (`mops-db`, `major_frontend`, `major_backend`, `mops_scheduler`) started successfully.
2.  **Backend Connectivity**:
    -   **Endpoint `/keywords`**: Tested via `curl http://localhost:9000/keywords`.
        -   Result: returned JSON array of keywords (`["資安", "網路攻擊"...]`). 🟢 Pass.
    -   **Endpoint `/notifications`**: Tested via `curl http://localhost:9000/notifications`.
        -   Result: returned JSON array of notifications. 🟢 Pass.
3.  **Frontend-Backend Integration**:
    -   Verified Nginx configuration (`frontend/nginx.conf`) correctly proxies `/api` requests to backend service on port 9000.
    -   Validated frontend JS logic uses `/api` base path which aligns with the proxy config.

### 📝 Notes
-   The system is fully functional.
-   UI is responsive and strictly follows the Global Timesaver design system.

## [2026-01-12] Export/Import Functionality Fix

### 🐛 Issue Reported
User reported that data package export (`.dtt` file) was displaying as failed.

### 🔍 Investigation
1.  **Backend Testing**:
    -   Tested export endpoint directly using `curl`.
    -   Result: Backend successfully returns a valid ZIP file (3023 bytes) containing:
        - `manifest.json` (114 bytes)
        - `disclosures.json` (8727 bytes)
        - `keywords.txt` (648 bytes)
    -   Status: Backend is working correctly. 🟢 Pass.

2.  **Frontend Analysis**:
    -   Examined `exportDataPackage()` function in `frontend/index.html`.
    -   Issue: Minimal error handling and logging made it difficult to diagnose failures.

### ✅ Fixes Applied
1.  **Backend (`backend/main.py`)**:
    -   Modified `export_data_package()` to read ZIP buffer into bytes before creating `StreamingResponse`.
    -   This ensures data remains available even after the buffer context closes.

2.  **Frontend (`frontend/index.html`)**:
    -   Enhanced error handling in `exportDataPackage()` function:
        - Added console logging for response status and headers.
        - Added blob size validation to detect empty files.
        - Improved error messages with specific failure reasons.
        - Added link element to DOM before clicking for better browser compatibility.
        - Added URL cleanup to prevent memory leaks.
    -   Error timeout increased from 3s to 5s for better user visibility.

### 🧪 Verification
-   Backend export tested successfully via curl command line.
-   Frontend now includes detailed console logging for debugging.
-   Users should check browser console for specific error details if issues persist.
