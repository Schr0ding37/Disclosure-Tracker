-- 1. 基本資料表保持不變
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
    fetch_status BOOLEAN DEFAULT FALSE,
    raw_onclick_params TEXT,
    UNIQUE (company_code, publish_date, publish_time, subject)
);

-- 2. 索引優化 (搜尋歷史資料必備)
CREATE INDEX IF NOT EXISTS idx_publish_date ON disclosures(publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_fetch_status ON disclosures(fetch_status) WHERE fetch_status = FALSE;
-- 新增：加速公司代號與名稱的搜尋
CREATE INDEX IF NOT EXISTS idx_company_search ON disclosures(company_code, company_name);

-- 3. 通知表
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    disclosure_id INTEGER REFERENCES disclosures(id) ON DELETE CASCADE,
    matched_keyword VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_alert UNIQUE(disclosure_id, matched_keyword)
);

-- 4. 【新增】自動監控觸發邏輯
-- 這樣無論是 fetch_daily 還是 backfill_history 存入資料，都會自動進 alerts 表
CREATE OR REPLACE FUNCTION auto_match_keywords() RETURNS TRIGGER AS $$
DECLARE
    kw_record RECORD;
    keywords TEXT[];
BEGIN
    -- 這裡假設你的關鍵字存放在某個地方，或者我們直接搜尋 subject/content
    -- 實務上我們會從一個 keywords 表讀取，這裡先示範邏輯：
    -- 如果你的 backend 已經有掃描邏輯，這段可以選配。
    -- 但為了歷史補件方便，建議保留 backend 的掃描邏輯即可。
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;