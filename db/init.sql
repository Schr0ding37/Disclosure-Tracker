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
    -- 確保唯一性
    UNIQUE (company_code, publish_date, publish_time, subject)
);

-- 建立日期索引（這行沒問題）
CREATE INDEX IF NOT EXISTS idx_publish_date ON disclosures(publish_date);

-- 💡 刪除或註釋掉下面這行，因為標準 Docker 鏡像不支援中文分詞索引
-- CREATE INDEX IF NOT EXISTS idx_keyword ON disclosures USING gin(to_tsvector('simplified_chinese', subject || content));

-- 新增通知表
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    disclosure_id INTEGER REFERENCES disclosures(id),
    matched_keyword VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_alert UNIQUE(disclosure_id, matched_keyword)
);

-- 新增使用者表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user', -- 'admin' or 'user'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);