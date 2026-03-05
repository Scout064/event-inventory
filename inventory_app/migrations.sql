-- migrations.sql

-- VERSION X: Example changes
-- ALTER TABLE items ADD COLUMN IF NOT EXISTS price DECIMAL(10,2) DEFAULT 0.00;
-- ALTER TABLE items ADD COLUMN IF NOT EXISTS location VARCHAR(128);

-- VERSION 2: User Profile Expansion
ALTER TABLE users ADD COLUMN IF NOT EXISTS real_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday DATE;

-- ALWAYS AT THE END: Update to the latest version
-- We use INSERT to ensure the version is recorded, 
-- and the update.sh script cleans up older rows.
INSERT INTO schema_version (version) VALUES (2);
