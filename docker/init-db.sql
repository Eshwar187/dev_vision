-- DevVision AI: Database Initialization Script
-- Executed on PostgreSQL container startup

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Verify extensions
DO $$
BEGIN
    RAISE NOTICE 'DevVision AI: PostgreSQL initialized with uuid-ossp and vector extensions.';
END
$$;
