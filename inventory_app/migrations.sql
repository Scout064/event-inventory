-- migration_v2.sql (Example: Adding a 'price' and 'location' column)

-- 1. Add the columns (Wrapped in a check if you're feeling fancy, 
-- but usually handled by the deployment script version check)
-- ALTER TABLE items ADD COLUMN IF NOT EXISTS price DECIMAL(10,2) DEFAULT 0.00;
-- ALTER TABLE items ADD COLUMN IF NOT EXISTS location VARCHAR(128);

-- 2. Update the version number
-- UPDATE schema_version SET version = 2;
