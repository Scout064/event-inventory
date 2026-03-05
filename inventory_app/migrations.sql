-- migration_v2.sql (Example: Adding a 'price' and 'location' column)

-- 1. Add the columns (Wrapped in a check if you're feeling fancy, 
-- but usually handled by the deployment script version check)
-- ALTER TABLE items ADD COLUMN IF NOT EXISTS price DECIMAL(10,2) DEFAULT 0.00;
-- ALTER TABLE items ADD COLUMN IF NOT EXISTS location VARCHAR(128);

-- 2. Update the version number
-- UPDATE schema_version SET version = 2;

-- migration_v2.sql (Expanding User Profile Data)
-- 1. Add the new columns to the users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS real_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday DATE;

-- 2. Update the version number (Change 'X' to whatever your next version is)
UPDATE schema_version SET version = 2;
