CREATE TABLE IF NOT EXISTS door_imports (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename text NOT NULL,
    checksum char(64) NOT NULL UNIQUE,
    row_count integer NOT NULL CHECK (row_count > 0),
    incomplete_count integer NOT NULL DEFAULT 0 CHECK (incomplete_count >= 0),
    created_count integer NOT NULL DEFAULT 0 CHECK (created_count >= 0),
    updated_count integer NOT NULL DEFAULT 0 CHECK (updated_count >= 0),
    imported_by text NOT NULL REFERENCES users(username),
    imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS door_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    import_id bigint NOT NULL REFERENCES door_imports(id),
    code text NOT NULL UNIQUE,
    facility_code text NOT NULL REFERENCES facilities(code),
    closed_at timestamp,
    reopened_at timestamp,
    note text NOT NULL DEFAULT '',
    CHECK (closed_at IS NOT NULL OR reopened_at IS NOT NULL),
    CHECK (closed_at IS NULL OR reopened_at IS NULL OR reopened_at > closed_at)
);

CREATE INDEX IF NOT EXISTS door_records_period ON door_records (closed_at, reopened_at);
CREATE INDEX IF NOT EXISTS door_records_facility ON door_records (facility_code, code);

ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1;
ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS revises bigint REFERENCES snapshots(id);
ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS affected jsonb;
