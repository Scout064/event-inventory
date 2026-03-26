-- migrations.sql

-- VERSION X: Example changes
-- ALTER TABLE items ADD COLUMN IF NOT EXISTS price DECIMAL(10,2) DEFAULT 0.00;
-- ALTER TABLE items ADD COLUMN IF NOT EXISTS location VARCHAR(128);

-- VERSION 2: User Profile Expansion
ALTER TABLE users ADD COLUMN IF NOT EXISTS real_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday DATE;

-- VERSION 3: Settings Table
CREATE TABLE IF NOT EXISTS settings (
    setting_key VARCHAR(64) PRIMARY KEY,
    setting_value VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ALWAYS AT THE END: Update to the latest version
INSERT IGNORE INTO schema_version (version) VALUES (3);

